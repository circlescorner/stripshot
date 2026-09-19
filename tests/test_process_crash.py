"""Real process death at durable record boundaries, using simulated cameras only."""
import json
import subprocess
import sys
import time
import unittest

import test_software_app


class ProcessCrashTests(unittest.TestCase):
    setUp = test_software_app.SoftwareAppTests.setUp
    tearDown = test_software_app.SoftwareAppTests.tearDown
    engine = test_software_app.SoftwareAppTests.engine
    def test_sigkill_preserves_uncertain_shutter_and_releases_process_lock(self):
        for boundary in ('capture_intent', 'capture_returned'):
            with self.subTest(boundary=boundary):
                marker = self.root / ('ready-' + boundary)
                child = subprocess.Popen([sys.executable, '-c', '''
import sys, time
from pathlib import Path
from batch import Engine
from camera import DemoCamera
from config import load_config
cfg = load_config(sys.argv[1])
e = Engine(cfg, {c: DemoCamera(Path(sys.argv[1]).parent / 'cards', c) for c in ('A', 'B')})
e.freeze(software=True)
e.software_record('A', 0, 'capture_intent', {'count': 1})
if sys.argv[3] == 'capture_returned':
    e.software_record('A', 0, 'capture_returned', {'folder': '/store', 'name': 'unknown.JPG'})
Path(sys.argv[2]).write_text('ready')
while True: time.sleep(1)
''', str(self.cfgpath), str(marker), boundary])
                try:
                    deadline = time.monotonic() + 5
                    while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
                        time.sleep(.01)
                    self.assertTrue(marker.exists(), 'Child did not persist the record')
                    child.kill()
                    child.wait(timeout=5)
                    e, cards = self.engine(phase='capture_held')
                    with self.assertRaisesRegex(ValueError, 'Uncertain shutter'):
                        e.request('resume_capture').result(5)
                    self.assertEqual(sum(c.shutters for c in cards.values()), 0)
                    batchid = e.status()['current']['id']
                    e.request('abandon_capture').result(5)
                    archive = json.loads((e.root / 'batches' / batchid / 'manifest.json').read_text())
                    self.assertIn('intent', archive['shots']['A'][0])
                    if boundary == 'capture_returned':
                        self.assertIn('returned', archive['shots']['A'][0])
                    e.stop()
                finally:
                    if child.poll() is None:
                        child.kill()
                        child.wait(timeout=5)

