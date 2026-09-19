"""Plain-text, locally persisted styling for guest screens; no executable markup."""
import copy
import json
import math
import re
import string
from storage import save_json

FONTS = {'sans': 'Arial, Helvetica, sans-serif', 'serif': 'Georgia, serif',
         'system': 'system-ui, sans-serif', 'mono': 'monospace',
         'rounded': '"Trebuchet MS", sans-serif', 'display': 'Impact, sans-serif',
         'cursive': 'cursive'}
FIELDS = {'monitor.brand': ('Live view · heading', 'MalanaphyVickWedding', 30),
 'monitor.loading': ('Live view · initial loading', 'Waiting for camera {camera}…', 36),
 'monitor.disconnected': ('Live view · connection lost', 'Reconnecting — please wait', 36),
 'monitor.unavailable': ('Live view · preview unavailable',
                         'Camera {camera} preview unavailable — check the operator dashboard',
                         36),
 'monitor.holding': ('Live view · other camera during capture', 'MalanaphyVick Wedding', 36),
 'monitor.paused': ('Live view · session paused', 'Session paused — please ask the attendant', 36),
 'monitor.rendering': ('Live view · making strips', 'Making your strips…', 36),
 'monitor.countdown': ('Live view · countdown', '{count} — get ready!', 36),
 'monitor.capturing': ('Live view · taking photo', 'Taking photo {round} of 8…', 36),
 'monitor.footer': ('Live view · camera label', 'CAMERA {camera}', 14),
 'monitor.fullscreen': ('Live view · full screen button', 'Full screen', 14),
 'monitor.recovery_connection': ('Live view · reconnecting detail', 'Reconnecting to server…', 14),
 'monitor.recovery_failed': ('Live view · camera failure detail', 'Camera failure — check operator', 14),
 'monitor.recovery_browser': ('Live view · display recovery detail', 'Recovering browser display…', 14),
 'monitor.recovery_waiting': ('Live view · waiting detail', 'Waiting for camera preview', 14),
 'kiosk.brand': ('Kiosk · heading', 'MalanaphyVickWedding', 18),
 'kiosk.mode': ('Kiosk · dry-run label', 'Practice mode · no printing', 16),
 'kiosk.go': ('Kiosk · start button', 'Go', 48),
 'kiosk.hint': ('Kiosk · start hint', 'Press Space or tap Go', 20),
 'kiosk.count': ('Kiosk · photo progress', '{camera}: {count} / 8', 32),
 'kiosk.ready_title': ('Kiosk · ready title', 'Have fun. Be wierd.', 76),
 'kiosk.ready_detail': ('Kiosk · ready description', 'Eight photos. Two cameras. Four keepsakes.', 30),
 'kiosk.printed_detail': ('Kiosk · submitted description',
                          'Your photos were sent to the printer. Collect your strips below.',
                          30),
 'kiosk.capture_title': ('Kiosk · taking photos title', 'Look at the cameras!', 76),
 'kiosk.capture_detail': ('Kiosk · taking photos description',
                          'Keep posing — we’ll take eight photos on each camera.',
                          30),
 'kiosk.render_title': ('Kiosk · making sheets title', 'Making your keepsakes', 76),
 'kiosk.render_detail': ('Kiosk · making sheets description',
                         'Please wait. Your session is in progress.',
                         30),
 'kiosk.loading_title': ('Kiosk · loading title', 'Getting ready', 76),
 'kiosk.loading_detail': ('Kiosk · loading description', 'Please wait a moment.', 30),
 'kiosk.paused_title': ('Kiosk · paused title', 'Please ask the attendant', 76),
 'kiosk.paused_detail': ('Kiosk · paused description', 'Your session is safely paused.', 30),
 'kiosk.uncertain_title': ('Kiosk · checking session title', 'Please ask the attendant', 76),
 'kiosk.uncertain_detail': ('Kiosk · checking session description',
                            'We are checking whether your session started.',
                            30),
 'kiosk.disconnected_title': ('Kiosk · reconnecting title', 'Reconnecting', 76),
 'kiosk.disconnected_detail': ('Kiosk · reconnecting description',
                               'Please wait, or ask the attendant if this continues.',
                               30)}

def defaults():
    result = {}
    for key, (label, text, size) in FIELDS.items():
        result[key] = {'text': text, 'font': 'serif' if key.startswith('kiosk.') and key.endswith('_title') else 'sans',
            'size': size, 'weight': 700 if key.endswith('.brand') else 400, 'italic': False,
            'color': '#ffffff' if key.startswith('monitor.') or key == 'kiosk.go' else '#203a2a',
            'background': 'transparent', 'align': 'center', 'spacing': 0, 'line_height': 1.3}
    return {'countdown_camera': 'B', 'items': result}


def validate_screens(value):
    baseline = defaults()
    if not isinstance(value, dict) or set(value) != set(baseline) or value['countdown_camera'] not in ('A','B'):
        raise ValueError('Choose camera A or B for the countdown')
    items = value['items']
    if not isinstance(items, dict) or set(items) != set(FIELDS):
        raise ValueError('Screen settings need every displayed text item')
    for key, item in items.items():
        if not isinstance(item, dict) or set(item) != set(baseline['items'][key]):
            raise ValueError('Invalid text style: ' + key)
        if not isinstance(item['text'], str) or len(item['text']) > 500:
            raise ValueError('Each screen message must be at most 500 characters')
        allowed = {name for _, name, _, _ in string.Formatter().parse(FIELDS[key][1]) if name}
        try:
            for _, name, spec, conversion in string.Formatter().parse(item['text']):
                if name is not None and (name not in allowed or spec or conversion):
                    raise ValueError('Use only the listed placeholders for ' + key)
        except ValueError as exc:
            raise ValueError('Invalid message placeholders for ' + key) from exc
        if not isinstance(item['font'],str) or item['font'] not in FONTS or item['align'] not in ('left','center','right') or type(item['italic']) is not bool:
            raise ValueError('Choose a listed font and alignment')
        if type(item['weight']) is not int or item['weight'] not in (400,700):
            raise ValueError('Choose regular or bold text')
        for name, low, high in (('size',8,180),('spacing',-2,20),('line_height',.8,3)):
            v = item[name]
            if type(v) not in (int,float) or not math.isfinite(v) or not low <= v <= high:
                raise ValueError('Text style outside its allowed range: ' + name)
        for name in ('color','background'):
            if not isinstance(item[name], str) or not (re.fullmatch(r'#[0-9a-fA-F]{6}',item[name]) or name=='background' and item[name]=='transparent'):
                raise ValueError('Choose a six-digit color or transparent background')


class ScreenSettings:
    def initialize_screens(self):
        self.screens_path = self.root / 'operator-screens.json'
        self.screens = json.loads(self.screens_path.read_text()) if self.screens_path.exists() else defaults()
        validate_screens(self.screens)

    def save_screens(self, candidate):
        validate_screens(candidate)
        with self.lock:
            save_json(self.screens_path, candidate)
            self.screens = copy.deepcopy(candidate)
        return {'saved': copy.deepcopy(candidate)}
