"""Operator calibration and paper-free rendering of completed originals."""
import copy
import hashlib
import json
import time
import uuid
from render import (render_sheet, validate_strip_offsets, validate_vertical_offset,
                    default_overlay_settings, validate_overlay_settings)
from storage import atomic_bytes, save_json
from qualification import validate_software_printing


class OperatorTools:
    def initialize_operator_tools(self):
        # Retain the historical storage name as the single alignment setting.
        # New renders apply this fit to the combined photos and PNG.
        self.overlay_settings_path = self.root / 'operator-overlays.json'
        self.overlay_settings = (json.loads(self.overlay_settings_path.read_text())
                                 if self.overlay_settings_path.exists() else default_overlay_settings())
        validate_overlay_settings(self.overlay_settings)
        self.calibration_path = self.root / 'operator-calibration.json'
        # Preserve legacy offsets/profile authorization for historical recovery;
        # whole_strip renders do not apply these photo-only translations.
        if self.calibration_path.exists():
            self.apply_calibration(json.loads(self.calibration_path.read_text()), persist=False)
        self.session_path = self.root / 'operator-session.json'
        self.countdown_seconds = self.config.get('countdown_seconds', 0)
        if self.session_path.exists():
            self.countdown_seconds = json.loads(self.session_path.read_text())['countdown_seconds']
        self.validate_countdown(self.countdown_seconds)
        self.quality_path = self.root / 'operator-printer-quality.json'
        from printer_quality import QUALITY_BASELINE, validate_quality
        from qualification import DS40_OPTIONS
        if self.quality_path.exists():
            quality = json.loads(self.quality_path.read_text())
            validate_quality(quality)
            self.config['printer']['quality'] = quality
        elif self.config['printer'].get('queue') == 'DNP_DS40' and self.config['printer'].get('options') == DS40_OPTIONS:
            self.config['printer'].setdefault('quality', copy.deepcopy(QUALITY_BASELINE))
        self.next_photo = None
        self.round_number = None

    def save_overlay_settings(self, candidate):
        candidate = copy.deepcopy(candidate)
        validate_overlay_settings(candidate)
        with self.lock:
            save_json(self.overlay_settings_path, candidate)
            self.overlay_settings = candidate

    @staticmethod
    def validate_countdown(seconds):
        if type(seconds) is not int or not 0 <= seconds <= 10:
            raise ValueError('Countdown must be a whole number from 0 to 10 seconds')

    def save_session(self, candidate):
        if not isinstance(candidate,dict) or set(candidate) != {'countdown_seconds'}:
            raise ValueError('Session settings need countdown_seconds')
        self.validate_countdown(candidate['countdown_seconds'])
        with self.lock:
            save_json(self.session_path,candidate)
            self.countdown_seconds = candidate['countdown_seconds']

    def apply_calibration(self, candidate, persist=True):
        if not isinstance(candidate,dict) or not {'strip_offsets_px'} <= set(candidate) or set(candidate)-{'strip_offsets_px','sheet_offset_y_px'}:
            raise ValueError('Calibration needs four strip offsets')
        validate_strip_offsets(candidate['strip_offsets_px'])
        printer = copy.deepcopy(self.config['printer'])
        vertical=candidate.get('sheet_offset_y_px',printer.get('sheet_offset_y_px',0))
        validate_vertical_offset(vertical)
        printer['sheet_offset_y_px']=vertical
        candidate={**candidate,'sheet_offset_y_px':vertical}
        printer.update(strip_offsets_px=list(candidate['strip_offsets_px']),
                       operator_calibration_authorized=True)
        if self.software:
            validate_software_printing(printer,self.config['demo'])
        if persist:
            with self.lock:
                save_json(self.calibration_path,candidate)
                self.config['printer'] = printer
        else:
            self.config['printer'] = printer

    def set_printing(self, candidate):
        if not isinstance(candidate, dict) or set(candidate) != {'enabled'} or type(candidate['enabled']) is not bool:
            raise ValueError('Printing setting needs enabled: true or false')
        with self.lock:
            if not self.software or self.config['demo']:
                raise ValueError('Live printing requires real cameras in software capture mode')
            if self.phase != 'watching' or self.state['current'] or any(not f.done() for f in self.capture_futures):
                raise ValueError('Change printing only between sessions, with no active or held batch')
            printer = copy.deepcopy(self.config['printer'])
            printer.update(enabled=candidate['enabled'], software_print_authorized=candidate['enabled'])
            validate_software_printing(printer, self.config['demo'])
            # Run through the coordinator: no batch can freeze halfway through.
            # This is a runtime choice; never rewrite startup settings or old batches.
            from printer import Printer
            self.config['printer'] = printer
            self.printer = Printer(printer)
            return {'printing_enabled': printer['enabled']}

    def save_printer_quality(self, candidate):
        from printer_quality import validate_quality, verify_driver, driver_choices
        from qualification import DS40_OPTIONS
        from printer import Printer
        validate_quality(candidate)
        with self.lock:
            if (self.phase != 'watching' or self.state['current']
                    or any(not f.done() for f in self.capture_futures)):
                raise ValueError('Save printer quality only between sessions, with no active or held batch')
            printer = copy.deepcopy(self.config['printer'])
            if printer.get('queue') != 'DNP_DS40' or printer.get('options') != DS40_OPTIONS:
                raise ValueError('Photo quality requires the qualified DS40 media and cut profile')
            verify_driver(candidate, driver_choices(printer['queue']))
            printer['quality'] = copy.deepcopy(candidate)
            if self.software:
                validate_software_printing(printer, self.config['demo'])
            save_json(self.quality_path, candidate)
            self.config['printer'] = printer
            self.printer = Printer(printer)
        return {'saved': copy.deepcopy(candidate)}

    def render_dry_run(self):
        with self.lock:
            if self.state['current'] or self.phase != 'watching':
                raise ValueError('Wait until the current session is finished before rendering a dry run')
            batch = copy.deepcopy(self.state['last'])
            if not batch or batch.get('stage') != 'complete':
                raise ValueError('Complete one photo session first; dry run reuses its sixteen saved originals')
            layout = copy.deepcopy(self.layout)
            overlay_settings = copy.deepcopy(self.overlay_settings)
            offsets = list(self.config['printer'].get('strip_offsets_px',[0]*4))
            vertical = self.config['printer'].get('sheet_offset_y_px',0)
        source = self.root / 'batches' / batch['id']
        photos = {c:[source/f'{c}{n:02d}.jpg' for n in range(1,9)] for c in ('A','B')}
        hashes = {}
        for c, paths in photos.items():
            for index,path in enumerate(paths):
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
                if batch.get('software') and actual != batch['shots'][c][index].get('sha256'):
                    raise ValueError('Saved original hash mismatch; preserve evidence and inspect this batch')
                hashes[path.name] = actual
        ident = 'dry-' + uuid.uuid4().hex
        output = self.root / 'dry-runs' / ident
        output.mkdir(parents=True)
        overlays=[]
        for n in range(1,5):
            path=self.root/'overlays'/f'strip{n}.png'
            target=output/f'overlay{n}.png'
            if path.exists(): atomic_bytes(target,path.read_bytes()); overlays.append(target)
            else: overlays.append(None)
        render_sheet(photos,overlays,layout,output/'sheet.png',strip_offsets_px=offsets,
                     sheet_offset_y_px=vertical,overlay_settings=overlay_settings,alignment_mode='whole_strip')
        save_json(output/'manifest.json',{'id':ident,'source_batch':batch['id'],
                  'created_at':time.time(),'layout':layout,'strip_offsets_px':offsets,'sheet_offset_y_px':vertical,
                  'original_hashes':hashes,'overlays':[p.name if p else None for p in overlays],
                  'overlay_settings':overlay_settings,
                  'alignment_mode':'whole_strip',
                  'status':'render_only_no_capture_no_print'})
        return {'id':ident,'url':'/dry-runs/'+ident}

    def monitor_status(self):
        with self.lock:
            current=self.state['current']
            active=bool(current)
            return {'active':active, 'phase':self.phase,
                    'previews':{c:{**w.preview_status(),'failed':bool(w.failure)} for c,w in self.workers.items()},
                    'round':self.round_number if active else None,
                    'countdown_remaining':max(0,self.next_photo-time.monotonic())
                      if active and self.phase == 'capturing' and self.next_photo is not None else None}
