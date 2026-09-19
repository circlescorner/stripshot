"""Measure printed paper edges from four separate flatbed calibration scans."""
import hashlib
import io
import json
import math
import secrets
import time
import uuid
from PIL import Image, ImageDraw, ImageFont, ImageOps
from render import STRIP, validate_overlay_settings
from storage import atomic_bytes, save_json


def vision():
    import cv2
    import numpy as np
    cv2.setNumThreads(1)
    return cv2, np


def make_scan_sheet(ident, settings):
    cv, np = vision()
    dictionary = cv.aruco.getPredefinedDictionary(cv.aruco.DICT_5X5_1000)
    ids = secrets.SystemRandom().sample(range(1000), 16)
    sheet = Image.new('RGB', (2400, 1800), 'white')
    font = ImageFont.truetype('DejaVuSans.ttf', 25)
    markers = []
    for strip in range(4):
        panel = Image.new('RGB', STRIP, 'white'); draw = ImageDraw.Draw(panel)
        draw.text((100, 70), f'SCAN STRIP {strip+1}', font=font, fill='black')
        draw.text((100, 110), ident[-8:], font=font, fill='black')
        draw.text((110, 850), 'TOP IS ABOVE', font=font, fill='black')
        draw.text((75, 900), 'Scan on dark backing', font=font, fill='black')
        current = settings[strip]
        w = int(600 * current['scale_x_percent'] / 100 + .5)
        h = int(1800 * current.get('scale_y_percent', 100) / 100 + .5)
        x = (600-w)//2 + current['offset_x_px']; y = (1800-h)//2 + current.get('offset_y_px', 0)
        # Light outline is the current artwork extent; it cannot obscure paper detection.
        draw.rectangle((x, y, x+w-1, y+h-1), outline=(210, 230, 215), width=3)
        strip_markers = []
        for n, (mx, my) in enumerate(((90, 250), (414, 250), (90, 1450), (414, 1450))):
            marker_id = ids[strip*4+n]
            panel.paste(Image.fromarray(cv.aruco.generateImageMarker(dictionary, marker_id, 96)), (mx, my))
            strip_markers.append({'id': marker_id, 'corners': [[mx, my], [mx+95, my], [mx+95, my+95], [mx, my+95]]})
        sheet.paste(panel, (600*strip, 0)); markers.append(strip_markers)
    return sheet, markers


