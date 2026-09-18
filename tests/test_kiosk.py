import base64
import copy
import os
import re
import unittest
from unittest.mock import patch

from app import create_app
from config import load_config
from storage import save_json
from qualification import DS40_OPTIONS, DS40_OFFSETS
import test_software_app
from test_stripshot import eventually


class KioskTests(unittest.TestCase):
    setUp = test_software_app.SoftwareAppTests.setUp
    tearDown = test_software_app.SoftwareAppTests.tearDown
    engine = test_software_app.SoftwareAppTests.engine

    def app(self, engine):
        engine.config['kiosk_mode'] = True
        with patch.dict(os.environ, {'STRIPSHOT_OPERATOR_PASSWORD': 'test-only-password'}):
            return create_app(engine)

    def test_guest_can_only_capture_and_see_reduced_status(self):
        e, _ = self.engine()
        client = self.app(e).test_client()
        page = client.get('/')
        self.assertIn(b'id="go"', page.data)
        self.assertNotIn(b'Change PNG', page.data)
        token = re.search(rb'name="stripshot-token" content="([^"]+)"', page.data).group(1).decode()
        headers = {'X-Stripshot-Token': token}
        for path in ('/operator','/api/status','/api/printer','/overlays/1.png'):
            self.assertEqual(client.get(path).status_code, 401)
        for action in ('reset','resume_capture','abandon_capture','retry','acknowledge'):
            self.assertEqual(client.post('/api/'+action, headers=headers).status_code, 401)
        self.assertEqual(client.post('/api/capture').status_code,403)
        self.assertEqual(client.post('/api/capture',headers=headers).status_code,200)
        self.assertNotEqual(client.post('/api/capture',headers=headers).status_code,200)
        eventually(lambda: e.status()['last'] is not None)
        status = client.get('/api/kiosk/status').get_json()
        self.assertNotIn('current',status)
        self.assertNotIn('last',status)
        self.assertNotIn('error',status)
        self.assertTrue(status['ready'])

    def test_operator_requires_password_and_own_csrf(self):
        e,_ = self.engine()
        client = self.app(e).test_client()
        guest = re.search(rb'name="stripshot-token" content="([^"]+)"',client.get('/').data).group(1).decode()
        auth = {'Authorization':'Basic '+base64.b64encode(b'operator:test-only-password').decode()}
        page = client.get('/operator',headers=auth)
        self.assertEqual(page.status_code,200)
        self.assertIn(b'Change PNG',page.data)
        operator = re.search(rb'name="stripshot-token" content="([^"]+)"',page.data).group(1).decode()
        self.assertNotEqual(guest,operator)
        self.assertEqual(client.post('/api/reset',headers={**auth,'X-Stripshot-Token':guest}).status_code,403)
        self.assertEqual(client.post('/api/reset',headers={**auth,'X-Stripshot-Token':operator}).status_code,200)

    def test_kiosk_fails_closed_without_operator_password(self):
        e,_ = self.engine(start=False)
        e.config['kiosk_mode']=True
        with patch.dict(os.environ, {'STRIPSHOT_OPERATOR_PASSWORD':''}):
            with self.assertRaisesRegex(ValueError,'PASSWORD'):
                create_app(e)

    def live_config(self):
        self.cfg['demo']=False
        self.cfg['cameras']={'A':{'serial':'A'},'B':{'serial':'B'}}
        self.cfg['printer']={'enabled':True,'software_print_authorized':True,
                             'queue':'DNP_DS40','options':copy.deepcopy(DS40_OPTIONS),
                             'strip_offsets_px':list(DS40_OFFSETS)}

    def test_qualified_batch_one_spool_submission_and_restart_no_reprint(self):
        self.live_config()
        with patch('printer.subprocess.run') as submit:
            submit.return_value.returncode=0
            submit.return_value.stdout='request id is DNP_DS40-99 (1 file(s))\n'
            submit.return_value.stderr=''
            e,cards=self.engine()
            client=self.app(e).test_client()
            token=re.search(rb'name="stripshot-token" content="([^"]+)"',client.get('/').data).group(1).decode()
            self.assertEqual(client.post('/api/capture',headers={'X-Stripshot-Token':token}).status_code,200)
            eventually(lambda:e.status()['last'] is not None)
            self.assertEqual(e.status()['last']['job_id'],'DNP_DS40-99')
            self.assertEqual([cards[c].shutters for c in ('A','B')],[8,8])
            self.assertEqual(submit.call_count,1)
            self.assertIn('number-up=1',submit.call_args.args[0])
            e.stop()
            restarted,newcards=self.engine()
            self.assertEqual(submit.call_count,1)
            self.assertEqual(sum(c.shutters for c in newcards.values()),0)

    def test_uncertain_live_submission_holds_without_retry(self):
        self.live_config()
        with patch('printer.subprocess.run',side_effect=TimeoutError('uncertain')) as submit:
            e,_=self.engine()
            e.request('capture').result(5)
            eventually(lambda:e.status()['phase']=='print_uncertain')
            e.stop()
            restarted,_=self.engine(phase='print_uncertain')
            with self.assertRaises(ValueError):restarted.request('capture').result(5)
            self.assertEqual(submit.call_count,1)

    def test_unqualified_profile_and_demo_live_rejected(self):
        self.live_config()
        save_json(self.cfgpath,self.cfg)
        self.assertTrue(load_config(self.cfgpath)['printer']['enabled'])
        for change in ({'queue':'other'},{'strip_offsets_px':[0]*4},{'software_print_authorized':False}):
            cfg=copy.deepcopy(self.cfg);cfg['printer'].update(change);save_json(self.cfgpath,cfg)
            with self.assertRaises(ValueError):load_config(self.cfgpath)
        self.cfg['demo']=True;save_json(self.cfgpath,self.cfg)
        with self.assertRaises(ValueError):load_config(self.cfgpath)
