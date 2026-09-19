import base64
import copy
import hashlib
import json
import os
import re
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
from app import create_app
from render import default_overlay_settings, position_overlay, render_sheet
from test_stripshot import eventually
import test_operator_tools
import test_software_app


class OverlaySettingsTests(unittest.TestCase):
    setUp = test_software_app.SoftwareAppTests.setUp
    tearDown = test_software_app.SoftwareAppTests.tearDown
    engine = test_software_app.SoftwareAppTests.engine
    completed = test_operator_tools.OperatorToolsTests.completed

    def test_settings_persist_freeze_and_do_not_change_other_settings(self):
        e, _ = self.engine(start=False)
        original_layout = copy.deepcopy(e.layout)
        original_printer = copy.deepcopy(e.config['printer'])
        settings = [{'scale_x_percent': 90 + i / 10, 'offset_x_px': i - 2} for i in range(4)]
        e.action('overlay_settings', settings)
        e.freeze(software=True)
        e.action('overlay_settings', default_overlay_settings())
        restarted, _ = self.engine(start=False)
        self.assertEqual(restarted.overlay_settings, default_overlay_settings())
        self.assertEqual(restarted.state['current']['overlay_settings'], settings)
        self.assertEqual(e.layout, original_layout)
        self.assertEqual(e.config['printer'], original_printer)
        # Replacing artwork keeps its independently saved placement.
        e.action('overlay_settings', settings)
        image = Image.new('RGBA', (600, 1800), (0, 0, 0, 0))
        import io
        buf = io.BytesIO(); image.save(buf, format='PNG')
        e.action('overlay', 1, buf.getvalue())
        self.assertEqual(e.overlay_settings, settings)
        self.assertEqual(json.loads(e.overlay_settings_path.read_text()), settings)

    def test_invalid_values_or_failed_save_preserve_settings(self):
        e, _ = self.engine(start=False)
        defaults = default_overlay_settings()
        invalid = [None, {}, defaults[:3], defaults + [defaults[0]]]
        for key, value in [('scale_x_percent', True), ('scale_x_percent', '100'),
                           ('scale_x_percent', float('nan')), ('scale_x_percent', float('inf')),
                           ('scale_x_percent', 9.9), ('scale_x_percent', 100.1),
                           ('offset_x_px', True), ('offset_x_px', 1.5), ('offset_x_px', 1), ('offset_x_px', -1)]:
            invalid.append([{**defaults[0], key: value}] + defaults[1:])
        invalid += [[{}] + defaults[1:], [{**defaults[0], 'extra': 1}] + defaults[1:]]
        for settings in invalid:
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                e.action('overlay_settings', settings)
            self.assertEqual(e.overlay_settings, defaults)
        with patch('operator_tools.save_json', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): e.action('overlay_settings', defaults)
        self.assertEqual(e.overlay_settings, defaults)

    def test_api_authentication_token_validation_and_saved_status(self):
        e, cards = self.engine(); e.config['kiosk_mode'] = True
        with patch.dict(os.environ, {'STRIPSHOT_OPERATOR_PASSWORD': 'test-only-password'}):
            client = create_app(e).test_client()
        settings = [{'scale_x_percent': 95.5, 'offset_x_px': -12}] + default_overlay_settings()[1:]
        auth = {'Authorization': 'Basic ' + base64.b64encode(b'operator:test-only-password').decode()}
        self.assertEqual(client.post('/api/overlay-settings', json=settings).status_code, 401)
        self.assertEqual(client.post('/api/overlay-settings', json=settings, headers=auth).status_code, 403)
        page = client.get('/operator', headers=auth)
        token = re.search(rb'name="stripshot-token" content="([^"]+)"', page.data).group(1).decode()
        headers = {**auth, 'X-Stripshot-Token': token}
        self.assertEqual(client.post('/api/overlay-settings', json=[], headers=headers).status_code, 400)
        self.assertEqual(client.post('/api/overlay-settings', json=settings, headers=headers).status_code, 200)
        self.assertEqual(client.get('/api/status', headers=auth).json['overlay_settings'], settings)
        for i in range(1, 5):
            self.assertIn(f'id="overlay-scale-{i}"'.encode(), page.data)
            self.assertIn(f'id="overlay-offset-{i}"'.encode(), page.data)
        self.assertEqual(sum(c.shutters for c in cards.values()), 0)

    def test_render_scales_each_png_horizontally_without_calibration_moving_art(self):
        e, _ = self.engine(start=False)
        source = self.completed(e)
        photos = {c: [source / f'{c}{n:02d}.jpg' for n in range(1, 9)] for c in ('A', 'B')}
        art = Image.new('RGBA', (600, 1800))
        ImageDraw.Draw(art).rectangle((100, 20, 199, 39), fill=(0, 0, 255, 255))
        overlay = self.root / 'art.png'; art.save(overlay)
        before = hashlib.sha256(overlay.read_bytes()).hexdigest()
        settings = [{'scale_x_percent': s, 'offset_x_px': dx}
                    for s, dx in [(50, -40), (90, 30), (100, 0), (80, 40)]]
        calibration = [26, 16, 6, -2]
        baseline, output = self.root / 'baseline.png', self.root / 'sheet.png'
        render_sheet(photos, [None] * 4, e.layout, baseline, calibration, 2)
        render_sheet(photos, [overlay] * 4, e.layout, output, calibration, 2, settings)
        with Image.open(output) as actual, Image.open(baseline) as plain:
            for i, (start, end) in enumerate([(160, 210), (150, 240), (100, 200), (180, 260)]):
                origin = 600 * i
                self.assertEqual(actual.getpixel((origin + start + 5, 20)), (0, 0, 255))
                self.assertEqual(actual.getpixel((origin + end - 5, 39)), (0, 0, 255))
                self.assertEqual(actual.getpixel((origin + start - 5, 20)), plain.getpixel((origin + start - 5, 20)))
                self.assertEqual(actual.getpixel((origin + start + 5, 19)), plain.getpixel((origin + start + 5, 19)))
            self.assertEqual(actual.crop((0, 50, 2400, 1800)).tobytes(), plain.crop((0, 50, 2400, 1800)).tobytes())
        self.assertEqual(hashlib.sha256(overlay.read_bytes()).hexdigest(), before)

    def test_full_png_edges_alpha_and_default_are_preserved(self):
        art = Image.new('RGBA', (600, 1800), (255, 0, 0, 128))
        self.assertEqual(position_overlay(art, default_overlay_settings()[0]).tobytes(), art.tobytes())
        for scale, offset in [(100, -1), (100, 1), (50, 151), (50, -151), (200, 0)]:
            with self.assertRaises(ValueError):
                position_overlay(art, {'scale_x_percent': scale, 'offset_x_px': offset})
        positioned = position_overlay(art, {'scale_x_percent': 50, 'offset_x_px': 150})
        self.assertEqual(positioned.getpixel((299, 900)), (0, 0, 0, 0))
        self.assertEqual(positioned.getpixel((599, 900)), (255, 0, 0, 128))
        # Both horizontal extremes retain the full resized alpha area, including top/bottom.
        for offset in (-150, 150):
            result = position_overlay(art, {'scale_x_percent': 50, 'offset_x_px': offset})
            self.assertEqual(result.getchannel('A').histogram()[128], 300 * 1800)

    def test_calibration_cannot_crop_any_png_edge(self):
        e, _ = self.engine(start=False); source = self.completed(e)
        photos = {c: [source / f'{c}{n:02d}.jpg' for n in range(1, 9)] for c in ('A', 'B')}
        art = Image.new('RGBA', (600, 1800)); draw = ImageDraw.Draw(art)
        draw.rectangle((0, 0, 599, 1799), outline=(0, 0, 255, 255), width=8)
        overlay = self.root / 'border.png'; art.save(overlay)
        for y in (-60, 60):
            output = self.root / 'edge-sheet.png'
            render_sheet(photos, [overlay] * 4, e.layout, output, [-60, 60, 26, -2], y)
            with Image.open(output) as sheet:
                for i in range(4):
                    for x, py in [(0, 0), (599, 0), (0, 1799), (599, 1799), (0, 900), (599, 900)]:
                        self.assertEqual(sheet.getpixel((i * 600 + x, py)), (0, 0, 255))

    def test_dry_run_uses_saved_adjustments_without_rewriting_originals(self):
        e, cards = self.engine(start=False); e.phase = 'watching'
        source = self.completed(e)
        before = {p: p.read_bytes() for p in source.iterdir()}
        overlay = e.root / 'overlays/strip1.png'; overlay.parent.mkdir()
        art = Image.new('RGBA', (600, 1800))
        ImageDraw.Draw(art).rectangle((0, 0, 599, 19), fill=(0, 0, 255, 255)); art.save(overlay)
        settings = [{'scale_x_percent': 50, 'offset_x_px': 50}] + default_overlay_settings()[1:]
        e.action('overlay_settings', settings)
        with patch('printer.Printer.submit', side_effect=AssertionError('Never print')):
            result = e.action('dry_run')
        output = e.root / 'dry-runs' / result['id']
        with Image.open(output / 'sheet.png') as sheet:
            self.assertEqual(sheet.getpixel((199, 10)), (255, 255, 255))
            self.assertEqual(sheet.getpixel((200, 10)), (0, 0, 255))
            self.assertEqual(sheet.getpixel((500, 10)), (255, 255, 255))
        self.assertEqual(json.loads((output / 'manifest.json').read_text())['overlay_settings'], settings)
        self.assertEqual(before, {p: p.read_bytes() for p in source.iterdir()})
        self.assertEqual(sum(c.shutters for c in cards.values()), 0)

    def test_resumed_batches_use_frozen_adjustments_and_legacy_defaults(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                e, _ = self.engine(start=False)
                frozen = [{'scale_x_percent': 95, 'offset_x_px': -5}] * 4
                e.action('overlay_settings', frozen)
                e.freeze(software=True)
                if legacy:
                    del e.state['current']['overlay_settings']; e.save()
                e.action('overlay_settings', default_overlay_settings())
                with patch('batch.render_sheet', wraps=render_sheet) as render:
                    restarted, _ = self.engine(phase='capture_held')
                    restarted.request('resume_capture').result(5)
                    eventually(lambda: restarted.state['last'] is not None and not restarted.state['current'])
                    self.assertEqual(render.call_args.kwargs['overlay_settings'], None if legacy else frozen)
                restarted.stop()
