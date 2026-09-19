"""A narrow DS40 quality allowlist; media and geometry stay in qualification.py."""
import copy
import os
import subprocess

# Discrete choices verified against DS40 CUPS+Gutenprint 5.3.4. Avoid raw/custom
# options: they can bypass color processing or accept ambiguous driver values.
QUALITY_FIELDS = {
    'StpBrightness': ('Brightness', 'Overall lightness of the printed photo.'),
    'StpContrast': ('Contrast', 'Separation between light and dark tones.'),
    'StpSaturation': ('Saturation', 'Color intensity; lower values make colors more muted.'),
    'StpCyanGamma': ('Cyan tone', 'Cyan channel gamma. Adjust only to correct a visible color cast.'),
    'StpMagentaGamma': ('Magenta tone', 'Magenta channel gamma. Adjust only to correct a visible color cast.'),
    'StpYellowGamma': ('Yellow tone', 'Yellow channel gamma. Adjust only to correct a visible color cast.'),
}
QUALITY_VALUES = tuple('None' if n == 1000 else str(n) for n in range(500, 1600, 100))
QUALITY_BASELINE = {key: 'None' for key in QUALITY_FIELDS}
# Freeze the existing driver's baseline processing, including fine adjustments.
# Otherwise queue-wide defaults could silently stack with the chosen values.
QUALITY_CONTEXT = {
    'StpColorCorrection': 'None', 'StpImageType': 'Photo', 'StpGamma': 'None',
    'StpFineGamma': 'None', 'StpColorPrecision': 'Normal',
    'StpLegacyDyesubGamma': 'False', 'StpLinearContrast': 'False',
    **{'StpFine' + key[3:]: 'None' for key in QUALITY_FIELDS},
    **{key: 'None' for key in ('StpCyanBalance', 'StpMagentaBalance', 'StpYellowBalance',
                              'StpFineCyanBalance', 'StpFineMagentaBalance', 'StpFineYellowBalance')},
}


def validate_quality(value):
    if (not isinstance(value, dict) or set(value) != set(QUALITY_FIELDS)
            or any(type(v) is not str or v not in QUALITY_VALUES for v in value.values())):
        raise ValueError('Choose supported DS40 photo-quality values; media and geometry cannot be changed here')


def driver_choices(queue):
    if queue != 'DNP_DS40':
        raise ValueError('Photo quality controls require the qualified DNP_DS40 queue')
    result = subprocess.run(['lpoptions', '-p', queue, '-l'], capture_output=True,
                            text=True, timeout=5, env={**os.environ, 'LC_ALL': 'C'})
    if result.returncode:
        raise ValueError('Cannot read DS40 driver options; saved quality settings were not changed')
    choices = {}
    for line in result.stdout.splitlines():
        if '/' in line and ': ' in line:
            key = line.split('/', 1)[0]
            choices[key] = {v.lstrip('*') for v in line.split(': ', 1)[1].split()}
    return choices


def verify_driver(quality, choices):
    validate_quality(quality)
    for key, value in {**QUALITY_CONTEXT, **quality}.items():
        if value not in choices.get(key, set()):
            raise ValueError('DS40 driver does not support the saved quality profile: ' + key)


def quality_menu(printer):
    saved = copy.deepcopy(printer.get('quality', QUALITY_BASELINE))
    menu = {'saved': saved, 'baseline': dict(QUALITY_BASELINE), 'fields': [], 'available': False}
    try:
        choices = driver_choices(printer.get('queue'))
        verify_driver(saved, choices)
        for key, (label, description) in QUALITY_FIELDS.items():
            menu['fields'].append({'key': key, 'label': label, 'description': description,
                'values': [{'value': v, 'label': '1.0 · baseline' if v == 'None' else f'{int(v)/1000:.1f}'}
                           for v in QUALITY_VALUES if v in choices.get(key, set())]})
        menu['available'] = True
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        menu['error'] = str(exc)
    return menu
