"""A single CUPS submission. Spooler acceptance is not physical completion."""
import os
import re
import subprocess


class Printer:
    def __init__(self, config):
        self.config = config

    def submit(self, sheet, batch_id):
        if not self.config['enabled']:
            return {'status': 'dry_run', 'job_id': None}
        command = ['lp', '-d', self.config['queue'], '-n', '1', '-t', 'Stripshot ' + batch_id]
        for name, value in self.config['options'].items():
            command += ['-o', f'{name}={value}']
        command += ['--', str(sheet)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=45,
                                env={**os.environ, 'LC_ALL': 'C'})
        match = re.search(r'request id is (\S+)', result.stdout)
        if result.returncode or not match:
            raise RuntimeError('CUPS submission uncertain: ' + (result.stderr or result.stdout)[:500])
        return {'status': 'submitted', 'job_id': match.group(1)}

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
