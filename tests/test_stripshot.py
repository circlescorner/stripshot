import copy
import io
import json
import queue
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from PIL import Image

from app import create_app
from batch import Engine
from camera import DemoCamera, GPhotoCamera, identity, key
from config import load_config
from printer import Printer
from render import normalize_overlay, render_sheet
from storage import ProcessLock, atomic_bytes, save_json


def eventually(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.03)
    raise AssertionError('Timed out waiting for expected state')


class CountingCamera(DemoCamera):
    def __init__(self, *args):
        super().__init__(*args)
        self.downloads = 0

    def download(self, *args):
        self.downloads += 1
        super().download(*args)


class ApplianceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        cfg = self.root / 'config.json'
        save_json(cfg, {'data_dir': 'data', 'demo': True, 'poll_seconds': .25})
        self.config = load_config(cfg)
        self.engines = []

    def tearDown(self):
        for engine in self.engines:
            engine.stop()
        self.temp.cleanup()

    def engine(self, start=True):
        cards = {c: CountingCamera(self.root / 'cards', c) for c in ('A', 'B')}
        engine = Engine(self.config, cards)
        self.engines.append(engine)
        if start:
            engine.start()
            eventually(lambda: engine.status()['phase'] == 'watching')
        return engine, cards

    def test_no_download_until_eight_from_each_and_only_one_sheet(self):
        engine, cards = self.engine()
        cards['A'].shoot(8)
        cards['B'].shoot(7)
        eventually(lambda: engine.status()['counts'] == {'A': 8, 'B': 7})
        self.assertEqual(sum(c.downloads for c in cards.values()), 0)
        cards['B'].shoot(1)
        eventually(lambda: engine.status()['last'] is not None)
        self.assertEqual(sum(c.downloads for c in cards.values()), 16)
        self.assertEqual(engine.status()['last']['status'], 'dry_run')
        self.assertEqual(engine.status()['counts'], {'A': 0, 'B': 0})
        sheet = engine.root / 'batches' / engine.status()['last']['id'] / 'sheet.png'
        with Image.open(sheet) as img:
            self.assertEqual(img.size, (2400, 1800))
            self.assertAlmostEqual(img.info['dpi'][0], 300, places=1)
        self.assertEqual(len(list((engine.root / 'batches').glob('*/sheet.png'))), 1)

    def test_completed_batch_is_not_reprinted_on_restart(self):
        engine, _ = self.engine()
        engine.request('demo').result(10)
        eventually(lambda: engine.status()['last'] is not None)
        old_id = engine.status()['last']['id']
        engine.stop()
        restarted, cards = self.engine()
        time.sleep(.3)
        self.assertEqual(restarted.status()['last']['id'], old_id)
        self.assertEqual(restarted.status()['counts'], {'A': 0, 'B': 0})
        self.assertEqual(sum(c.downloads for c in cards.values()), 0)

    def test_partial_batch_and_offline_arrivals_survive_restart(self):
        engine, cards = self.engine()
        cards['A'].shoot(3)
        cards['B'].shoot(2)
        eventually(lambda: engine.status()['counts'] == {'A': 3, 'B': 2})
        engine.stop()
        cards['B'].shoot(1)
        restarted, _ = self.engine()
        self.assertEqual(restarted.status()['counts'], {'A': 3, 'B': 3})

    def test_initial_sd_contents_are_baseline_not_new_photos(self):
        engine, cards = self.engine(start=False)
        cards['A'].shoot(8)
        cards['B'].shoot(8)
        engine.start()
        eventually(lambda: engine.status()['phase'] == 'watching')
        self.assertEqual(engine.status()['counts'], {'A': 0, 'B': 0})
        self.assertIsNone(engine.status()['last'])

    def test_reset_keeps_files_and_ignores_duplicate_events(self):
        engine, cards = self.engine()
        cards['A'].shoot(3)
        eventually(lambda: engine.status()['counts']['A'] == 3)
        files = cards['A'].snapshot()
        engine.request('reset').result(10)
        for item in files:
            engine.events.put(('A', item, None))
        time.sleep(.25)
        self.assertEqual(engine.status()['counts'], {'A': 0, 'B': 0})
        self.assertEqual(len(list(cards['A'].directory.glob('*.jpg'))), 3)

    def test_overflow_is_retained_for_next_batch(self):
        engine, cards = self.engine()
        cards['A'].shoot(9)
        cards['B'].shoot(8)
        eventually(lambda: engine.status()['last'] is not None and engine.status()['counts']['A'] == 1)
        self.assertEqual(engine.status()['counts'], {'A': 1, 'B': 0})

    def test_polling_fallback_collects_a_batch(self):
        self.config['camera_mode'] = 'poll'
        engine, _ = self.engine()
        engine.request('demo').result(10)
        eventually(lambda: engine.status()['last'] is not None)
        self.assertEqual(engine.status()['last']['status'], 'dry_run')

    def test_print_timeout_is_never_retried(self):
        engine, _ = self.engine()
        with patch('batch.Printer.submit', side_effect=TimeoutError('spooler timed out')) as submit:
            engine.request('demo').result(10)
            eventually(lambda: engine.status()['phase'] == 'print_uncertain')
            self.assertEqual(submit.call_count, 1)
            engine.stop()
            # Restart resolves the saved intent without calling the printer.
            cards = {c: CountingCamera(self.root / 'cards', c) for c in ('A', 'B')}
            restarted = Engine(self.config, cards)
            self.engines.append(restarted)
            restarted.start()
            eventually(lambda: restarted.status()['phase'] == 'print_uncertain')
            self.assertEqual(submit.call_count, 1)
            restarted.request('acknowledge').result(10)
            self.assertEqual(restarted.status()['last']['status'], 'acknowledged_without_retry')
            self.assertEqual(submit.call_count, 1)

    def test_crash_after_intent_before_submission_holds_batch(self):
        engine, _ = self.engine(start=False)
        engine.state['initialized'] = True
        engine.state['current'] = {'id': 'batch-test', 'stage': 'print_intent'}
        engine.save()
        cards = {c: CountingCamera(self.root / 'cards', c) for c in ('A', 'B')}
        restarted = Engine(self.config, cards)
        self.engines.append(restarted)
        with patch('batch.Printer.submit') as submit:
            restarted.start()
            eventually(lambda: restarted.status()['phase'] == 'print_uncertain')
            submit.assert_not_called()

    def test_invalid_jpeg_prevents_print(self):
        engine, cards = self.engine()
        for c in ('A', 'B'):
            for index in range(8):
                atomic_bytes(cards[c].directory / f'bad{index}.jpg', b'not a jpeg')
        with patch('batch.Printer.submit') as submit:
            eventually(lambda: engine.status()['phase'] == 'error')
            submit.assert_not_called()
        self.assertEqual(engine.status()['current']['stage'], 'preparing')

    def test_missing_pending_file_stops_recovery(self):
        engine, cards = self.engine()
        cards['A'].shoot(2)
        eventually(lambda: engine.status()['counts']['A'] == 2)
        engine.stop()
        next(cards['A'].directory.glob('*.jpg')).unlink()
        restarted, _ = self.engine(start=False)
        restarted.start()
        eventually(lambda: restarted.status()['phase'] == 'error')
        self.assertIn('missing saved batch', restarted.status()['error'])

    def test_corrupt_state_is_not_silently_replaced(self):
        Path(self.config['data_dir']).mkdir()
        path = Path(self.config['data_dir']) / 'state.json'
        path.write_text('{broken')
        with self.assertRaises(json.JSONDecodeError):
            self.engine(start=False)
        self.assertEqual(path.read_text(), '{broken')

    def test_process_lock_rejects_second_owner(self):
        lock = ProcessLock(self.root / 'locked')
        try:
            with self.assertRaises(RuntimeError):
                ProcessLock(self.root / 'locked')
        finally:
            lock.close()

    def test_dashboard_csrf_upload_and_traversal(self):
        engine, _ = self.engine()
        client = create_app(engine).test_client()
        page = client.get('/')
        self.assertEqual(page.status_code, 200)
        import re
        token = re.search(rb'name="stripshot-token" content="([^"]+)"', page.data).group(1).decode()
        self.assertEqual(client.post('/api/reset').status_code, 403)
        self.assertEqual(client.post('/api/reset', headers={'X-Stripshot-Token': token}).status_code, 200)
        image = Image.new('RGBA', (600, 1800), (0, 0, 0, 0))
        buf = io.BytesIO(); image.save(buf, format='PNG'); buf.seek(0)
        response = client.post('/api/overlays/1', data={'file': (buf, '../../escape.png')},
                               headers={'X-Stripshot-Token': token})
        self.assertEqual(response.status_code, 200)
        response = client.get('/overlays/1.png')
        self.assertEqual(response.status_code, 200)
        response.close()
        self.assertEqual(client.get('/batches/not-a-batch/preview.jpg').status_code, 404)
        self.assertFalse((self.root / 'escape.png').exists())

    def test_overlay_dimensions_and_transparency(self):
        for size, mode in [((100, 100), 'RGBA'), ((600, 1800), 'RGB')]:
            buf = io.BytesIO(); Image.new(mode, size, 'white').save(buf, format='PNG')
            with self.assertRaises(ValueError):
                normalize_overlay(buf.getvalue())

    def test_exact_strip_order_and_independent_overlays(self):
        photos = {'A': [], 'B': []}
        colors = {}
        for c in photos:
            for i in range(8):
                color = (20 + 20 * i, 30 if c == 'A' else 180, 100)
                path = self.root / f'{c}{i}.jpg'
                Image.new('RGB', (200, 200), color).save(path, quality=100, subsampling=0)
                photos[c].append(path)
                colors[(c, i)] = color
        overlays = []
        for i in range(4):
            image = Image.new('RGBA', (600, 1800), (0, 0, 0, 0))
            image.putpixel((0, 0), (i * 60, 0, 0, 255))
            path = self.root / f'overlay{i}.png'; image.save(path); overlays.append(path)
        output = self.root / 'sheet.png'
        layout = {'margin': 0, 'gap': 0, 'top': 0, 'bottom': 0}
        render_sheet(photos, overlays, layout, output)
        with Image.open(output) as img:
            for strip in range(4):
                self.assertEqual(img.getpixel((strip * 600, 0)), (strip * 60, 0, 0))
                for row, (c, n) in enumerate((('A', strip*2), ('B', strip*2), ('A', strip*2+1), ('B', strip*2+1))):
                    actual = img.getpixel((strip*600+300, row*450+225))
                    self.assertTrue(all(abs(a-b) <= 2 for a, b in zip(actual, colors[(c, n)])))

    def test_cups_single_submission_and_explicit_queue(self):
        config = {'enabled': True, 'queue': 'DS40', 'options': {'media': 'Test6x8'}}
        with patch('printer.subprocess.run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = 'request id is DS40-42 (1 file(s))\n'
            run.return_value.stderr = ''
            result = Printer(config).submit(self.root / 'sheet.png', 'batch-test')
            self.assertEqual(result, {'status': 'submitted', 'job_id': 'DS40-42'})
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][:5], ['lp', '-d', 'DS40', '-n', '1'])

    def test_demo_cannot_enable_printer(self):
        path = self.root / 'unsafe.json'
        save_json(path, {'demo': True, 'printer': {'enabled': True, 'queue': 'DS40'}})
        with self.assertRaises(ValueError):
            load_config(path)

    def test_preparation_recovers_after_restart(self):
        engine, cards = self.engine(start=False)
        for c in ('A', 'B'):
            cards[c].shoot(8)
            files = cards[c].snapshot()
            engine.state['pending'][c] = files
            engine.state['seen'][c] = [key(i) for i in files]
        engine.state['initialized'] = True
        engine.freeze()  # Simulate a process exit after freezing, before download.
        expected = engine.state['current']['id']
        restarted, _ = self.engine()
        eventually(lambda: restarted.status()['last'] is not None)
        self.assertEqual(restarted.status()['last']['id'], expected)

    def test_batch_freezes_overlay_and_printer_configuration(self):
        engine, _ = self.engine(start=False)
        overlay = Image.new('RGBA', (600, 1800), (100, 40, 30, 100))
        buf = io.BytesIO(); overlay.save(buf, format='PNG')
        engine.action('overlay', 1, buf.getvalue())
        for c in ('A', 'B'):
            engine.state['pending'][c] = [identity('/', f'{n}.jpg', 100, n) for n in range(8)]
        engine.freeze()
        batch = copy.deepcopy(engine.state['current'])
        engine.config['printer']['enabled'] = True
        replacement = io.BytesIO()
        Image.new('RGBA', (600, 1800), (0, 0, 0, 0)).save(replacement, format='PNG')
        engine.action('overlay', 1, replacement.getvalue())
        self.assertFalse(batch['printer']['enabled'])
        self.assertEqual((engine.root / 'batches' / batch['id'] / 'overlay1.png').read_bytes(), buf.getvalue())

    def test_live_camera_download_checks_identity_and_size(self):
        camera = GPhotoCamera('usb:001,002', 'serial')
        camera.camera = MagicMock()
        camera.gp = MagicMock()
        camera.camera.file_get_info.return_value.file.size = 3
        camera.camera.file_get_info.return_value.file.mtime = 42
        item = identity('/store/DCIM', 'A.JPG', 3, 42)
        camera.camera.file_get.return_value.get_data_and_size.return_value = b'abc'
        camera.download(item, self.root / 'download.jpg')
        self.assertEqual((self.root / 'download.jpg').read_bytes(), b'abc')
        camera.camera.file_get.return_value.get_data_and_size.return_value = b'ab'
        with self.assertRaisesRegex(RuntimeError, 'Incomplete'):
            camera.download(item, self.root / 'short.jpg')
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            camera.download({**item, 'size': 4}, self.root / 'changed.jpg')
        self.assertFalse((self.root / 'short.jpg').exists())

    def test_live_camera_ignores_non_file_and_raw_events(self):
        camera = GPhotoCamera('usb:001,002', 'serial')
        camera.camera = MagicMock()
        camera.gp = MagicMock(GP_EVENT_FILE_ADDED=2)
        camera.camera.wait_for_event.return_value = (0, None)
        self.assertIsNone(camera.event())
        camera.camera.wait_for_event.return_value = (2, type('File', (), {'folder': '/', 'name': 'photo.NEF'})())
        self.assertIsNone(camera.event())
        camera.camera.file_get.assert_not_called()

    def test_camera_failure_holds_collection(self):
        engine, cards = self.engine()
        engine.workers['A'].failure = 'USB disconnected'
        eventually(lambda: engine.status()['phase'] == 'error')
        self.assertIn('restart', engine.status()['error'])
        self.assertIsNone(engine.status()['last'])


if __name__ == '__main__':
    unittest.main()
