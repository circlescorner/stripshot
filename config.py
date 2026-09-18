"""Small, explicit configuration; physical printing is opt-in."""
import json
from pathlib import Path


def validate_preview_fps(value, allow_disabled=True):
    if type(value) not in (int, float) or not (1 <= value <= 15 or allow_disabled and value == 0):
        raise ValueError('Preview FPS must be between 1 and 15' + (' (or 0 to disable)' if allow_disabled else ''))


def load_config(path):
    path = Path(path).resolve()
    cfg = json.loads(path.read_text())
    cfg.setdefault('data_dir', 'data')
    cfg['data_dir'] = str((path.parent / cfg['data_dir']).resolve())
    cfg.setdefault('camera_mode', 'events')
    cfg.setdefault('poll_seconds', 2)
    cfg.setdefault('demo', False)
    cfg.setdefault('printer', {})
    cfg['printer'].setdefault('enabled', False)
    cfg['printer'].setdefault('queue', '')
    cfg['printer'].setdefault('options', {})
    cfg['printer'].setdefault('strip_offsets_px', [0, 0, 0, 0])
    cfg.setdefault('layout', {'margin': 24, 'gap': 18, 'top': 24, 'bottom': 180})
    cfg.setdefault('host', '127.0.0.1')
    cfg.setdefault('port', 8080)
    cfg.setdefault('preview_fps', 0)
    cfg.setdefault('kiosk_mode', False)
    cfg.setdefault('auto_reconnect', True)
    if type(cfg['auto_reconnect']) is not bool:
        raise ValueError('auto_reconnect must be true or false')
    if type(cfg['kiosk_mode']) is not bool:
        raise ValueError('kiosk_mode must be true or false')
    if cfg['kiosk_mode'] and (cfg['camera_mode'] != 'software' or cfg['host'] not in ('127.0.0.1', 'localhost')):
        raise ValueError('Kiosk requires software mode and loopback-only host')
    validate_preview_fps(cfg['preview_fps'])
    if cfg['camera_mode'] not in ('events', 'poll', 'software'):
        raise ValueError('camera_mode must be events, poll or software')
    if not 0.25 <= cfg['poll_seconds'] <= 60:
        raise ValueError('poll_seconds must be between 0.25 and 60')
    if not cfg['demo']:
        cameras = cfg.get('cameras', {})
        if set(cameras) != {'A', 'B'}:
            raise ValueError('Configure cameras A and B with their serial numbers')
        serials = [cameras[c].get('serial', '').strip() for c in ('A', 'B')]
        if not all(serials) or serials[0] == serials[1]:
            raise ValueError('Two different camera serial numbers are required')
    if cfg['camera_mode'] == 'software':
        from qualification import validate_software_printing
        validate_software_printing(cfg['printer'], cfg['demo'])
    if cfg['demo'] and cfg['printer']['enabled']:
        raise ValueError('Demo mode cannot enable physical printing')
    if cfg['printer']['enabled'] and not cfg['printer']['queue']:
        raise ValueError('An explicit CUPS queue is required')
    options = cfg['printer']['options']
    if not isinstance(options, dict) or any(
        not isinstance(k, str) or not isinstance(v, (str, int))
        or any(c.isspace() for c in f'{k}{v}') or '=' in k
        for k, v in options.items()
    ):
        raise ValueError('Printer options must be simple key/value pairs')
    if any(k.lower() in ('copies', 'number-up', 'page-ranges') for k in options):
        raise ValueError('Copies, number-up and page-ranges cannot be overridden')
    from render import validate_layout, validate_strip_offsets
    validate_layout(cfg['layout'])
    validate_strip_offsets(cfg['printer']['strip_offsets_px'])
    return cfg
