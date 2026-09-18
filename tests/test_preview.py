import io
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from PIL import Image
from app import create_app
from batch import Engine
from camera import GPhotoCamera, CameraWorker, DemoCamera
from config import load_config
from storage import save_json
from test_stripshot import eventually
import queue


def jpeg():
    output = io.BytesIO()
    Image.new('RGB', (32, 24), 'red').save(output, 'JPEG')
    return output.getvalue()


class PreviewTests(unittest.TestCase):
    def test_appliance_monitor_policy_allows_cached_blob_frames(self):
        engine = MagicMock()
        engine.config = {'demo': False}
        engine.workers = {'A': MagicMock(), 'B': MagicMock()}
        for worker in engine.workers.values():
            worker.latest_frame.return_value = jpeg()
        client = create_app(engine).test_client()
        for label in ('A', 'B'):
            response = client.get('/view/' + label)
            self.assertEqual(response.status_code, 200)
            directives = dict(part.strip().split(' ', 1) for part in
                              response.headers['Content-Security-Policy'].split(';'))
            self.assertEqual(set(directives['img-src'].split()), {"'self'", 'blob:'})
            self.assertEqual(directives['script-src'], "'self'")
            frame = client.get('/api/preview/' + label + '.jpg')
            self.assertEqual(frame.status_code, 200)
            self.assertEqual(frame.mimetype, 'image/jpeg')
            self.assertEqual(frame.data, jpeg())

    def test_preview_keeps_camera_file_alive_until_bytes_are_copied(self):
        expected = jpeg()

        class BorrowedCameraFile:
            def __init__(self):
                self.buffer = bytearray(expected)

            def get_data_and_size(self):
                return memoryview(self.buffer)

            def __del__(self):
                # Model libgphoto invalidating the borrowed memory on release.
                self.buffer[:] = b'\x00' * len(self.buffer)

        camera = GPhotoCamera('test', 'serial')
        camera.camera = MagicMock()
        camera.camera.capture_preview.side_effect = BorrowedCameraFile
        camera.camera.get_single_config.return_value.get_value.return_value = 1
        camera._media = MagicMock(return_value='Card')
        camera._set = MagicMock()
        self.assertEqual(camera.start_preview(), expected)
        self.assertEqual(camera.preview(), expected)

    def test_preview_only_diagnostic_skips_sd_scan(self):
        adapter = MagicMock()
        adapter.snapshot.side_effect = AssertionError('Unexpected SD scan')
        adapter.start_preview.return_value = jpeg()
        adapter.event.side_effect = lambda: time.sleep(.01)
        worker = CameraWorker('A', adapter, queue.Queue(), preview_fps=1,
                              baseline_required=False)
        worker.start()
        try:
            self.assertEqual(worker.ready.result(timeout=2), [])
            self.assertIsNotNone(worker.latest_frame())
            adapter.snapshot.assert_not_called()
        finally:
            worker.stopping.set()
            worker.join(timeout=2)

    def test_card_is_restored_even_if_first_preview_fails(self):
        camera = GPhotoCamera('test', 'serial')
        camera.camera = MagicMock()
        camera._media = MagicMock(return_value='Card')
        camera._set = MagicMock()
        camera.camera.capture_preview.side_effect = RuntimeError('USB error')
        with self.assertRaisesRegex(RuntimeError, 'USB error'):
            camera.start_preview()
        camera._set.assert_called_with('recordingmedia', 'Card')
        camera.camera.capture.assert_not_called()

    def test_startup_cannot_report_ready_if_card_restore_fails(self):
        camera = GPhotoCamera('test', 'serial')
        camera.camera = MagicMock()
        camera.camera.capture_preview.return_value.get_data_and_size.return_value = jpeg()
        camera._media = MagicMock(side_effect=['Card', 'SDRAM'])
        camera._set = MagicMock()
        with self.assertRaisesRegex(RuntimeError, 'restore Card'):
            camera.start_preview()

    def test_stopped_liveview_does_not_silently_restart_into_sdram(self):
        camera = GPhotoCamera('test', 'serial')
        camera.camera = MagicMock()
        camera.camera.get_single_config.return_value.get_value.return_value = 0
        with self.assertRaisesRegex(RuntimeError, 'ended live view'):
            camera.preview()
        camera.camera.capture_preview.assert_not_called()

    def test_media_change_during_preview_is_a_failure(self):
        camera = GPhotoCamera('test', 'serial')
        camera.camera = MagicMock()
        camera.camera.get_single_config.return_value.get_value.return_value = 1
        camera.camera.capture_preview.return_value.get_data_and_size.return_value = jpeg()
        camera._media = MagicMock(side_effect=['Card', 'SDRAM'])
        with self.assertRaisesRegex(RuntimeError, 'changed recording destination'):
            camera.preview()

    def test_cleanup_restores_card_and_exits_even_when_end_liveview_fails(self):
        camera = GPhotoCamera('test', 'serial')
        camera.camera = MagicMock()
        camera.preview_started = True
        camera._media = MagicMock(return_value='Card')
        camera._set = MagicMock(side_effect=[RuntimeError('end failed'), None])
        with self.assertRaisesRegex(RuntimeError, 'end failed'):
            camera.close()
        self.assertEqual(camera._set.call_args.args, ('recordingmedia', 'Card'))
        camera.camera.exit.assert_called_once()

    def test_stale_failed_and_stopped_frames_are_not_served(self):
        worker = CameraWorker('A', MagicMock(), queue.Queue(), preview_fps=3)
        data = jpeg()
        worker.publish_frame(data)
        self.assertEqual(worker.latest_frame(), data)
        worker.frame_at = time.monotonic() - 3
        self.assertIsNone(worker.latest_frame())
        worker.publish_frame(data)
        worker.failure = 'disconnected'
        self.assertIsNone(worker.latest_frame())
        worker.failure = None
        worker.stopping.set()
        self.assertIsNone(worker.latest_frame())

    def test_http_clients_share_cache_and_batch_processing_still_works(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'config.json'
            save_json(config, {'data_dir': 'data', 'demo': True, 'preview_fps': 3})
            engine = Engine(load_config(config), {c: DemoCamera(root / 'cards', c) for c in ('A', 'B')})
            engine.start()
            try:
                eventually(lambda: engine.status()['phase'] == 'watching')
                client = create_app(engine).test_client()
                self.assertEqual(client.get('/view/A').status_code, 200)
                self.assertEqual(client.get('/view/C').status_code, 404)
                for _ in range(10):
                    response = client.get('/api/preview/A.jpg')
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.mimetype, 'image/jpeg')
                    self.assertEqual(response.headers['Cache-Control'], 'no-store')
                engine.request('demo').result(10)
                eventually(lambda: engine.status()['last'] is not None)
                self.assertEqual(engine.status()['last']['status'], 'dry_run')
                eventually(lambda: client.get('/api/preview/A.jpg').status_code == 200)
                engine.workers['A'].failure = 'unplugged'
                self.assertEqual(client.get('/api/preview/A.jpg').status_code, 503)
            finally:
                engine.stop()

    def test_invalid_rates_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            for fps in [-1, .1, 16, True, '3', float('nan')]:
                save_json(path, {'demo': True, 'preview_fps': fps})
                with self.assertRaises(ValueError):
                    load_config(path)