def analyze_scan(content, markers):
    """Return paper boundaries in original 300-DPI strip coordinates, plus evidence."""
    cv, np = vision()
    try:
        with Image.open(io.BytesIO(content)) as source:
            if source.format not in ('PNG', 'JPEG', 'TIFF') or getattr(source, 'n_frames', 1) != 1:
                raise ValueError('Upload one PNG, JPEG or single-page TIFF scan')
            if source.width * source.height > 50_000_000:
                raise ValueError('Scan is too large; use 300 or 600 DPI, at most 50 megapixels')
            image = ImageOps.exif_transpose(source).convert('RGB')
    except (OSError, Image.DecompressionBombError) as exc:
        raise ValueError('This file could not be read as a scan') from exc
    image.thumbnail((6000, 6000))
    pixels = np.array(image); gray = cv.cvtColor(pixels, cv.COLOR_RGB2GRAY)
    parameters = cv.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = cv.aruco.CORNER_REFINE_SUBPIX
    corners, ids, _ = cv.aruco.ArucoDetector(
        cv.aruco.getPredefinedDictionary(cv.aruco.DICT_5X5_1000), parameters).detectMarkers(gray)
    found = {} if ids is None else {int(i): c.reshape(4, 2) for i, c in zip(ids.flatten(), corners)}
    wanted = {m['id'] for m in markers}
    if set(found) != wanted or ids is None or len(ids) != 4:
        raise ValueError('The four reference marks do not match this target and strip. Scan the numbered calibration strip, with all four marks visible')
    original = np.array([p for m in markers for p in m['corners']], dtype=np.float64)
    scanned = np.concatenate([found[m['id']] for m in markers]).astype(np.float64)
    design = np.column_stack((original, np.ones(len(original))))
    affine = np.linalg.lstsq(design, scanned, rcond=None)[0].T
    linear = affine[:, :2]
    scales = np.linalg.norm(linear, axis=0)
    if min(scales) < .85:
        raise ValueError('The scan is too small for reliable alignment. Scan at 300 or 600 DPI without resizing')
    if np.linalg.det(linear) <= 0 or max(scales)/min(scales) > 1.06:
        raise ValueError('Scan is mirrored or distorted. Use a flatbed scan with automatic stretching disabled')
    if abs(float(np.dot(linear[:, 0], linear[:, 1])/(scales[0]*scales[1]))) > .03:
        raise ValueError('Scan is sheared. Use a flatbed scan without perspective correction')
    residual = float(np.max(np.linalg.norm((design @ affine.T - scanned) @ np.linalg.inv(linear).T, axis=1)))
    if residual > 1.5:
        raise ValueError('Reference marks are not consistent enough. Keep the strip flat and rescan without perspective correction')
    # Bright saturated backing (especially yellow) can be as bright as paper in
    # grayscale. Require brightness in every channel to separate white paper
    # from coloured backing without guessing boundaries from the marker positions.
    mask = (pixels.min(axis=2) > 175).astype(np.uint8)*255
    contours, _ = cv.findContours(mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
    candidates = [c for c in contours if all(cv.pointPolygonTest(c, tuple(map(float, p)), False) >= 0 for p in scanned)]
    if len(candidates) != 1:
        raise ValueError('Paper edges are unclear. Put a dark matte sheet behind the strip and leave space around all four edges')
    contour = candidates[0]
    x, y, w, h = cv.boundingRect(contour)
    if x < 8 or y < 8 or x+w > image.width-8 or y+h > image.height-8:
        raise ValueError('Paper cannot be separated from the scan border. The scan may be cropped, or the backing may blend into the paper. Leave visible dark matte backing around all four edges and disable automatic cropping')
    rectangle = cv.minAreaRect(contour)
    box = cv.boxPoints(rectangle)
    if cv.contourArea(contour)/(rectangle[1][0]*rectangle[1][1]) < .985:
        raise ValueError('Paper outline is not a clean rectangle. Remove other objects, flatten the strip and use dark backing')
    inv = cv.invertAffineTransform(affine)
    paper = cv.transform(box.reshape(1, -1, 2).astype(np.float64), inv)[0]
    ordered = paper[np.argsort(paper[:, 1])]
    top = ordered[:2][np.argsort(ordered[:2, 0])]
    bottom = ordered[2:][np.argsort(ordered[2:, 0])]
    tl, tr, bl, br = top[0], top[1], bottom[0], bottom[1]
    skew = max(abs(tl[0]-bl[0]), abs(tr[0]-br[0]), abs(tl[1]-tr[1]), abs(bl[1]-br[1]))
    if skew > 6:
        raise ValueError('The print is too skewed relative to its cut edges for scale/offset correction. Rescan flat; check the printer if the skew repeats')
    bounds = [float(max(tl[0], bl[0])), float(max(tl[1], tr[1])),
              float(min(tr[0], br[0])+1), float(min(bl[1], br[1])+1)]
    if not 540 < bounds[2]-bounds[0] < 660 or not 1650 < bounds[3]-bounds[1] < 1950:
        raise ValueError('Detected paper size does not match one 2 × 6 inch strip; scan each strip separately')
    if max(abs(bounds[0]), abs(bounds[1]), abs(bounds[2]-600), abs(bounds[3]-1800)) > 100:
        raise ValueError('The detected displacement is unusually large. Check the paper edges and printer media before applying')
    annotated = image.copy(); draw = ImageDraw.Draw(annotated)
    polygon = [tuple(map(float, p)) for p in box]
    draw.line(polygon+[polygon[0]], fill=(0, 190, 65), width=max(3, round(min(scales)*2)))
    for m in markers:
        points = [tuple(map(float, p)) for p in found[m['id']]]
        draw.line(points+[points[0]], fill=(0, 100, 255), width=3)
    annotated.thumbnail((1100, 1400)); buf = io.BytesIO(); annotated.save(buf, 'JPEG', quality=90)
    return {'paper_bounds_px': bounds, 'fit_error_px': round(residual, 3),
            'edge_skew_px': round(float(skew), 3), 'scan_size': list(image.size)}, buf.getvalue()


def fit_axis(low, high, size, clearance):
    center = (low+high)/2
    available = 2*min(center-max(0, low+clearance), min(size, high-clearance)-center)
    if available < size*.75:
        raise ValueError('Correction would shrink the strip unusually far. Review the detected paper edges')
    scale = math.floor(min(size, available)*1000/size)/10
    # Round to renderer pixels, then ensure the complete PNG meets both boundaries.
    while scale >= 75:
        length = int(size*scale/100+.5)
        position = round(center-length/2)
        if position >= max(0, low+clearance) and position+length <= min(size, high-clearance):
            return round(scale, 1), position-(size-length)//2, [position-low, high-position-length]
        scale = round(scale-.1, 1)
    raise ValueError('No safe strip placement fits the measured paper')


class ScanAlignment:
    def __init__(self, engine): self.engine = engine

    def target(self, ident):
        latest = self.engine.calibration_print.latest()
        if not latest or latest['id'] != ident or latest.get('kind') != 'scan_alignment':
            raise ValueError('Prepare a scan-alignment target first; this target is no longer current')
        return latest, self.engine.calibration_print.directory(ident)

    @staticmethod
    def read_state(directory):
        path = directory/'scan-state.json'
        return json.loads(path.read_text()) if path.exists() else {'strips': {}, 'proposal': None}

    def status(self):
        target = self.engine.calibration_print.latest()
        if not target or target.get('kind') != 'scan_alignment': return {'target': None, 'strips': {}, 'proposal': None}
        directory = self.engine.calibration_print.directory(target['id'])
        state = self.read_state(directory)
        return {'target': {key: target[key] for key in ('id', 'status', 'url')}, **state}

    def upload(self, ident, strip, content):
        self.engine.calibration_print.idle()
        target, directory = self.target(ident)
        if target['status'] not in ('submitted', 'acknowledged_without_retry'):
            raise ValueError('Print this calibration target before uploading its scans')
        if type(strip) is not int or strip not in (1, 2, 3, 4): raise ValueError('Choose strip 1–4')
        state = self.read_state(directory); state['proposal'] = None
        # A failed replacement also invalidates the old measurement for this strip.
        state['strips'].pop(str(strip), None); save_json(directory/'scan-state.json', state)
        measurement, preview = analyze_scan(content, target['scan_markers'][strip-1])
        scan_id = uuid.uuid4().hex
        atomic_bytes(directory/f'scan-{scan_id}.original', content)
        atomic_bytes(directory/f'scan-{scan_id}.jpg', preview)
        record = {**measurement, 'scan_id': scan_id, 'sha256': hashlib.sha256(content).hexdigest(),
                  'preview_url': f'/api/scan-alignment/{ident}/preview/{scan_id}.jpg'}
        state['strips'][str(strip)] = record; save_json(directory/'scan-state.json', state)
        return self.status()

    def propose(self, candidate):
        self.engine.calibration_print.idle()
        if not isinstance(candidate, dict) or set(candidate) != {'id', 'clearance_mm'}: raise ValueError('Choose a target and border clearance')
        target, directory = self.target(candidate['id'])
        clearance = candidate['clearance_mm']
        if type(clearance) not in (int, float) or not 0 <= clearance <= 3: raise ValueError('Border clearance must be 0–3 mm')
        state = self.read_state(directory)
        if set(state['strips']) != {'1', '2', '3', '4'}: raise ValueError('Upload all four numbered scans first')
        settings, measurements = [], []
        for i in range(4):
            left, top, right, bottom = state['strips'][str(i+1)]['paper_bounds_px']
            sx, dx, horizontal = fit_axis(left, right, 600, clearance*300/25.4)
            sy, dy, vertical = fit_axis(top, bottom, 1800, clearance*300/25.4)
            settings.append({'scale_x_percent': sx, 'offset_x_px': dx, 'scale_y_percent': sy, 'offset_y_px': dy})
            old = target['overlay_settings'][i]
            w = int(600*old['scale_x_percent']/100+.5); h = int(1800*old.get('scale_y_percent', 100)/100+.5)
            x = (600-w)//2+old['offset_x_px']; y = (1800-h)//2+old.get('offset_y_px', 0)
            measurements.append({'before_margins_mm': [round(v*25.4/300, 2) for v in (x-left, right-x-w, y-top, bottom-y-h)],
                                 'after_margins_mm': [round(v*25.4/300, 2) for v in horizontal+vertical]})
        validate_overlay_settings(settings)
        state['proposal'] = {'id': uuid.uuid4().hex, 'settings': settings, 'measurements': measurements,
                             'clearance_mm': clearance, 'created_at': time.time(),
                             'scans': {key: value['scan_id'] for key, value in state['strips'].items()}, 'applied': False}
        save_json(directory/'scan-state.json', state)
        return self.status()

    def apply(self, candidate):
        self.engine.calibration_print.idle()
        if not isinstance(candidate, dict) or set(candidate) != {'id', 'proposal_id'}: raise ValueError('Choose the displayed proposal')
        target, directory = self.target(candidate['id']); state = self.read_state(directory)
        proposal = state.get('proposal')
        if not proposal or proposal['id'] != candidate['proposal_id'] or proposal['scans'] != {k: v['scan_id'] for k, v in state['strips'].items()}:
            raise ValueError('Scans or proposal changed; calculate and review again')
        if any(self.engine.config['printer'].get(k) != target['printer'].get(k) for k in ('queue', 'options')):
            raise ValueError('Printer configuration changed; print and scan a new target')
        current = self.engine.overlay_settings
        if current != target['overlay_settings'] and current != proposal['settings']:
            raise ValueError('Strip alignment changed since this target was prepared; prepare and scan a new target')
        self.engine.save_overlay_settings(proposal['settings'])
        proposal.update(applied=True, applied_at=time.time()); save_json(directory/'scan-state.json', state)
        return self.status()
