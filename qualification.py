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
    from render import validate_strip_offsets, validate_vertical_offset
    validate_strip_offsets(printer.get('strip_offsets_px'))
    validate_vertical_offset(printer.get('sheet_offset_y_px',0))
    if (demo or printer.get('software_print_authorized') is not True
            or printer.get('queue') != 'DNP_DS40'
            or printer.get('options') != DS40_OPTIONS
            or ((printer.get('strip_offsets_px') != DS40_OFFSETS or printer.get('sheet_offset_y_px',0)!=0)
                and printer.get('operator_calibration_authorized') is not True)):
        raise ValueError('Software printing remains disabled without explicit authorization and the accepted DS40 qualification profile')
