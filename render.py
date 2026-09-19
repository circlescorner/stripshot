"""Four alternating-camera strips on an 8 x 6 inch, 300 DPI sheet."""
import io
import math
from pathlib import Path
from PIL import Image, ImageOps
from storage import atomic_bytes

STRIP = (600, 1800)
SHEET = (2400, 1800)
DEFAULT_PHOTO_ORDER = [[f"{c}{n}" for n in (i * 2 + 1, i * 2 + 2) for c in ("A", "B")] for i in range(4)]


def default_overlay_settings():
    return [{'scale_x_percent': 100, 'offset_x_px': 0} for _ in range(4)]


def validate_overlay_settings(settings):
    if not isinstance(settings, list) or len(settings) != 4:
        raise ValueError('Alignment settings need four strips')
    for strip in settings:
        if (not isinstance(strip, dict) or not {'scale_x_percent', 'offset_x_px'} <= set(strip)
                or set(strip) - {'scale_x_percent', 'offset_x_px', 'scale_y_percent', 'offset_y_px'}):
            raise ValueError('Each strip needs scale_x_percent and offset_x_px')
        scale, offset = strip['scale_x_percent'], strip['offset_x_px']
        if type(scale) not in (int, float) or not math.isfinite(scale) or not 10 <= scale <= 100:
            raise ValueError('Strip horizontal scale must be between 10 and 100 percent so the full design fits')
        if type(offset) is not int or not -600 <= offset <= 600:
            raise ValueError('Strip horizontal offset must be a whole number between -600 and 600 pixels')
        width = int(STRIP[0] * scale / 100 + 0.5)
        left = (STRIP[0] - width) // 2
        if not -left <= offset <= STRIP[0] - width - left:
            raise ValueError(f'Strip offset must be between {-left} and {STRIP[0] - width - left} pixels '
                             f'at {scale}% width; shrink the strip to make room. The full design is kept')
        scale_y, offset_y = strip.get('scale_y_percent', 100), strip.get('offset_y_px', 0)
        if type(scale_y) not in (int, float) or not 10 <= scale_y <= 100:
            raise ValueError('Strip vertical scale must be between 10 and 100 percent')
        height = int(STRIP[1] * scale_y / 100 + 0.5)
        top = (STRIP[1] - height) // 2
        if type(offset_y) is not int or not -top <= offset_y <= STRIP[1] - height - top:
            raise ValueError('Strip vertical offset would crop the design; reduce the offset or height')


def position_overlay(overlay, settings):
    """Fit a complete canvas inside one strip without clipping any edge."""
    validate_overlay_settings([settings] * 4)
    width = int(STRIP[0] * settings['scale_x_percent'] / 100 + 0.5)
    height = int(STRIP[1] * settings.get('scale_y_percent', 100) / 100 + 0.5)
    artwork = overlay.convert('RGBA')
    if (width, height) != STRIP:
        artwork = artwork.resize((width, height), Image.Resampling.LANCZOS)
    positioned = Image.new('RGBA', STRIP)
    positioned.paste(artwork, ((STRIP[0] - width) // 2 + settings['offset_x_px'],
                             (STRIP[1] - height) // 2 + settings.get('offset_y_px', 0)))
    return positioned


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


def render_sheet(photos, overlays, layout, output, strip_offsets_px=None, sheet_offset_y_px=0,
                 overlay_settings=None, alignment_mode='legacy'):
    # Unversioned, already frozen batches must keep their original geometry.
    if alignment_mode not in ('legacy', 'whole_strip'):
        raise ValueError('Unknown strip alignment mode')
    validate_layout(layout)
    artwork_settings = default_overlay_settings() if overlay_settings is None else overlay_settings
    validate_overlay_settings(artwork_settings)
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
        calibrated = Image.new('RGBA', STRIP, 'white')
        calibrated.paste(strip, (offsets[index], sheet_offset_y_px) if alignment_mode == 'legacy' else (0, 0))
        if overlays[index] is not None:
            with Image.open(overlays[index]) as overlay:
                if overlay.size != STRIP:
                    raise ValueError('Overlay has incorrect dimensions')
                artwork = (position_overlay(overlay, artwork_settings[index])
                           if alignment_mode == 'legacy' else overlay.convert('RGBA'))
                calibrated = Image.alpha_composite(calibrated, artwork)
        if alignment_mode == 'whole_strip':
            # Compose first, then fit photos and artwork together exactly once.
            # White backing matters: position_overlay leaves transparent margins.
            calibrated = Image.alpha_composite(Image.new('RGBA', STRIP, 'white'),
                                               position_overlay(calibrated, artwork_settings[index]))
        sheet.paste(calibrated.convert('RGB'), (index * 600, 0))
    buf = io.BytesIO()
    sheet.save(buf, format='PNG', dpi=(300, 300))
    atomic_bytes(output, buf.getvalue())
    buf = io.BytesIO()
    sheet.resize((800, 600), Image.Resampling.LANCZOS).save(buf, format='JPEG', quality=88)
    atomic_bytes(Path(output).with_name('preview.jpg'), buf.getvalue())
