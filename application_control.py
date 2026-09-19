"""Operator-requested clean shutdown; restart replaces the same process."""
import os
import logging
from pathlib import Path
import signal
import sys
import threading

LOG = logging.getLogger(__name__)


class ApplicationControl:
    def __init__(self, engine, config_path, dev_server=False):
        self.engine = engine
        self.config_path = str(Path(config_path).resolve())
        self.dev_server = dev_server
        self.action = None
        self.printing_enabled = None
        self.event = threading.Event()
        self.closed = threading.Event()
        self.state = 'idle'
        self.message = None

    def available(self):
        e = self.engine
        return (e.config.get('kiosk_mode', False) and e.software and self.action is None
                and e.phase in ('watching', 'error', 'reconnecting') and not e.state['current']
                and not any(not f.done() for f in e.capture_futures))

    def request(self, candidate):
        if not isinstance(candidate, dict) or set(candidate) != {'action'} or candidate['action'] not in ('stop', 'restart'):
            raise ValueError('Choose stop or restart')
        with self.engine.lock:
            if not self.available():
                raise ValueError('Stop or restart only between sessions, with no active or held batch')
            self.action = candidate['action']
            self.printing_enabled = self.engine.config['printer']['enabled']
            self.engine.phase = 'stopping'
            self.state = 'stopping'
            self.message = 'Waiting for the coordinator and camera sessions to close safely.'
            # Close the coordinator to new capture/print actions before acknowledging.
            self.engine.stop_event.set()
            self.event.set()
            return {'action': self.action, 'accepted': True}

    def watch(self):
        self.event.wait()
        if self.closed.wait(1): return  # Let the HTTP acknowledgement reach the browser first.
        previous = None
        while not self.closed.is_set():
            self.engine.stop(timeout=1)
            if self.closed.is_set(): return
            blockers = self.engine.cleanup_blockers()
            with self.engine.lock:
                self.state = 'blocked' if blockers else 'closing'
                self.message = ('Shutdown is waiting: ' + '; '.join(blockers) +
                    '. This instance still owns the booth. No replacement has started. '
                    'Check camera power/USB and the existing terminal for details; do not start another copy. '
                    'If release failed rather than remaining in progress, exit this instance from its terminal (Ctrl+C) before relaunching.'
                    if blockers else 'Cameras released. Closing the booth now.')
            if blockers != previous:
                LOG.warning('%s requested: %s', self.action, self.message)
                previous = blockers
            if not blockers:
                os.kill(os.getpid(), signal.SIGTERM)
                return
            self.closed.wait(.25)

    def status(self):
        return {'state': self.state, 'message': self.message,
                'blockers': self.engine.cleanup_blockers() if self.action else []}

    def start(self):
        threading.Thread(target=self.watch, name='application-control', daemon=True).start()

    def restart_command(self):
        command = [sys.executable, str(Path(__file__).with_name('app.py').resolve()),
                   '--config', self.config_path, '--kiosk',
                   '--live-printing' if self.printing_enabled else '--dry-run']
        if self.dev_server: command.append('--dev-server')
        return command

    def finish(self):
        if self.action != 'restart': return
        # Called with the data lock held, after server shutdown and Engine.stop().
        blockers = self.engine.cleanup_blockers()
        if blockers:
            raise RuntimeError('Camera cleanup did not finish cleanly: ' + '; '.join(blockers) +
                               '. No replacement camera owner was started')
        command = self.restart_command()
        os.execv(command[0], command)

    def close(self):
        self.closed.set()
        self.event.set()
