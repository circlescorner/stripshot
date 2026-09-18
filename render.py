"""Four alternating-camera strips on an 8 x 6 inch, 300 DPI sheet."""
import io
from pathlib import Path
from PIL import Image, ImageOps
from storage import atomic_bytes

STRIP = (600, 1800)
SHEET = (2400, 1800)


def validate_layout(layout):
    if set(layout) != {'margin', 'gap', 'top', 'bottom'} or any(
        type(v) is not int or v < 0 for v in layout.values()
    ):
        raise ValueError('Layout needs nonnegative integer margin, gap, top, bottom')
    if 600 - 2 * layout['margin'] < 100:
        raise ValueError('Photo width must be at least 100 pixels')
    if (1800 - layout['top'] - layout['bottom'] - 3 * layout['gap']) // 4 < 100:
        raise ValueError('Photo height must be at least 100 pixels')


def validate_jpeg(path):
    with Image.open(path) as img:
        if img.format != 'JPEG':
            raise ValueError(f'Not a JPEG: {Path(path).name}')
        img.verify()
    with Image.open(path) as img:
        img.load()
        if min(img.size) < 100:
            raise ValueError(f'Image too small: {Path(path).name}')


def normalize_overlay(content):
    with Image.open(io.BytesIO(content)) as img:
        if img.format != 'PNG' or img.size != STRIP:
            raise ValueError('Overlay must be a 600 × 1800 pixel PNG')
        img.load()
        rgba = img.convert('RGBA')
        if rgba.getchannel('A').getextrema()[0] == 255:
            raise ValueError('Overlay needs transparent areas so photographs remain visible')
        buf = io.BytesIO()
        rgba.save(buf, format='PNG')
        return buf.getvalue()


def render_sheet(photos, overlays, layout, output):
    validate_layout(layout)
    if set(photos) != {'A', 'B'} or any(len(photos[c]) != 8 for c in photos):
        raise ValueError('Exactly eight JPEGs per camera are required')
    for files in photos.values():
        for path in files:
            validate_jpeg(path)
    sheet = Image.new('RGB', SHEET, 'white')
    width = 600 - 2 * layout['margin']
    height = (1800 - layout['top'] - layout['bottom'] - 3 * layout['gap']) // 4
    for index in range(4):
        strip = Image.new('RGBA', STRIP, 'white')
        ordered = [photos[c][n] for n in (index * 2, index * 2 + 1) for c in ('A', 'B')]
        for row, path in enumerate(ordered):
            with Image.open(path) as img:
                photo = ImageOps.fit(ImageOps.exif_transpose(img).convert('RGB'),
                                     (width, height), method=Image.Resampling.LANCZOS)
            strip.paste(photo, (layout['margin'], layout['top'] + row * (height + layout['gap'])))
        if overlays[index] is not None:
            with Image.open(overlays[index]) as overlay:
                if overlay.size != STRIP:
                    raise ValueError('Overlay has incorrect dimensions')
                strip = Image.alpha_composite(strip, overlay.convert('RGBA'))
        sheet.paste(strip.convert('RGB'), (index * 600, 0))
    buf = io.BytesIO()
    sheet.save(buf, format='PNG', dpi=(300, 300))
    atomic_bytes(output, buf.getvalue())
    buf = io.BytesIO()
    sheet.resize((800, 600), Image.Resampling.LANCZOS).save(buf, format='JPEG', quality=88)
    atomic_bytes(Path(output).with_name('preview.jpg'), buf.getvalue())
