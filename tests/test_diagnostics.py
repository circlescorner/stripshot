import unittest
from concurrent.futures import Future
from unittest.mock import MagicMock
from diagnostics import ProgressDeadline, wait_for_camera

class DiagnosticWaitTests(unittest.TestCase):
    def test_progressing_49_second_inventory_allowed(self):
        limit = ProgressDeadline(0)
        for second in range(50):
            limit.check(second, second, 'metadata')

    def test_blocked_call_times_out(self):
        limit = ProgressDeadline(0)
        limit.check(0, 'call', 'metadata')
        limit.check(29.9, 'call', 'metadata')
        with self.assertRaisesRegex(TimeoutError, 'No progress'):
            limit.check(30, 'call', 'metadata')

    def test_progress_cannot_extend_overall_cap(self):
        limit = ProgressDeadline(0)
        for second in range(300):
            limit.check(second, second, 'metadata')
        with self.assertRaisesRegex(TimeoutError, 'Overall'):
            limit.check(300, 300, 'metadata')

    def test_failed_future_propagates(self):
        future = Future()
        future.set_exception(RuntimeError('USB failed'))
        with self.assertRaisesRegex(RuntimeError, 'USB failed'):
            wait_for_camera(future, MagicMock(), MagicMock(), MagicMock(), 'Inventory')
