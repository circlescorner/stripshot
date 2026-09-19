"""Operator-requested clean shutdown; restart replaces the same process."""
import os
from pathlib import Path
import signal
import sys
import threading
import time


class ApplicationControl:
    def __init__(self, engine, config_path, dev_server=False):
        self.engine = engine
        self.config_path = str(Path(config_path).resolve())
        self.dev_server = dev_server
        self.action = None
        self.printing_enabled = None
        self.event = threading.Event()

    def available(self):
        e = self.engine
        return (e.config.get('kiosk_mode', False) and e.software and self.action is None
                and e.phase in ('watching', 'error') and not e.state['current']
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
            # Close the coordinator to new capture/print actions before acknowledging.
            self.engine.stop_event.set()
            self.event.set()
            return {'action': self.action, 'accepted': True}

    def watch(self):
        self.event.wait()
        time.sleep(1)  # Let the HTTP acknowledgement reach the browser first.
        os.kill(os.getpid(), signal.SIGTERM)

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
        # Called only after server shutdown, Engine.stop(), and release of the data lock.
        for worker in self.engine.workers.values():
            if worker.is_alive(): worker.join(timeout=10)
        if any(w.is_alive() or w.cleanup_error for w in self.engine.workers.values()):
            raise RuntimeError('Camera cleanup did not finish cleanly. Stripshot stopped without starting another camera owner')
        command = self.restart_command()
        os.execv(command[0], command)
