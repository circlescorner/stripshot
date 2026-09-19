import hashlib
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from render import render_sheet, validate_strip_offsets, fit_calibrated_strip
from config import load_config
from storage import save_json
import test_software_app
from test_stripshot import eventually


class CalibrationRenderTests(unittest.TestCase):
    def test_shift_clips_each_composited_strip_preserves_order_and_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            photos = {'A': [], 'B': []}
            for c in photos:
                for i in range(8):
                    p = root/f'{c}{i}.jpg'
                    Image.new('RGB', (120,120), (30+i*20, 50 if c=='A' else 150, 70)).save(p)
                    photos[c].append(p)
            overlays = []
            for i in range(4):
                p = root/f'o{i}.png'
                im = Image.new('RGBA',(600,1800),(i*50,20,200,100))
                im.save(p); overlays.append(p)
            paths = sum(photos.values(), []) + overlays
            before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
            layout = {'margin':24,'gap':18,'top':24,'bottom':180}
            render_sheet(photos, overlays, layout, root/'original.png')
            render_sheet(photos, overlays, layout, root/'shifted.png', [20,15,6,-2], fit_calibration=False)
            with Image.open(root/'original.png') as original, Image.open(root/'shifted.png') as shifted:
                for i, dx in enumerate([20,15,6,-2]):
                    expected = Image.new('RGB',(600,1800),'white')
                    expected.paste(original.crop((i*600,0,(i+1)*600,1800)),(dx,0))
                    self.assertEqual(expected.tobytes(),shifted.crop((i*600,0,(i+1)*600,1800)).tobytes())
            self.assertEqual(before,[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths])

    def test_fitted_strip_has_no_padding_and_retains_center_shift(self):
        from PIL import ImageDraw
        for dx,dy in ((26,2),(20,0),(-2,-12),(60,-60),(-60,60),(0,0)):
            strip=Image.new('RGB',(600,1800),(80,120,160))
            draw=ImageDraw.Draw(strip);draw.rectangle((296,896,303,903),fill=(220,40,30))
            fitted=fit_calibrated_strip(strip,dx,dy)
            self.assertEqual(fitted.size,(600,1800))
            for x,y in ((0,0),(599,0),(0,1799),(599,1799),(0,900),(599,900),(300,0),(300,1799)):
                self.assertEqual(fitted.getpixel((x,y)),(80,120,160))
            self.assertEqual(fitted.getpixel((300+dx,900+dy)),(220,40,30))
            if dx==dy==0:self.assertEqual(strip.tobytes(),fitted.tobytes())

    def test_horizontal_fit_does_not_crop_vertical_artwork(self):
        strip=Image.new('RGB',(600,1800),(80,120,160))
        from PIL import ImageDraw
        ImageDraw.Draw(strip).rectangle((280,1780,320,1790),fill=(220,40,30))
        fitted=fit_calibrated_strip(strip,26,0)
        self.assertEqual(fitted.getpixel((326,1785)),(220,40,30))

    def test_invalid_offsets_and_legacy_default(self):
        for value in (None,[0]*3,[0,0,0,True],[0,0,0,1.5],[61,0,0,0],'20,15,6,-2'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_strip_offsets(value)
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'config.json'
            save_json(p,{'demo':True})
            self.assertEqual(load_config(p)['printer']['strip_offsets_px'],[0]*4)
            save_json(p,{'demo':True,'printer':{'strip_offsets_px':[100,0,0,0]}})
            with self.assertRaises(ValueError): load_config(p)


class CalibrationRecoveryTests(unittest.TestCase):
    setUp = test_software_app.SoftwareAppTests.setUp
    tearDown = test_software_app.SoftwareAppTests.tearDown
    engine = test_software_app.SoftwareAppTests.engine

    def test_frozen_offsets_survive_config_change_and_resume(self):
        self.cfg['printer']['strip_offsets_px']=[20,15,6,-2]
        e,_=self.engine(start=False)
        e.freeze(software=True)
        e.state['current']['printer'].pop('calibration_fit')
        e.save()
        self.cfg['printer']['strip_offsets_px']=[0]*4
        resumed,_=self.engine(phase='capture_held')
        resumed.request('resume_capture').result(5)
        eventually(lambda: resumed.status()['last'] is not None)
        last=resumed.status()['last']
        self.assertEqual(last['printer']['strip_offsets_px'],[20,15,6,-2])
        self.assertEqual(last['status'],'dry_run')
        with Image.open(resumed.root/'batches'/last['id']/'sheet.png') as im:
            for col,dx in enumerate([20,15,6,-2]):
                edge=col*600+self.cfg['layout']['margin']+dx
                self.assertEqual(im.getpixel((edge-1,100)),(255,255,255))
                self.assertNotEqual(im.getpixel((edge,100)),(255,255,255))
