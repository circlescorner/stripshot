import queue
import threading
import unittest
from unittest.mock import MagicMock
from camera import CameraWorker, GPhotoCamera, identity

class ScanTests(unittest.TestCase):
    def adapter(self):
        a = GPhotoCamera('test', 'serial')
        a.camera = MagicMock()
        a.camera.folder_list_files.side_effect = lambda f: [('a.JPG', None), ('ignore.NEF', None)] if f == '/DCIM' else []
        a.camera.folder_list_folders.side_effect = lambda f: [('DCIM', None)] if f == '/' else []
        a.camera.file_get_info.return_value.file.size = 123
        a.camera.file_get_info.return_value.file.mtime = 456
        return a

    def test_trace_preserves_identity(self):
        a = self.adapter()
        trace = []
        a.scan_trace = trace.append
        self.assertEqual(a.snapshot(), [identity('/DCIM', 'a.JPG', 123, 456)])
        self.assertEqual(len(trace), 10)
        for start, done in zip(trace[::2], trace[1::2]):
            self.assertEqual(start['state'], 'start')
            self.assertEqual(done['state'], 'done')
            self.assertEqual(start['sequence'], done['sequence'])
            self.assertGreaterEqual(done['duration'], 0)
        a.camera.file_get_info.assert_called_once_with('/DCIM', 'a.JPG')

    def test_metadata_failure_rejects_baseline(self):
        a = self.adapter()
        a.camera.file_get_info.side_effect = RuntimeError('metadata failed')
        with self.assertRaisesRegex(RuntimeError, 'metadata failed'):
            a.snapshot()
        self.assertEqual(a.scan_progress['operation'], 'file_get_info')
        self.assertEqual(a.scan_progress['state'], 'error')
        self.assertEqual(a.scan_progress['arguments'], ['/DCIM', 'a.JPG'])

    def test_stall_visible_and_stop_prevents_preview(self):
        a = self.adapter()
        a.open, a.close, a.start_preview = MagicMock(), MagicMock(), MagicMock()
        entered, release = threading.Event(), threading.Event()
        def blocked(folder):
            entered.set()
            release.wait(2)
            return []
        a.camera.folder_list_files.side_effect = blocked
        w = CameraWorker('A', a, queue.Queue(), preview_fps=3)
        w.start()
        try:
            self.assertTrue(entered.wait(1))
            self.assertEqual(a.scan_progress['state'], 'start')
            self.assertEqual(a.scan_progress['operation'], 'folder_list_files')
            w.stopping.set()
        finally:
            release.set()
            w.join(2)
        self.assertFalse(w.is_alive())
        with self.assertRaisesRegex(RuntimeError, 'baseline incomplete'):
            w.ready.result()
        a.start_preview.assert_not_called()
        a.close.assert_called_once()
