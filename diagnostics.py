"""Bounded diagnostic waits; progress never removes the overall time limit."""
import time


class ProgressDeadline:
    def __init__(self, now, idle_seconds=30, total_seconds=300):
        self.started = self.last_progress = now
        self.idle_seconds, self.total_seconds = idle_seconds, total_seconds
        self.token = None

    def check(self, now, token, stage):
        if token != self.token:
            self.token, self.last_progress = token, now
        if now - self.started >= self.total_seconds:
            raise TimeoutError(f'Overall {self.total_seconds}-second limit during {stage}')
        if now - self.last_progress >= self.idle_seconds:
            raise TimeoutError(f'No progress for {self.idle_seconds} seconds during {stage}')


def wait_for_camera(future, worker, adapter, stop, label):
    limit = ProgressDeadline(time.monotonic())
    last_print = float('-inf')
    while not future.done():
        now = time.monotonic()
        progress = getattr(adapter, 'scan_progress', None)
        # Each operation creates a new immutable progress record. The scan
        # sequence restarts for subsequent scans, so retain record identity too.
        token = (worker.stage, getattr(adapter, 'stage', ''), id(progress))
        stage = worker.stage + ': ' + getattr(adapter, 'stage', '')
        limit.check(now, token, stage)
        if now - last_print >= 2:
            print(label + ': ' + stage, flush=True)
            last_print = now
        if stop.wait(.2):
            raise RuntimeError('Test interrupted during ' + label.lower())
    return future.result()
