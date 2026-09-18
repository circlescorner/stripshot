"""Small, explicit configuration; physical printing is opt-in."""
import json
from pathlib import Path


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
    cfg.setdefault('layout', {'margin': 24, 'gap': 18, 'top': 24, 'bottom': 180})
    cfg.setdefault('host', '127.0.0.1')
    cfg.setdefault('port', 8080)
    cfg.setdefault('preview_fps', 0)
    if type(cfg['preview_fps']) not in (int, float) or not 0 <= cfg['preview_fps'] <= 5:
        raise ValueError('preview_fps must be between 0 (disabled) and 5')
    if 0 < cfg['preview_fps'] < 1:
        raise ValueError('Enabled preview_fps must be at least 1')
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
    if cfg['camera_mode'] == 'software' and cfg['printer']['enabled']:
        raise ValueError('Software capture printing is disabled pending hardware qualification')
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
    from render import validate_layout
    validate_layout(cfg['layout'])
    return cfg
