"""A single CUPS submission. Spooler acceptance is not physical completion."""
import os
from pathlib import Path
from urllib.parse import quote
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
        self._supplies = {'prints_remaining': None, 'media': None, 'percent': None,
                          'reported_at': None, 'message': 'Checking remaining prints…'}

    def submit(self, sheet, batch_id):
        if not self.config['enabled']:
            return {'status': 'dry_run', 'job_id': None}
        quality_options = {}
        if 'quality' in self.config:
            from qualification import DS40_OPTIONS
            from printer_quality import QUALITY_CONTEXT, verify_driver, driver_choices
            if self.config.get('options') != DS40_OPTIONS:
                raise ValueError('DS40 quality settings require unchanged qualified media and geometry')
            verify_driver(self.config['quality'], driver_choices(self.config.get('queue')))
            quality_options = {**QUALITY_CONTEXT, **self.config['quality']}
        command = ['lp', '-d', self.config['queue'], '-n', '1', '-t', 'Stripshot ' + batch_id, '-o', 'number-up=1']
        for name, value in {**self.config['options'], **quality_options}.items():
            command += ['-o', f'{name}={value}']
        command += ['--', str(sheet)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=45,
                                env={**os.environ, 'LC_ALL': 'C'})
        match = re.search(r'request id is (\S+)', result.stdout)
        if result.returncode or not match:
            raise RuntimeError('CUPS submission uncertain: ' + (result.stderr or result.stdout)[:500])
        return {'status': 'submitted', 'job_id': match.group(1)}

    def cached_status(self):
        return self.cached_details()['status']

    def cached_details(self):
        """One bounded CUPS read shared by dashboards; never block HTTP."""
        with self._status_lock:
            if not self._status_running and time.monotonic() >= self._status_next:
                self._status_running = True
                threading.Thread(target=self._refresh_status, name='printer-status', daemon=True).start()
            return {'status': self._status_value, **self._supplies}

    def _refresh_status(self):
        try:
            value = self.status()
        except Exception as exc:
            value = 'Printer status unavailable: ' + str(exc)
        try:
            supplies = self.supplies()
        except Exception:
            supplies = {'prints_remaining': None, 'media': None, 'percent': None,
                        'reported_at': None, 'message': 'Remaining prints unavailable — check CUPS and the printer.'}
        with self._status_lock:
            self._supplies = supplies
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

    def supplies(self):
        """Use the driver's count, never estimate sheets from a percentage."""
        empty = {'prints_remaining': None, 'media': None, 'percent': None,
                 'reported_at': None, 'message': 'Remaining prints unavailable — no driver count reported.'}
        queue = self.config.get('queue')
        if not queue:
            return {**empty, 'message': 'No printer queue configured.'}
        result = subprocess.run(
            ['ipptool', '-T', '4', '-tv',
             'ipp://localhost:631/printers/' + quote(queue, safe=''),
             str(Path(__file__).resolve().parent / 'tools' / 'printer-status.test')],
            capture_output=True, text=True, timeout=6,
            env={**os.environ, 'LC_ALL': 'C'})
        if result.returncode:
            raise RuntimeError('CUPS supplies unavailable')
        attrs = dict(re.findall(r'^\s*([a-z-]+) \([^\n)]+\) = ([^\n]*)$', result.stdout, re.MULTILINE))
        message = attrs.get('marker-message', '').strip().strip('"')
        match = re.fullmatch(r'(\d+) native prints remaining on (.+) media', message)
        if match:
            empty.update(prints_remaining=int(match[1]), media=match[2],
                         message='Last reported by the printer driver; updates after printing.')
        elif attrs.get('marker-names'):
            empty['media'] = attrs['marker-names'].strip().strip('"')
        level = attrs.get('marker-levels', '')
        if level.isdigit() and 0 <= int(level) <= 100:
            empty['percent'] = int(level)
        changed, uptime = attrs.get('marker-change-time', ''), attrs.get('printer-up-time', '')
        if changed.isdigit() and uptime.isdigit() and 0 < int(changed) <= int(uptime):
            empty['reported_at'] = time.time() - (int(uptime) - int(changed))
        return empty
