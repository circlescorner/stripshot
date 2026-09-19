import base64
import copy
import json
import os
import re
import unittest
from unittest.mock import patch
from app import create_app
from qualification import DS40_OPTIONS, DS40_OFFSETS, validate_software_printing
from printer_quality import QUALITY_BASELINE, QUALITY_CONTEXT, QUALITY_FIELDS, QUALITY_VALUES, validate_quality, driver_choices, verify_driver
from printer import Printer
from screen_settings import defaults, validate_screens
from edge_fit import measured_edge_fit
import test_software_app


class QualityAndScreensTests(unittest.TestCase):
    setUp = test_software_app.SoftwareAppTests.setUp
    tearDown = test_software_app.SoftwareAppTests.tearDown
    engine = test_software_app.SoftwareAppTests.engine

    def qualified(self, start=False):
        self.cfg['demo'] = False
        self.cfg['printer'].update(queue='DNP_DS40', options=dict(DS40_OPTIONS),
            strip_offsets_px=list(DS40_OFFSETS), enabled=True, software_print_authorized=True)
        e,cards=self.engine(start=start)
        if not start:e.phase='watching'
        return e,cards

    def test_quality_save_persists_without_shutters_jobs_or_alignment_change(self):
        e,cards=self.qualified()
        original=copy.deepcopy(e.config['printer']); alignment=copy.deepcopy(e.overlay_settings)
        chosen={**QUALITY_BASELINE,'StpBrightness':'1100','StpSaturation':'900'}
        with patch('printer.Printer.submit',side_effect=AssertionError('No printing')):
            e.action('printer_quality',chosen)
        self.assertEqual(e.config['printer']['quality'],chosen)
        self.assertEqual(e.overlay_settings,alignment)
        self.assertEqual(e.config['printer']['options'],DS40_OPTIONS)
        self.assertTrue(e.config['printer']['enabled'])
        self.assertEqual(sum(c.shutters for c in cards.values()),0)
        frozen=e.freeze(software=True);batch=copy.deepcopy(e.state['current'])
        with self.assertRaises(ValueError):e.action('printer_quality',QUALITY_BASELINE)
        restarted,_=self.qualified()
        self.assertEqual(restarted.config['printer']['quality'],chosen)
        self.assertEqual(restarted.state['current'],batch)
        self.assertEqual(json.loads(e.quality_path.read_text()),chosen)

    def test_quality_missing_support_invalid_value_failed_save_and_unqualified_rejected(self):
        e,_=self.qualified();before=copy.deepcopy(e.config)
        for value in ({}, {**QUALITY_BASELINE,'copies':'2'}, {**QUALITY_BASELINE,'StpContrast':'Custom.1.5'}, {**QUALITY_BASELINE,'StpBrightness':True}):
            with self.assertRaises(ValueError):e.action('printer_quality',value)
        with patch('printer_quality.driver_choices',return_value={}):
            with self.assertRaises(ValueError):e.action('printer_quality',QUALITY_BASELINE)
        with patch('operator_tools.save_json',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):e.action('printer_quality',{**QUALITY_BASELINE,'StpBrightness':'1200'})
        self.assertEqual(e.config,before)
        for key,value in (('PageSize','B7'),('copies','2'),('StpBrightness','1100')):
            invalid=copy.deepcopy(before['printer']);invalid['options'][key]=value
            with self.assertRaises(ValueError):validate_software_printing(invalid)
        for key in ('software_print_authorized','operator_calibration_authorized'):
            invalid=copy.deepcopy(before['printer']);invalid[key]=False
            if key=='operator_calibration_authorized':invalid['strip_offsets_px']=[1,2,3,4]
            with self.assertRaises(ValueError):validate_software_printing(invalid)
        invalid=copy.deepcopy(before['printer']);invalid['quality']['StpBrightness']='Raw'
        with self.assertRaises(ValueError):validate_software_printing(invalid)

    def test_submission_uses_frozen_quality_once_and_legacy_profile_is_unchanged(self):
        e,_=self.qualified();e.action('printer_quality',{**QUALITY_BASELINE,'StpContrast':'1200'})
        e.freeze(software=True);frozen=copy.deepcopy(e.state['current']['printer'])
        e.config['printer']['quality']['StpContrast']='900'
        with patch('printer.subprocess.run') as run:
            run.return_value.returncode=0;run.return_value.stdout='request id is DNP_DS40-7 (1 file(s))'
            Printer(frozen).submit('test.png','test')
            command=run.call_args.args[0]
            self.assertIn('StpContrast=1200',command);self.assertNotIn('StpContrast=900',command)
            self.assertIn('PageSize=w432h576-div4',command);self.assertEqual(command.count('-n'),1)
            self.assertIn('StpFineContrast=None',command);self.assertEqual(run.call_count,1)
            del frozen['quality'];run.reset_mock();Printer(frozen).submit('test.png','legacy')
            self.assertFalse(any('StpContrast=' in str(v) for v in run.call_args.args[0]))
        e.config['printer']['enabled']=False;e.state['current']=None
        e.action('printer_quality',QUALITY_BASELINE)
        self.assertFalse(e.config['printer']['enabled'])

    def test_printer_and_screen_api_authentication(self):
        e,_=self.qualified(start=True);e.config['kiosk_mode']=True
        with patch.dict(os.environ,{'STRIPSHOT_OPERATOR_PASSWORD':'test-only-password'}):client=create_app(e).test_client()
        auth={'Authorization':'Basic '+base64.b64encode(b'operator:test-only-password').decode()}
        self.assertEqual(client.get('/api/screen-settings').status_code,200)
        self.assertEqual(client.get('/api/printer-quality').status_code,401)
        token=re.search(rb'name="stripshot-token" content="([^"]+)"',client.get('/operator',headers=auth).data).group(1).decode()
        for path,body in (('/api/printer-quality',QUALITY_BASELINE),('/api/screen-settings',defaults())):
            self.assertEqual(client.post(path,json=body).status_code,401)
            self.assertEqual(client.post(path,json=body,headers=auth).status_code,403)
            self.assertEqual(client.post(path,json=body,headers={**auth,'X-Stripshot-Token':token}).status_code,200)

    def test_every_screen_style_persists_plain_text_without_capture_or_fit_changes(self):
        e,cards=self.qualified();before=copy.deepcopy(e.config);settings=defaults()
        settings['countdown_camera']='A'
        for item in settings['items'].values():item.update(font='mono',size=42,weight=700,italic=True,color='#123456',align='left',spacing=2,line_height=1.5)
        settings['items']['monitor.countdown']['text']='Ready in {count}'
        settings['items']['kiosk.ready_title']['text']='<script>plain text</script>'
        e.action('screen_settings',settings);restarted,_=self.qualified()
        self.assertEqual(restarted.screens,settings);self.assertEqual(e.config,before)
        self.assertEqual(sum(c.shutters for c in cards.values()),0)
        for key,value in (('size',float('nan')),('size',181),('color','url(x)'),('font','external'),('text','{camera.__class__}'),('text','{count:1000}')):
            bad=copy.deepcopy(settings);bad['items']['monitor.countdown'][key]=value
            with self.assertRaises(ValueError):e.action('screen_settings',bad)
        with patch('screen_settings.save_json',side_effect=OSError('full')):
            with self.assertRaises(OSError):e.action('screen_settings',defaults())
        self.assertEqual(e.screens,settings)

    def test_measured_edges_share_existing_fit_and_never_crop_or_auto_save(self):
        e,cards=self.qualified()
        e.overlay_settings=[dict(scale_x_percent=90,offset_x_px=0,scale_y_percent=95,offset_y_px=0) for _ in range(4)]
        baseline=copy.deepcopy(e.overlay_settings)
        measures=[dict(left=1,right=2,top=.5,bottom=1) for _ in range(4)]
        result=e.action('edge_preview',{'baseline':baseline,'measurements':measures})
        proposed=result['settings'][0]
        # 540px wide grows 12px left and 24px right; its center shifts right 6px.
        self.assertEqual(proposed['scale_x_percent'],96)
        self.assertEqual(proposed['offset_x_px'],6)
        self.assertEqual(e.overlay_settings,baseline)
        self.assertFalse(e.overlay_settings_path.exists())
        limited=measured_edge_fit(baseline,[dict(left=5,right=5,top=5,bottom=5)]*4)
        self.assertEqual(limited['settings'][0]['scale_x_percent'],100)
        self.assertGreater(limited['limits'][0]['remaining_mm']['left'],0)
        self.assertEqual(sum(c.shutters for c in cards.values()),0)
        for measures in ([],[dict(left=-1,right=0,top=0,bottom=0)]*4,[dict(left=True,right=0,top=0,bottom=0)]*4):
            with self.assertRaises(ValueError):measured_edge_fit(baseline,measures)
        e.overlay_settings[0]['offset_x_px']=1
        with self.assertRaisesRegex(ValueError,'changed'):e.action('edge_preview',{'baseline':baseline,'measurements':measures})
        e.freeze(software=True)
        with self.assertRaisesRegex(ValueError,'session'):e.action('edge_preview',{})


class DriverParsingTests(unittest.TestCase):
    def test_actual_driver_choices_and_fails_closed(self):
        from pathlib import Path
        with patch('printer_quality.subprocess.run') as run:
            run.return_value.returncode=0
            run.return_value.stdout=(Path(__file__).parent/'fixtures/ds40-options.txt').read_text()
            choices=driver_choices('DNP_DS40');verify_driver(QUALITY_BASELINE,choices)
            for field in QUALITY_FIELDS:self.assertTrue(set(QUALITY_VALUES)<=choices[field])
            self.assertEqual(run.call_args.args[0],['lpoptions','-p','DNP_DS40','-l'])
            run.return_value.returncode=1
            with self.assertRaises(ValueError):driver_choices('DNP_DS40')
            with self.assertRaises(ValueError):driver_choices('Other')
