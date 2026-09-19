"""One-sheet calibration printing with a durable independent submission ledger."""
import copy
import hashlib
import io
import json
import math
import re
import time
import uuid
from PIL import Image, ImageDraw, ImageFont
from printer import Printer
from qualification import validate_software_printing
from render import validate_strip_offsets, validate_vertical_offset
from storage import atomic_bytes, save_json


class CalibrationPrint:
    def __init__(self,engine):self.engine=engine;self.root=engine.root/'calibration-targets'

    def directory(self,ident):
        if not isinstance(ident,str) or not re.fullmatch('cal-[0-9a-f]{32}',ident):raise ValueError('Invalid calibration target')
        path=self.root/ident
        if not (path/'manifest.json').is_file():raise ValueError('Calibration target does not exist')
        return path

    def latest(self):
        pointer=self.root/'latest.json'
        if not pointer.exists():return None
        ident=json.loads(pointer.read_text())['id'];directory=self.directory(ident)
        record=json.loads((directory/'manifest.json').read_text())
        measurements=directory/'measurements.json'
        if measurements.exists():record['measurements']=json.loads(measurements.read_text())[-1]
        record['url']='/calibration-targets/'+ident
        return record

    def idle(self):
        if self.engine.state['current'] or self.engine.phase!='watching':raise ValueError('Wait for the current session to finish')

    def prepare(self, scan=False):
        self.idle();previous=self.latest()
        if previous and previous['status'] in ('print_intent','print_uncertain'):
            raise ValueError('Check CUPS and the physical printer, then acknowledge the uncertain calibration job first')
        printer=copy.deepcopy(self.engine.config['printer']);offsets=printer.get('strip_offsets_px',[0]*4);vertical=printer.get('sheet_offset_y_px',0)
        validate_strip_offsets(offsets);validate_vertical_offset(vertical)
        ident='cal-'+uuid.uuid4().hex;directory=self.root/ident;directory.mkdir(parents=True)
        sheet=Image.new('RGB',(2400,1800),'white')
        font=ImageFont.truetype('DejaVuSans.ttf',27);small=ImageFont.truetype('DejaVuSans.ttf',21)
        mark=round(10*300/25.4);square=round(20*300/25.4)
        for n in range(4):
            strip=Image.new('RGB',(600,1800),'white');d=ImageDraw.Draw(strip)
            d.text((70,200),f'STRIP {n+1}',font=font,fill='black')
            d.text((70,250),ident[-8:],font=small,fill='black')
            d.text((70,300),f'X {offsets[n]:+d}px / Y {vertical:+d}px',font=small,fill='black')
            d.line((mark,650,mark,1050),fill='black',width=1)
            d.line((599-mark,650,599-mark,1050),fill='black',width=1)
            d.text((190,830),'L  <-->  R',font=font,fill='black')
            d.text((155,890),'Measure at middle',font=small,fill='black')
            d.line((180,mark,420,mark),fill='black',width=1)
            d.line((180,1799-mark,420,1799-mark),fill='black',width=1)
            d.text((160,145),'TOP: strip 1 only',font=small,fill='black')
            d.text((135,1620),'BOTTOM: strip 1 only',font=small,fill='black')
            d.rectangle((180,1200,180+square,1200+square),outline='black',width=1)
            d.text((190,1480),'20 mm square',font=small,fill='black')
            shifted=Image.new('RGB',(600,1800),'white');shifted.paste(strip,(offsets[n],vertical));sheet.paste(shifted,(600*n,0))
        extra = {}
        if scan:
            from scan_alignment import make_scan_sheet
            settings = copy.deepcopy(self.engine.overlay_settings)
            sheet, markers = make_scan_sheet(ident, settings)
            extra = {'kind': 'scan_alignment', 'scan_markers': markers, 'overlay_settings': settings,
                     'alignment_mode': 'whole_strip'}
        data=io.BytesIO();sheet.save(data,'PNG',dpi=(300,300));atomic_bytes(directory/'sheet.png',data.getvalue())
        record={'id':ident,'status':'ready','created_at':time.time(),'printer':printer,
                'strip_offsets_px':list(offsets),'sheet_offset_y_px':vertical,
                'sheet_sha256':hashlib.sha256(data.getvalue()).hexdigest(), **extra}
        save_json(directory/'manifest.json',record);save_json(self.root/'latest.json',{'id':ident})
        return self.latest()

    def print_once(self,ident):
        self.idle();directory=self.directory(ident);record=json.loads((directory/'manifest.json').read_text())
        if record['status']!='ready':raise ValueError('This target already has a print attempt; it will not be resubmitted')
        if not self.engine.config['printer']['enabled'] or not record['printer']['enabled']:
            raise ValueError('Enable live printing in the operator Output panel and prepare a new target to enable a physical calibration print')
        validate_software_printing(self.engine.config['printer'],self.engine.config['demo'])
        validate_software_printing(record['printer'],self.engine.config['demo'])
        if hashlib.sha256((directory/'sheet.png').read_bytes()).hexdigest()!=record['sheet_sha256']:
            raise ValueError('Calibration sheet hash mismatch; preserve this target and prepare a new one')
        record.update(status='print_intent',print_intent_at=time.time());save_json(directory/'manifest.json',record)
        try:
            result=Printer(record['printer']).submit(directory/'sheet.png',ident)
            record.update(result);save_json(directory/'manifest.json',record)
        except Exception as exc:
            record.update(status='print_uncertain',error=str(exc));save_json(directory/'manifest.json',record)
        return record

    def acknowledge(self,ident):
        directory=self.directory(ident);record=json.loads((directory/'manifest.json').read_text())
        if record['status'] not in ('print_intent','print_uncertain'):raise ValueError('No uncertain calibration job to acknowledge')
        record.update(status='acknowledged_without_retry',acknowledged_at=time.time());save_json(directory/'manifest.json',record)
        return record

    def measure(self,candidate):
        if not isinstance(candidate,dict) or set(candidate)!={'id','top_mm','bottom_mm','strips'}:raise ValueError('Enter top/bottom once and left/right for all four strips')
        directory=self.directory(candidate['id']);record=json.loads((directory/'manifest.json').read_text())
        if record['status'] not in ('submitted','acknowledged_without_retry'):raise ValueError('Print the target and measure that sheet before calculating corrections')
        def number(value):
            if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=50:raise ValueError('Caliper distances must be 0–50 mm')
            return value
        top=number(candidate['top_mm']);bottom=number(candidate['bottom_mm'])
        if not isinstance(candidate['strips'],list) or len(candidate['strips'])!=4:raise ValueError('Enter four left/right pairs')
        horizontal=[]
        for index,pair in enumerate(candidate['strips']):
            if not isinstance(pair,dict) or set(pair)!={'left_mm','right_mm'}:raise ValueError('Enter left and right distances')
            delta=(number(pair['right_mm'])-number(pair['left_mm']))*300/25.4/2
            horizontal.append(round(record['strip_offsets_px'][index]+delta))
        vertical=round(record.get('sheet_offset_y_px',0)+(bottom-top)*300/25.4/2)
        validate_strip_offsets(horizontal);validate_vertical_offset(vertical)
        result={'entered_at':time.time(),'measurements':candidate,'proposed':{'strip_offsets_px':horizontal,'sheet_offset_y_px':vertical}}
        path=directory/'measurements.json';history=json.loads(path.read_text()) if path.exists() else []
        save_json(path,history+[result]);return result
