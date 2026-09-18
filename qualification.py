"""Explicit opt-in to the physically accepted DS40 configuration."""
DS40_OPTIONS = {
    'PageSize': 'w432h576-div4', 'Resolution': '300dpi', 'ColorModel': 'RGB',
    'StpLaminate': 'Glossy', 'StpiShrinkOutput': 'Crop',
    'StpNoCutWaste': 'False', 'orientation-requested': '4',
}
DS40_OFFSETS = [20, 15, 6, -2]


def validate_software_printing(printer, demo=False):
    if not printer.get('enabled'):
        return
    if (demo or printer.get('software_print_authorized') is not True
            or printer.get('queue') != 'DNP_DS40'
            or printer.get('options') != DS40_OPTIONS
            or printer.get('strip_offsets_px') != DS40_OFFSETS):
        raise ValueError('Software printing remains disabled without explicit authorization and the accepted DS40 qualification profile')
