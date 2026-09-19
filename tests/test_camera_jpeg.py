import tempfile
import unittest
from pathlib import Path
from PIL import Image
from render import validate_jpeg, render_sheet

class CameraJpegTests(unittest.TestCase):
    def test_mpo_uses_primary_photo_not_thumbnail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'camera.jpg'
            primary = Image.new('RGB', (600, 400), 'red')
            thumbnail = Image.new('RGB', (160, 100), 'blue')
            primary.save(path, format='MPO', save_all=True, append_images=[thumbnail])
            original = path.read_bytes()
            with Image.open(path) as img:
                self.assertEqual(img.format, 'MPO')
            validate_jpeg(path)
            output = Path(directory) / 'sheet.png'
            render_sheet({'A': [path]*8, 'B': [path]*8}, [None]*4,
                         {'margin': 0, 'gap': 0, 'top': 0, 'bottom': 0}, output)
            with Image.open(output) as sheet:
                r, g, b = sheet.getpixel((300, 200))
                self.assertGreater(r, 240)
                self.assertLess(b, 10)
            self.assertEqual(path.read_bytes(), original)

    def test_png_disguised_as_jpeg_still_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fake.jpg'
            Image.new('RGB', (600, 400)).save(path, format='PNG')
            with self.assertRaisesRegex(ValueError, 'Not a JPEG'):
                validate_jpeg(path)

    def test_truncated_mpo_primary_still_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'broken.jpg'
            Image.new('RGB', (600, 400)).save(path, format='MPO', save_all=True,
                                             append_images=[Image.new('RGB', (160, 100))])
            path.write_bytes(path.read_bytes()[:1000])
            with self.assertRaises((OSError, ValueError, SyntaxError)):
                validate_jpeg(path)
