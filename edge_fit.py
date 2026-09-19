"""Review-only expansion of the canonical whole-strip fit from measured edges."""
import math
from render import validate_overlay_settings


def measured_edge_fit(settings, measurements):
    validate_overlay_settings(settings)
    if not isinstance(measurements, list) or len(measurements) != 4:
        raise ValueError('Enter white-edge measurements for all four strips')
    proposal, limits = [], []
    for index, (fit, edges) in enumerate(zip(settings, measurements), 1):
        if not isinstance(edges, dict) or set(edges) != {'left','right','top','bottom'}:
            raise ValueError('Measure left, right, top and bottom white edges in millimeters')
        if any(type(v) not in (int,float) or not math.isfinite(v) or not 0 <= v <= 5 for v in edges.values()):
            raise ValueError('White edges must be between 0 and 5 mm; use 0 to leave an edge alone')
        updated, remaining = dict(fit), {}
        for size, scale, offset, low, high in ((600,'scale_x_percent','offset_x_px','left','right'),
                                             (1800,'scale_y_percent','offset_y_px','top','bottom')):
            length = int(size*fit.get(scale,100)/100+.5)
            start = (size-length)//2+fit.get(offset,0)
            grow_low, grow_high = [int(edges[e]*300/25.4+.5) for e in (low,high)]
            new_start, new_end = max(0,start-grow_low), min(size,start+length+grow_high)
            new_length = new_end-new_start
            # Use enough precision for the renderer to round back to the exact pixel.
            updated[scale] = round(100*new_length/size, 4)
            updated[offset] = new_start-(size-new_length)//2
            remaining[low] = round(max(0,grow_low-(start-new_start))*25.4/300,2)
            remaining[high] = round(max(0,grow_high-(new_end-start-length))*25.4/300,2)
        proposal.append(updated)
        limits.append({'strip': index, 'remaining_mm': remaining})
    validate_overlay_settings(proposal)
    return {'settings': proposal, 'limits': limits, 'baseline': settings}
