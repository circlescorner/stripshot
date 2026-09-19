import subprocess
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from printer import Printer

REPORT = '''
        marker-change-time (integer) = 1000
        printer-up-time (integer) = 1060
        marker-levels (integer) = 75
        marker-message (textWithoutLanguage) = 150 native prints remaining on 6x8 (A5) media
        marker-names (nameWithoutLanguage) = 6x8 (A5)
'''


class PrinterStatusTests(unittest.TestCase):
    def test_driver_count_is_read_only_and_available_with_printing_disabled(self):
        p = Printer({'enabled': False, 'queue': 'DNP_DS40'})
        with patch('printer.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=REPORT)) as run, patch('printer.time.time', return_value=2000):
            result = p.supplies()
        self.assertEqual(result['prints_remaining'], 150)
        self.assertEqual(result['percent'], 75)
        self.assertEqual(result['media'], '6x8 (A5)')
        self.assertEqual(result['reported_at'], 1940)
        command = run.call_args.args[0]
        self.assertEqual(command[0], 'ipptool')
        self.assertIn('ipp://localhost:631/printers/DNP_DS40', command)
        self.assertEqual(run.call_args.kwargs['timeout'], 6)
        from pathlib import Path
        query = Path(command[-1]).read_text()
        self.assertIn('OPERATION Get-Printer-Attributes', query)
        self.assertNotIn('Print-Job', query)

    def test_empty_roll_is_zero_and_unknown_is_not_an_estimate(self):
        p = Printer({'enabled': True, 'queue': 'DNP_DS40'})
        cases = [
            (REPORT.replace('150 native', '0 native').replace('= 75', '= 0'), 0, 0),
            (REPORT.replace('150 native', '-1 native').replace('= 75', '= -1'), None, None),
            ('marker-levels (integer) = 75\n', None, 75),
            ('marker-message (textWithoutLanguage) = 12 prints remaining in job\n', None, None),
        ]
        for report, remaining, percent in cases:
            with self.subTest(report=report), patch('printer.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=report)):
                result = p.supplies()
                self.assertEqual(result['prints_remaining'], remaining)
                self.assertEqual(result['percent'], percent)

    def test_no_queue_does_not_query_cups(self):
        with patch('printer.subprocess.run') as run:
            self.assertIsNone(Printer({'enabled': False}).supplies()['prints_remaining'])
            run.assert_not_called()

    def test_failed_or_missing_tool_clears_old_count_and_recovers(self):
        p = Printer({'enabled': False, 'queue': 'DNP_DS40'})
        with patch('printer.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=REPORT)):
            p._refresh_status()
        self.assertEqual(p.cached_details()['prints_remaining'], 150)
        for failure in (FileNotFoundError('ipptool'), subprocess.TimeoutExpired('ipptool', 6)):
            with patch('printer.subprocess.run', side_effect=failure):
                p._refresh_status()
            self.assertIsNone(p.cached_details()['prints_remaining'])
        with patch('printer.subprocess.run', return_value=SimpleNamespace(returncode=1, stdout=REPORT)):
            p._refresh_status()
        self.assertIsNone(p.cached_details()['prints_remaining'], 'failed output must not be displayed as a valid count')
        with patch('printer.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=REPORT)):
            p._refresh_status()
        self.assertEqual(p.cached_details()['prints_remaining'], 150)

    def test_slow_supply_query_is_shared_and_does_not_block_panel(self):
        p = Printer({'enabled': False, 'queue': 'DNP_DS40'})
        entered, release = threading.Event(), threading.Event()
        def slow():
            entered.set(); release.wait(2)
            return {'prints_remaining': 150}
        with patch.object(p, 'supplies', side_effect=slow) as supplies:
            try:
                start = time.monotonic()
                for _ in range(20): p.cached_details()
                self.assertLess(time.monotonic() - start, .5)
                self.assertTrue(entered.wait(1))
                self.assertEqual(supplies.call_count, 1)
            finally:
                release.set()
            deadline = time.monotonic() + 2
            while p._status_running and time.monotonic() < deadline: time.sleep(.01)
            self.assertEqual(p.cached_details()['prints_remaining'], 150)
