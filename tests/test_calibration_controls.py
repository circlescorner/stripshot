import copy
import json
import unittest
from unittest.mock import patch
from qualification import DS40_OPTIONS, DS40_OFFSETS
import test_software_app


class CalibrationControlTests(unittest.TestCase):
    setUp=test_software_app.SoftwareAppTests.setUp
    tearDown=test_software_app.SoftwareAppTests.tearDown
    engine=test_software_app.SoftwareAppTests.engine

    def live_mock_engine(self):
        self.cfg['demo']=False
        self.cfg['printer'].update(enabled=True,software_print_authorized=True,queue='DNP_DS40',options=dict(DS40_OPTIONS),strip_offsets_px=list(DS40_OFFSETS))
        engine,cards=self.engine(start=False);engine.phase='watching'
        return engine,cards

    def test_durable_intent_uncertain_no_retry_and_no_shutters(self):
        e,cards=self.live_mock_engine();target=e.action('calibration_prepare');ident=target['id']
        path=e.calibration_print.directory(ident)/'manifest.json'
        def uncertain(*args):
            self.assertEqual(json.loads(path.read_text())['status'],'print_intent')
            raise RuntimeError('lost lp response')
        with patch('calibration_print.Printer.submit',side_effect=uncertain) as submit:
            self.assertEqual(e.action('calibration_print',{'id':ident})['status'],'print_uncertain')
            with self.assertRaises(ValueError):e.action('calibration_print',{'id':ident})
            with self.assertRaises(ValueError):e.action('calibration_prepare')
            self.assertEqual(submit.call_count,1)
        self.assertEqual(sum(c.shutters for c in cards.values()),0)
        restarted,_=self.engine(start=False);restarted.phase='watching'
        with self.assertRaises(ValueError):restarted.action('calibration_print',{'id':ident})
        restarted.action('calibration_acknowledge',{'id':ident})
        self.assertEqual(restarted.calibration_print.latest()['status'],'acknowledged_without_retry')

    def test_measurements_preview_without_apply_and_frozen_batch(self):
        e,_=self.live_mock_engine();target=e.action('calibration_prepare');ident=target['id']
        with patch('calibration_print.Printer.submit',return_value={'status':'submitted','job_id':'mock-1'}):e.action('calibration_print',{'id':ident})
        candidate={'id':ident,'top_mm':9,'bottom_mm':11,'strips':[{'left_mm':9,'right_mm':11}]*4}
        proposal=e.action('calibration_measure',candidate)['proposed']
        self.assertEqual(proposal,{'strip_offsets_px':[32,27,18,10],'sheet_offset_y_px':12})
        self.assertEqual(e.config['printer']['strip_offsets_px'],DS40_OFFSETS)
        e.freeze(software=True);frozen=copy.deepcopy(e.state['current'])
        e.action('calibration',proposal)
        self.assertEqual(e.state['current'],frozen)
        self.assertEqual(e.config['printer']['sheet_offset_y_px'],12)
        candidate['strips'][0]['left_mm']=float('nan')
        with self.assertRaises(ValueError):e.action('calibration_measure',candidate)

    def test_operator_routes_require_auth_and_csrf(self):
        import base64,os,re
        from app import create_app
        e,_=self.engine();e.config['kiosk_mode']=True
        with patch.dict(os.environ,{'STRIPSHOT_OPERATOR_PASSWORD':'test-only-password'}):client=create_app(e).test_client()
        auth={'Authorization':'Basic '+base64.b64encode(b'operator:test-only-password').decode()}
        for action in ('calibration_prepare','calibration_print','calibration_measure'):
            path='/api/operator-tools/'+action
            self.assertEqual(client.post(path,json={}).status_code,401)
            self.assertEqual(client.post(path,json={},headers=auth).status_code,403)
        page=client.get('/operator',headers=auth)
        token=re.search(rb'name="stripshot-token" content="([^"]+)"',page.data).group(1).decode()
        headers={**auth,'X-Stripshot-Token':token}
        self.assertEqual(client.post('/api/operator-tools/calibration_prepare',json={},headers=headers).status_code,200)
        for ident in (b'photo-folder',b'calibration-print',b'caliper-form'):
            self.assertIn(ident,page.data)

    def test_disabled_print_gate(self):
        e,cards=self.engine(start=False);e.phase='watching'
        target=e.action('calibration_prepare')
        with patch('calibration_print.Printer.submit') as submit:
            with self.assertRaises(ValueError):e.action('calibration_print',{'id':target['id']})
            submit.assert_not_called()
        self.assertEqual(sum(c.shutters for c in cards.values()),0)

