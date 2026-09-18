"""Simulated recovery and rendering checks: no native exposures or printing."""
import copy
import sys
import threading
import time
import unittest
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from PIL import Image
from app import create_app
from camera import GPhotoCamera
from printer import Printer
from render import DEFAULT_PHOTO_ORDER, render_sheet, validate_layout
import test_software_app
from test_stripshot import eventually


class RecoveryOrderingTests(unittest.TestCase):
    setUp = test_software_app.SoftwareAppTests.setUp
    tearDown = test_software_app.SoftwareAppTests.tearDown
    engine = test_software_app.SoftwareAppTests.engine

    def test_order_frozen_persistent_and_legacy_default(self):
        e, _ = self.engine(start=False)
        legacy = copy.deepcopy(e.layout)
        validate_layout(legacy)
        order = list(reversed(copy.deepcopy(DEFAULT_PHOTO_ORDER)))
        layout = {**legacy, 'photo_order': order}
        e.action('layout', layout)
        e.freeze(software=True)
        e.action('layout', {**legacy, 'photo_order': DEFAULT_PHOTO_ORDER})
        restarted, _ = self.engine(start=False)
        self.assertEqual(restarted.state['current']['layout']['photo_order'], order)
        self.assertEqual(restarted.layout['photo_order'], DEFAULT_PHOTO_ORDER)
        bad = copy.deepcopy(order); bad[0][0] = bad[0][1]
        for value in (bad, [], [[None]*4]*4, [['A9']*4]*4):
            with self.assertRaises(ValueError):
                e.action('layout', {**legacy, 'photo_order': value})
        self.assertEqual(e.layout['photo_order'], DEFAULT_PHOTO_ORDER)

    def test_pixels_follow_custom_order_and_legacy_order(self):
        e, _ = self.engine(start=False)
        photos = {'A': [], 'B': []}; colors = {}
        for c in photos:
            for n in range(1, 9):
                color = (n*25, 30 if c == 'A' else 190, 50)
                path = self.root / f'{c}{n}.jpg'
                Image.new('RGB', (120,120), color).save(path)
                photos[c].append(path); colors[f'{c}{n}'] = color
        for order in (None, [list(reversed(s)) for s in reversed(DEFAULT_PHOTO_ORDER)]):
            layout = {'margin':0,'top':0,'bottom':0,'gap':0}
            if order is not None: layout['photo_order'] = order
            path = self.root / 'sheet.png'
            render_sheet(photos, [None]*4, layout, path)
            with Image.open(path) as im:
                for i, strip in enumerate(order or DEFAULT_PHOTO_ORDER):
                    for j, photo in enumerate(strip):
                        self.assertTrue(all(abs(a-b) <= 3 for a,b in zip(im.getpixel((i*600+300,j*450+225)), colors[photo])))

    def test_held_uncertain_batch_reconnect_never_issues_shutter(self):
        e, cards = self.engine()
        cards['A'].fail_at = 'capture_intent'
        e.request('capture').result(5)
        eventually(lambda: e.reconnect_available())
        frozen = copy.deepcopy(e.state['current'])
        before = {c:a.shutters for c,a in cards.items()}
        cards['A'].fail_at = None
        e.request('reconnect').result(5)
        eventually(lambda: e.phase == 'capture_held' and not e.workers['A'].failure)
        self.assertEqual(e.state['current'], frozen)
        self.assertEqual({c:a.shutters for c,a in cards.items()}, before)
        with self.assertRaisesRegex(ValueError, 'Uncertain shutter'):
            e.request('resume_capture').result(5)

    def test_reconnect_refuses_alive_cleanup_error_and_pending_capture(self):
        e, _ = self.engine()
        old = e.workers['A']; old.stopping.set(); old.join(2)
        old.failure = 'disconnected'; e.phase = 'error'
        self.assertTrue(e.reconnect_available())
        old.cleanup_error = 'release unconfirmed'
        self.assertFalse(e.reconnect_available())
        old.cleanup_error = None
        with patch.object(old, 'is_alive', return_value=True):
            self.assertFalse(e.reconnect_available())
        e.capture_futures = [Future()]
        self.assertFalse(e.reconnect_available())
        e.capture_futures[0].set_result(None)
        with patch.object(e.workers['B'], 'ready', Future()):
            self.assertFalse(e.reconnect_available())
        e.phase = 'print_uncertain'
        self.assertFalse(e.reconnect_available())

    def test_idle_recovery_no_scan_no_shutter(self):
        e, cards = self.engine()
        old = e.workers['A']; old.stopping.set(); old.join(2)
        old.failure = 'disconnected'; e.reconnect_next_at = 0
        eventually(lambda: e.workers['A'] is not old and e.phase == 'watching')
        self.assertEqual(sum(a.shutters for a in cards.values()), 0)

    def test_branding_favicon_and_404_url_logging(self):
        e, _ = self.engine(start=False)
        app = create_app(e); client = app.test_client()
        for url in ('/kiosk', '/view/A', '/view/B'):
            self.assertIn(b'MalanaphyVickWedding', client.get(url).data)
        self.assertEqual(client.get('/favicon.ico').status_code, 204)
        with self.assertLogs(app.logger, level='WARNING') as logged:
            self.assertEqual(client.get('/missing-image.jpg').status_code, 404)
        self.assertIn('GET /missing-image.jpg', '\n'.join(logged.output))


class NativeRecoveryTests(unittest.TestCase):
    def test_reenumeration_checks_serial_and_skips_healthy_port(self):
        opened = []
        class Native:
            def set_port_info(self, port): self.port = port
            def init(self): opened.append(self.port)
            def get_single_config(self, name):
                return SimpleNamespace(get_value=lambda: {'wrong':'other','right':'expected'}[self.port])
            def exit(self): pass
        factory = MagicMock(side_effect=Native)
        factory.autodetect.return_value = [('Nikon D3300', p) for p in ('healthy','wrong','right')]
        ports = MagicMock(); ports.lookup_path.side_effect = lambda p:p; ports.__getitem__.side_effect = lambda p:p
        gp = SimpleNamespace(Camera=factory, PortInfoList=lambda: ports)
        with patch.dict(sys.modules, {'gphoto2':gp}):
            a = GPhotoCamera(None, 'expected', ['healthy']); a.open()
        self.assertEqual(opened, ['wrong','right'])
        self.assertEqual(a.port, 'right')

    def test_keepalive_only_restarts_viewfinder_and_checks_card(self):
        a = GPhotoCamera('port','serial'); a.camera = MagicMock()
        a.camera.get_single_config.return_value.get_value.return_value = 0
        a._media = MagicMock(return_value='Card')
        a.start_preview = MagicMock(return_value=b'jpeg')
        self.assertEqual(a.keepalive_preview(), b'jpeg')
        a.camera.capture.assert_not_called()
        a.keepalive_next_at = 0
        a._media.return_value = 'SDRAM'
        with self.assertRaises(RuntimeError): a.keepalive_preview()
        a.start_preview.assert_called_once()

    def test_slow_printer_poll_shared_without_blocking_http(self):
        p = Printer({'enabled':True})
        release = threading.Event(); entered = threading.Event()
        def slow(): entered.set(); release.wait(3); return 'idle'
        with patch.object(p, 'status', side_effect=slow) as poll:
            try:
                started = time.monotonic()
                for _ in range(20): p.cached_status()
                self.assertLess(time.monotonic()-started, .5)
                self.assertTrue(entered.wait(1))
                self.assertEqual(poll.call_count, 1)
            finally: release.set()
            eventually(lambda: p.cached_status() == 'idle')
            self.assertEqual(poll.call_count, 1)
