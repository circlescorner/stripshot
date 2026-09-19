import copy
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from batch import Engine
from camera import DemoCamera, key
from config import load_config
from storage import save_json
from test_stripshot import eventually


class SoftwareCamera(DemoCamera):
    def __init__(self, *args):
        super().__init__(*args)
        self.shutters = self.downloads = 0
        self.fail_at = None

    def snapshot(self):
        raise AssertionError('Software mode must never scan historical SD files')

    def event(self):
        raise AssertionError('Software mode must not ingest unrelated camera events')

    def download(self, *args):
        self.downloads += 1
        return super().download(*args)

    def software_shot(self, known, path, record, preview):
        def audited(event, data):
            record(event, data)
            saved = json.loads((path.parents[2] / 'state.json').read_text())
            slot = saved['current']['shots'][self.label][int(path.stem[1:]) - 1]
            if event == 'capture_intent':
                assert slot['intent']['count'] == 1  # Durable before fake shutter.
                self.shutters += 1
            if event == self.fail_at:
                raise RuntimeError('Injected disconnect at ' + event)
        return super().software_shot(known, path, audited, preview)


class SoftwareAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cfgpath = self.root / 'config.json'
        save_json(self.cfgpath, {'demo': True, 'camera_mode': 'software'})
        self.cfg = load_config(self.cfgpath)
        self.engines = []
        from printer_quality import QUALITY_CONTEXT, QUALITY_FIELDS, QUALITY_VALUES
        choices = {k:{v} for k,v in QUALITY_CONTEXT.items()}
        choices.update({k:set(QUALITY_VALUES) for k in QUALITY_FIELDS})
        self.driver_patch = patch('printer_quality.driver_choices',return_value=choices)
        self.driver_patch.start()
        self.addCleanup(self.driver_patch.stop)

    def tearDown(self):
        for e in self.engines:
            e.stop()
        self.temp.cleanup()

    def engine(self, start=True, phase='watching'):
        cards = {c: SoftwareCamera(self.root / 'cards', c) for c in ('A', 'B')}
        e = Engine(copy.deepcopy(self.cfg), cards)
        self.engines.append(e)
        if start:
            e.start()
            eventually(lambda: e.status()['phase'] == phase)
        return e, cards

    def test_two_batches_exact_sixteen_no_scans_and_restart_no_shutters(self):
        e, cards = self.engine()
        for n in (1, 2):
            old = e.status()['last']
            e.request('capture').result(5)
            eventually(lambda: e.status()['last'] is not None and e.status()['last'] != old)
            last = e.status()['last']
            self.assertEqual(last['status'], 'dry_run')
            self.assertTrue((e.root / 'batches' / last['id'] / 'sheet.png').exists())
            for c in cards:
                self.assertEqual(cards[c].shutters, 8*n)
                self.assertEqual(cards[c].downloads, 8*n)
                self.assertEqual(len({key(i) for i in last['files'][c]}), 8)
                self.assertEqual(len(list(cards[c].directory.glob('*.jpg'))), 8*n)
        e.request('reset').result(5)
        e.stop()
        restarted, cards = self.engine()
        time.sleep(.2)
        self.assertEqual(sum(c.shutters for c in cards.values()), 0)
        self.assertEqual(restarted.status()['last']['id'], last['id'])

    def test_uncertain_shutter_holds_across_restart_and_cannot_resume(self):
        e, cards = self.engine()
        cards['A'].fail_at = 'capture_intent'
        e.request('capture').result(5)
        eventually(lambda: e.status()['phase'] == 'capture_held')
        eventually(lambda: all(f.done() for f in e.capture_futures))
        self.assertEqual(cards['A'].shutters, 1)
        e.stop()
        restarted, cards = self.engine(phase='capture_held')
        with self.assertRaisesRegex(ValueError, 'Uncertain shutter'):
            restarted.request('resume_capture').result(5)
        self.assertEqual(sum(c.shutters for c in cards.values()), 0)
        batchid = restarted.status()['current']['id']
        restarted.request('abandon_capture').result(5)
        archive = json.loads((restarted.root / 'batches' / batchid / 'manifest.json').read_text())
        self.assertEqual(archive['stage'], 'abandoned')
        self.assertIn('intent_at', archive['shots']['A'][0])

    def test_returned_path_without_identity_cannot_be_replaced(self):
        e, cards = self.engine()
        cards['A'].fail_at = 'capture_returned'
        e.request('capture').result(5)
        eventually(lambda: e.status()['phase'] == 'capture_held')
        e.stop()
        restarted, cards = self.engine(phase='capture_held')
        self.assertIn('returned', restarted.status()['current']['shots']['A'][0])
        with self.assertRaises(ValueError):
            restarted.request('resume_capture').result(5)
        self.assertEqual(cards['A'].shutters, 0)

    def test_known_identity_resumes_download_without_duplicate_shutter(self):
        e, cards = self.engine()
        cards['A'].fail_at = 'identified'
        e.request('capture').result(5)
        eventually(lambda: e.status()['phase'] == 'capture_held')
        e.stop()
        restarted, newcards = self.engine(phase='capture_held')
        self.assertEqual(newcards['A'].shutters, 0)
        restarted.request('resume_capture').result(5)
        eventually(lambda: restarted.status()['last'] is not None)
        for c in cards:
            self.assertEqual(cards[c].shutters + newcards[c].shutters, 8)
            self.assertEqual(len(list(cards[c].directory.glob('*.jpg'))), 8)

    def test_changed_saved_identity_prevents_resumption(self):
        e, cards = self.engine()
        cards['A'].fail_at = 'identified'
        e.request('capture').result(5)
        eventually(lambda: e.status()['phase'] == 'capture_held')
        e.stop()
        next(cards['A'].directory.glob('*.jpg')).write_bytes(b'changed')
        restarted, newcards = self.engine(phase='capture_held')
        restarted.request('resume_capture').result(5)
        eventually(lambda: restarted.status()['phase'] == 'capture_held')
        self.assertIn('identity changed', restarted.status()['error'])
        self.assertEqual(sum(c.shutters for c in newcards.values()), 0)

    def test_preview_between_every_pair(self):
        self.cfg['preview_fps'] = 5
        e, _ = self.engine()
        e.request('capture').result(5)
        eventually(lambda: e.status()['last'] is not None)
        for c in ('A', 'B'):
            for shot in e.status()['last']['shots'][c]:
                self.assertGreaterEqual(shot['preview_frames'], 3)
            self.assertIsNotNone(e.workers[c].latest_frame())

    def test_existing_external_state_not_reinterpreted(self):
        e, _ = self.engine(start=False)
        e.state['binding'].pop('capture_mode')
        e.save()
        with self.assertRaisesRegex(ValueError, 'different cameras/mode'):
            self.engine(start=False)

    def test_printing_blocked_even_if_config_bypassed(self):
        self.cfg['printer']['enabled'] = True
        with self.assertRaisesRegex(ValueError, 'printing remains disabled'):
            self.engine(start=False)

    def test_software_config_rejects_printing(self):
        save_json(self.cfgpath, {'camera_mode': 'software', 'demo': False,
                  'cameras': {'A': {'serial': '1'}, 'B': {'serial': '2'}},
                  'printer': {'enabled': True, 'queue': 'DS40'}})
        with self.assertRaisesRegex(ValueError, 'qualification'):
            load_config(self.cfgpath)

    def test_active_batch_cannot_start_second_sequence(self):
        e, _ = self.engine(start=False)
        e.phase = 'watching'
        e.action('capture')
        with self.assertRaises(ValueError):
            e.action('capture')
        with self.assertRaises(ValueError):
            e.action('reset')

    def test_dashboard_starts_software_batch_with_csrf_protection(self):
        import re
        from app import create_app
        e, _ = self.engine()
        client = create_app(e).test_client()
        page = client.get('/')
        self.assertIn(b'id="capture"', page.data)
        self.assertNotIn(b'id="demo"', page.data)
        token = re.search(rb'name="stripshot-token" content="([^"]+)"', page.data).group(1).decode()
        self.assertEqual(client.post('/api/capture').status_code, 403)
        response = client.post('/api/capture', headers={'X-Stripshot-Token': token})
        self.assertEqual(response.status_code, 200)
        eventually(lambda: e.status()['last'] is not None)
        status = client.get('/api/status').get_json()
        self.assertEqual(status['capture_mode'], 'software')
        self.assertFalse(status['printing_enabled'])
        self.assertEqual(len(status['last']['files']['A']), 8)
        self.assertIn('recent_fps', status['previews']['A'])

    def test_failed_intent_save_prevents_shutter(self):
        from test_software_probe import SoftwareProbeTests
        adapter, native, _ = SoftwareProbeTests().setup_probe()
        e, _ = self.engine(start=False)
        e.freeze(software=True)
        with patch.object(e, 'save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                adapter._capture_once(lambda event, data: e.software_record('A', 0, event, data))
        native.capture.assert_not_called()

    def test_corrupt_local_download_recovers_exact_file_without_new_shutter(self):
        e, cards = self.engine()
        cards['A'].fail_at = 'downloaded'
        e.request('capture').result(5)
        eventually(lambda: e.status()['phase'] == 'capture_held')
        e.stop()
        batchid = e.status()['current']['id']
        (e.root / 'batches' / batchid / 'A01.jpg').write_bytes(b'corrupt local copy')
        restarted, newcards = self.engine(phase='capture_held')
        restarted.request('resume_capture').result(5)
        eventually(lambda: restarted.status()['last'] is not None)
        self.assertEqual(cards['A'].shutters + newcards['A'].shutters, 8)
        self.assertEqual(newcards['A'].downloads, 8)

    def test_recovered_preparation_never_submits_enabled_saved_printer(self):
        e, _ = self.engine(start=False)
        e.freeze(software=True)
        e.state['current']['stage'] = 'preparing'
        e.state['current']['printer']['enabled'] = True
        with patch('batch.Printer.submit') as submit:
            with self.assertRaisesRegex(RuntimeError, 'cannot enable'):
                e.process()
            submit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
