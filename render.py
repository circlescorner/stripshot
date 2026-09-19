"""Four alternating-camera strips on an 8 x 6 inch, 300 DPI sheet."""
import io
from pathlib import Path
from PIL import Image, ImageOps
from storage import atomic_bytes

STRIP = (600, 1800)
SHEET = (2400, 1800)
DEFAULT_PHOTO_ORDER = [[f"{c}{n}" for n in (i * 2 + 1, i * 2 + 2) for c in ("A", "B")] for i in range(4)]


def validate_strip_offsets(offsets):
    if not isinstance(offsets, list) or len(offsets) != 4 or any(
        type(value) is not int or abs(value) > 60 for value in offsets
    ):
        raise ValueError('strip_offsets_px must contain four integers between -60 and 60')


def validate_vertical_offset(value):
    if type(value) is not int or abs(value)>60:
        raise ValueError('Vertical offset must be a whole number between -60 and 60 pixels')


def validate_layout(layout):
    required = {'margin', 'gap', 'top', 'bottom'}
    if not isinstance(layout, dict) or not required <= set(layout) or set(layout) - required - {'photo_scale', 'photo_order'}:
        raise ValueError('Layout needs margin, gap, top, bottom and optional photo_scale')
    if any(type(layout[k]) is not int or layout[k] < 0 for k in required):
        raise ValueError('Margins and gaps must be nonnegative integer pixels')
    order = layout.get('photo_order', DEFAULT_PHOTO_ORDER)
    if (not isinstance(order, list) or len(order) != 4
            or any(not isinstance(strip, list) or len(strip) != 4 for strip in order)):
        raise ValueError('Photo order needs four strips with four photos each')
    flattened = [item for strip in order for item in strip]
    expected = {f'{c}{n}' for c in ('A', 'B') for n in range(1, 9)}
    if any(not isinstance(item, str) for item in flattened) or set(flattened) != expected:
        raise ValueError('Photo order must use A1–A8 and B1–B8 exactly once')
    scale = layout.get('photo_scale', 100)
    if type(scale) is not int or not 50 <= scale <= 100:
        raise ValueError('Photo scale must be an integer from 50 to 100 percent')
    if (600 - 2 * layout['margin']) * scale // 100 < 100:
        raise ValueError('Scaled photo width must be at least 100 pixels')
    if ((1800 - layout['top'] - layout['bottom'] - 3 * layout['gap']) // 4) * scale // 100 < 100:
        raise ValueError('Scaled photo height must be at least 100 pixels')


def validate_jpeg(path):
    with Image.open(path) as img:
        # Nikon JPEGs may contain MPF thumbnail entries and be identified
        # by Pillow as MPO. Decode the primary photograph, never a thumbnail.
        if img.format not in ('JPEG', 'MPO'):
            raise ValueError(f'Not a JPEG: {Path(path).name}')
        img.verify()
    with Image.open(path) as img:
        img.seek(0)
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


def fit_calibrated_strip(strip, dx, dy):
    """Fit each axis without padding, keeping the saved center translation."""
    width, height = strip.size
    # Horizontal correction must not unnecessarily crop the top/bottom artwork.
    scaled_width = width + 2 * abs(dx)
    scaled_height = height + 2 * abs(dy)
    enlarged = strip.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
    left = (scaled_width - width) // 2 - dx
    top = (scaled_height - height) // 2 - dy
    return enlarged.crop((left, top, left + width, top + height))


def render_sheet(photos, overlays, layout, output, strip_offsets_px=None, sheet_offset_y_px=0, fit_calibration=True):
    validate_layout(layout)
    offsets = [0, 0, 0, 0] if strip_offsets_px is None else strip_offsets_px
    validate_strip_offsets(offsets)
    validate_vertical_offset(sheet_offset_y_px)
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
        ordered = [photos[item[0]][int(item[1:]) - 1]
                   for item in layout.get('photo_order', DEFAULT_PHOTO_ORDER)[index]]
        for row, path in enumerate(ordered):
            with Image.open(path) as img:
                img.seek(0)
                photo = ImageOps.fit(ImageOps.exif_transpose(img).convert('RGB'),
                                     (width, height), method=Image.Resampling.LANCZOS)
            scale = layout.get('photo_scale', 100)
            scaled_width, scaled_height = width * scale // 100, height * scale // 100
            if scale != 100:
                photo = photo.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
            strip.paste(photo, (layout['margin'] + (width - scaled_width) // 2,
                               layout['top'] + row * (height + layout['gap']) + (height - scaled_height) // 2))
        if overlays[index] is not None:
            with Image.open(overlays[index]) as overlay:
                if overlay.size != STRIP:
                    raise ValueError('Overlay has incorrect dimensions')
                strip = Image.alpha_composite(strip, overlay.convert('RGBA'))
        # Translate photos and artwork together, clipped within this strip.
        # Never let calibration spill content into its neighbor.
        if fit_calibration:
            calibrated = fit_calibrated_strip(strip.convert('RGB'), offsets[index], sheet_offset_y_px)
        else:
            # Preserve the rendering of batches frozen before calibration fitting.
            calibrated = Image.new('RGB', STRIP, 'white')
            calibrated.paste(strip.convert('RGB'), (offsets[index], sheet_offset_y_px))
        sheet.paste(calibrated, (index * 600, 0))
    buf = io.BytesIO()
    sheet.save(buf, format='PNG', dpi=(300, 300))
    atomic_bytes(output, buf.getvalue())
    buf = io.BytesIO()
    sheet.resize((800, 600), Image.Resampling.LANCZOS).save(buf, format='JPEG', quality=88)
    atomic_bytes(Path(output).with_name('preview.jpg'), buf.getvalue())
