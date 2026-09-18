import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from camera import identity
from software_probe import SoftwareProbeCamera

class SoftwareProbeTests(unittest.TestCase):
    def setup_probe(self):
        a = SoftwareProbeCamera('port', 'serial')
        native = MagicMock()
        a.camera = native
        a.gp = SimpleNamespace(GP_CAPTURE_IMAGE=0)
        values = {'viewfinder': 1, 'capturetarget': 'Internal RAM', 'recordingmedia': 'Card'}
        native.get_single_config.side_effect = lambda name: SimpleNamespace(get_value=lambda: values[name])
        a._set = MagicMock(side_effect=lambda name, value: values.__setitem__(name, value))
        a._media = lambda: values['recordingmedia']
        native.capture.return_value = SimpleNamespace(folder='/DCIM', name='new.NEF')
        a.close = MagicMock()
        a.open = MagicMock(side_effect=lambda: setattr(a, 'camera', native))
        a.snapshot = MagicMock(return_value=[identity('/DCIM', 'new.JPG', 100, 20)])
        a.download = MagicMock()
        a.start_preview = MagicMock(return_value=b'frame')
        return a, native, values

    @patch('software_probe.validate_jpeg')
    def test_one_capture_persists_and_resumes(self, validate):
        a, native, values = self.setup_probe()
        events = []
        self.assertEqual(a.software_probe([], Path('out.jpg'), lambda e, d: events.append(e)), b'frame')
        native.capture.assert_called_once_with(0)
        self.assertEqual(values['capturetarget'], 'Internal RAM')
        self.assertEqual(events, ['capture_intent', 'capture_returned', 'new_card_jpegs', 'download_verified', 'preview_restarted'])
        a.close.assert_called_once()
        a.open.assert_called_once()
        a.download.assert_called_once()
        validate.assert_called_once()

    def test_uncertain_capture_not_retried(self):
        a, native, values = self.setup_probe()
        native.capture.side_effect = RuntimeError('timeout')
        with self.assertRaisesRegex(RuntimeError, 'timeout'):
            a.software_probe([], Path('out.jpg'), MagicMock())
        native.capture.assert_called_once()
        a.start_preview.assert_not_called()
        self.assertEqual(values['capturetarget'], 'Internal RAM')

    def test_destination_must_be_verified(self):
        a, native, values = self.setup_probe()
        a._set.side_effect = lambda n, v: values.__setitem__(n, v) if n != 'capturetarget' else None
        with self.assertRaisesRegex(RuntimeError, 'destination'):
            a.software_probe([], Path('out.jpg'), MagicMock())
        native.capture.assert_not_called()

    def test_wrong_file_rejected(self):
        a, native, _ = self.setup_probe()
        a.snapshot.return_value = [identity('/DCIM', 'other.JPG', 100, 20)]
        with self.assertRaisesRegex(RuntimeError, 'does not match'):
            a.software_probe([], Path('out.jpg'), MagicMock())
        a.download.assert_not_called()
        a.start_preview.assert_not_called()

    def test_cancel_prevents_shutter(self):
        a, native, _ = self.setup_probe()
        a.scan_cancelled = lambda: True
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            a.software_probe([], Path('out.jpg'), MagicMock())
        native.capture.assert_not_called()

    @patch('software_probe.validate_jpeg')
    def test_cycle_shot_downloads_and_resumes_without_full_scan(self, validate):
        a, native, _ = self.setup_probe()
        native.capture.return_value.name = 'new.JPG'
        item = identity('/DCIM', 'new.JPG', 100, 20)
        a.describe = MagicMock(return_value=item)
        self.assertEqual(a.cycle_shot([], Path('out.jpg'), MagicMock()), (item, b'frame'))
        native.capture.assert_called_once()
        a.snapshot.assert_not_called()
        a.close.assert_not_called()
        a.download.assert_called_once_with(item, Path('out.jpg'))

    def test_cycle_rejects_duplicate_capture(self):
        a, native, _ = self.setup_probe()
        native.capture.return_value.name = 'new.JPG'
        item = identity('/DCIM', 'new.JPG', 100, 20)
        a.describe = MagicMock(return_value=item)
        with self.assertRaisesRegex(RuntimeError, 'already known'):
            a.cycle_shot([item], Path('out.jpg'), MagicMock())
        a.download.assert_not_called()
        native.capture.assert_called_once()

    def test_cycle_final_audit_requires_exact_eight_identities(self):
        a, native, _ = self.setup_probe()
        captured = [identity('/DCIM', f'{n}.JPG', 100, n) for n in range(8)]
        a.snapshot.return_value = captured
        self.assertEqual(a.verify_cycle([], captured, MagicMock()), b'frame')
        a.open.assert_called_once()
        native.capture.assert_not_called()
        a.start_preview.reset_mock()
        a.snapshot.return_value = captured[:-1] + [identity('/DCIM', '7.JPG', 101, 7)]
        with self.assertRaisesRegex(RuntimeError, 'exact eight'):
            a.verify_cycle([], captured, MagicMock())
        a.start_preview.assert_not_called()

    def test_cycle_final_audit_rejects_extra_file(self):
        a, _, _ = self.setup_probe()
        captured = [identity('/DCIM', f'{n}.JPG', 100, n) for n in range(8)]
        a.snapshot.return_value = captured + [identity('/DCIM', 'extra.JPG', 100, 9)]
        with self.assertRaisesRegex(RuntimeError, 'exact eight'):
            a.verify_cycle([], captured, MagicMock())

    def test_fast_verification_never_scans_or_reopens(self):
        a, native, _ = self.setup_probe()
        captured = [identity('/DCIM', f'{n}.JPG', 100, n) for n in range(8)]
        a.describe = MagicMock(side_effect=captured)
        a.preview = MagicMock(return_value=b'frame')
        self.assertEqual(a.verify_cycle([], captured, MagicMock(), False), b'frame')
        self.assertEqual(a.describe.call_count, 8)
        a.snapshot.assert_not_called()
        a.close.assert_not_called()
        a.open.assert_not_called()
        native.capture.assert_not_called()

    def test_fast_verification_rejects_changed_identity(self):
        a, _, _ = self.setup_probe()
        captured = [identity('/DCIM', f'{n}.JPG', 100, n) for n in range(8)]
        a.describe = MagicMock(return_value=identity('/DCIM', '0.JPG', 101, 0))
        with self.assertRaisesRegex(RuntimeError, 'identity changed'):
            a.verify_cycle([], captured, MagicMock(), False)
