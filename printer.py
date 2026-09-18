"""A single CUPS submission. Spooler acceptance is not physical completion."""
import os
import re
import subprocess
import threading
import time


class Printer:
    def __init__(self, config):
        self.config = config
        self._status_lock = threading.Lock()
        self._status_value = 'Checking printer status…'
        self._status_next = 0
        self._status_running = False

    def submit(self, sheet, batch_id):
        if not self.config['enabled']:
            return {'status': 'dry_run', 'job_id': None}
        command = ['lp', '-d', self.config['queue'], '-n', '1', '-t', 'Stripshot ' + batch_id, '-o', 'number-up=1']
        for name, value in self.config['options'].items():
            command += ['-o', f'{name}={value}']
        command += ['--', str(sheet)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=45,
                                env={**os.environ, 'LC_ALL': 'C'})
        match = re.search(r'request id is (\S+)', result.stdout)
        if result.returncode or not match:
            raise RuntimeError('CUPS submission uncertain: ' + (result.stderr or result.stdout)[:500])
        return {'status': 'submitted', 'job_id': match.group(1)}

    def cached_status(self):
        """One bounded CUPS read shared by all dashboards; never block HTTP."""
        if not self.config['enabled']:
            return 'Dry run — no physical print jobs'
        with self._status_lock:
            if not self._status_running and time.monotonic() >= self._status_next:
                self._status_running = True
                threading.Thread(target=self._refresh_status, name='printer-status', daemon=True).start()
            return self._status_value

    def _refresh_status(self):
        try:
            value = self.status()
        except Exception as exc:
            value = 'Printer status unavailable: ' + str(exc)
        with self._status_lock:
            self._status_value = value
            self._status_next = time.monotonic() + 15
            self._status_running = False

    def status(self):
        if not self.config['enabled']:
            return 'Dry run — no physical print jobs'
        try:
            result = subprocess.run(['lpstat', '-p', self.config['queue']],
                                    capture_output=True, text=True, timeout=5,
                                    env={**os.environ, 'LC_ALL': 'C'})
            return (result.stdout or result.stderr).strip()[:500]
        except (OSError, subprocess.TimeoutExpired) as exc:
            return str(exc)
