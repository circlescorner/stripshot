import copy
import io
import json
import re
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
from app import create_app
from render import default_overlay_settings, position_overlay, validate_overlay_settings
from scan_alignment import analyze_scan
from storage import save_json
import test_software_app


class ScanAlignmentTests(unittest.TestCase):
    setUp = test_software_app.SoftwareAppTests.setUp
    tearDown = test_software_app.SoftwareAppTests.tearDown
    engine = test_software_app.SoftwareAppTests.engine

    def target(self, e):
        e.phase = 'watching'; target = e.action('scan_prepare')
        directory = e.calibration_print.directory(target['id'])
        record = json.loads((directory/'manifest.json').read_text())
        record['status'] = 'submitted'; record['job_id'] = 'mock-scan-target'
        save_json(directory/'manifest.json', record)
        return record, directory

    def scan(self, directory, strip, dx=24, dy=4, rotation=0, scale=1, cropped=False):
        with Image.open(directory/'sheet.png') as sheet:
            artwork = sheet.crop(((strip-1)*600, 0, strip*600, 1800))
        paper = Image.new('RGB', (600, 1800), 'white'); paper.paste(artwork, (dx, dy))
        scan = Image.new('RGB', (1000, 2200), (25, 25, 25)); scan.paste(paper, (200, 200))
        if cropped: scan = paper
        if rotation: scan = scan.rotate(rotation, Image.Resampling.BICUBIC, expand=True, fillcolor=(25, 25, 25))
        if scale != 1: scan = scan.resize((int(scan.width*scale), int(scan.height*scale)), Image.Resampling.LANCZOS)
        output = io.BytesIO(); scan.save(output, 'PNG'); return output.getvalue()

    def uploaded(self, e, rotations=False):
        target, directory = self.target(e)
        for i, dx in enumerate((27, 18, 9, -1), 1):
            e.action('scan_upload', target['id'], i, self.scan(directory, i, dx, rotation=1.1 if rotations else 0))
        return target, directory

    def test_rotated_and_high_resolution_scans_measure_known_print_error(self):
        e, _ = self.engine(start=False); target, directory = self.target(e)
        for rotation, scale in ((1.1, 1), (-1.5, 2), (90, 1), (180, 1)):
            with self.subTest(rotation=rotation, scale=scale):
                measurement, preview = analyze_scan(self.scan(directory, 1, rotation=rotation, scale=scale), target['scan_markers'][0])
                for actual, expected in zip(measurement['paper_bounds_px'], (-24, -4, 576, 1796)):
                    self.assertAlmostEqual(actual, expected, delta=2)
                self.assertLess(measurement['fit_error_px'], 1.5)
                with Image.open(io.BytesIO(preview)) as im: self.assertEqual(im.format, 'JPEG')

    def test_wrong_strip_target_crop_and_small_scan_are_rejected(self):
        e, _ = self.engine(start=False); target, directory = self.target(e)
        for content in (self.scan(directory, 2), self.scan(directory, 1, cropped=True),
                        self.scan(directory, 1, scale=.5), b'not an image'):
            with self.assertRaises(ValueError): analyze_scan(content, target['scan_markers'][0])
        old = self.scan(directory, 1); newer, _ = self.target(e)
        with self.assertRaises(ValueError): analyze_scan(old, newer['scan_markers'][0])
        with self.assertRaises(ValueError): e.action('scan_upload', target['id'], 1, old)

    def test_proposal_fits_full_png_to_cut_edges_and_apply_changes_only_png(self):
        e, cards = self.engine(start=False); target, directory = self.uploaded(e, rotations=True)
        originals = {p.name: p.read_bytes() for p in directory.glob('*.original')}
        printer = copy.deepcopy(e.config['printer']); layout = copy.deepcopy(e.layout)
        result = e.action('scan_propose', {'id': target['id'], 'clearance_mm': .5})
        proposal = result['proposal']; validate_overlay_settings(proposal['settings'])
        self.assertEqual(e.overlay_settings, default_overlay_settings())
        for i, setting in enumerate(proposal['settings']):
            self.assertAlmostEqual(setting['offset_x_px'], -(27, 18, 9, -1)[i], delta=2)
            self.assertAlmostEqual(setting['offset_y_px'], -4, delta=2)
            self.assertTrue(setting['scale_y_percent'] < 100)
            margins = proposal['measurements'][i]['after_margins_mm']
            self.assertTrue(all(m >= .49 for m in margins))
            self.assertAlmostEqual(margins[0], margins[1], delta=.1)
            self.assertAlmostEqual(margins[2], margins[3], delta=.1)
            art = Image.new('RGBA', (600, 1800), (0, 0, 255, 255))
            result_art = position_overlay(art, setting)
            expected_area = int(600*setting['scale_x_percent']/100+.5)*int(1800*setting['scale_y_percent']/100+.5)
            self.assertEqual(result_art.getchannel('A').histogram()[255], expected_area)
        with patch('printer.Printer.submit', side_effect=AssertionError('Never print on apply')):
            applied = e.action('scan_apply', {'id': target['id'], 'proposal_id': proposal['id']})
        self.assertTrue(applied['proposal']['applied'])
        self.assertEqual(e.overlay_settings, proposal['settings'])
        self.assertEqual(e.config['printer'], printer); self.assertEqual(e.layout, layout)
        self.assertEqual(sum(c.shutters for c in cards.values()), 0)
        self.assertEqual(originals, {p.name: p.read_bytes() for p in directory.glob('*.original')})
        restarted, _ = self.engine(start=False)
        self.assertEqual(restarted.overlay_settings, proposal['settings'])
        self.assertTrue(restarted.scan_alignment.status()['proposal']['applied'])

    def test_missing_scans_stale_settings_and_replacement_invalidate_apply(self):
        e, _ = self.engine(start=False); target, directory = self.target(e)
        with self.assertRaises(ValueError): e.action('scan_propose', {'id': target['id'], 'clearance_mm': .5})
        for i in range(1,5): e.action('scan_upload', target['id'], i, self.scan(directory, i))
        proposal = e.action('scan_propose', {'id': target['id'], 'clearance_mm': .5})['proposal']
        candidate = {'id': target['id'], 'proposal_id': proposal['id']}
        with self.assertRaises(ValueError): e.action('scan_apply', {**candidate, 'proposal_id': 'stale'})
        changed = default_overlay_settings(); changed[0]['scale_x_percent'] = 90
        e.action('overlay_settings', changed)
        with self.assertRaisesRegex(ValueError, 'settings changed'): e.action('scan_apply', candidate)
        e.action('overlay_settings', default_overlay_settings())
        with self.assertRaises(ValueError): e.action('scan_upload', target['id'], 1, b'bad replacement')
        self.assertNotIn('1', e.scan_alignment.status()['strips'])
        self.assertIsNone(e.scan_alignment.status()['proposal'])
        with self.assertRaises(ValueError): e.action('scan_apply', candidate)

    def test_no_analysis_before_print_and_no_apply_during_batch(self):
        e, _ = self.engine(start=False); e.phase='watching'; target=e.action('scan_prepare')
        with self.assertRaisesRegex(ValueError, 'Print this'): e.action('scan_upload', target['id'], 1, b'bad')
        target, _ = self.uploaded(e)
        proposal=e.action('scan_propose', {'id':target['id'], 'clearance_mm':.5})['proposal']
        e.freeze(software=True); frozen=copy.deepcopy(e.state['current'])
        with self.assertRaisesRegex(ValueError, 'session'): e.action('scan_apply', {'id':target['id'], 'proposal_id':proposal['id']})
        self.assertEqual(e.state['current'], frozen)

    def test_upload_api_token_and_evidence_preview(self):
        e, _ = self.engine(); client=create_app(e).test_client()
        token=re.search(rb'name="stripshot-token" content="([^"]+)"',client.get('/').data).group(1).decode()
        headers={'X-Stripshot-Token':token}
        response=client.post('/api/operator-tools/scan_prepare', json={}, headers=headers)
        self.assertEqual(response.status_code,200)
        target,directory=self.target(e); url=f'/api/scan-alignment/{target["id"]}/1'
        self.assertEqual(client.post(url).status_code,403)
        response=client.post(url, data={'file':(io.BytesIO(self.scan(directory,1)),'anything.png')}, headers=headers)
        self.assertEqual(response.status_code,200,response.json)
        with client.get(response.json['strips']['1']['preview_url']) as image:
            self.assertEqual(image.status_code,200)
        self.assertEqual(client.get(f'/api/scan-alignment/{target["id"]}/preview/not-a-scan.jpg').status_code,404)
        self.assertIn(b'scan-propose-form',client.get('/operator').data)
