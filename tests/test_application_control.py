import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from app import create_app
from application_control import ApplicationControl
from storage import save_json
import test_software_app


class ApplicationControlTests(unittest.TestCase):
    setUp = test_software_app.SoftwareAppTests.setUp
    tearDown = test_software_app.SoftwareAppTests.tearDown
    engine = test_software_app.SoftwareAppTests.engine

    def controlled(self, start=False):
        e,cards=self.engine(start=start); e.config['kiosk_mode']=True
        if not start:e.phase='watching'
        e.application_control=ApplicationControl(e,self.cfgpath)
        return e,cards

    def test_stop_is_idle_only_and_closes_capture_admission(self):
        e,cards=self.controlled()
        for bad in (None,{}, {'action':'capture'}, {'action':'stop','extra':1}):
            with self.assertRaises(ValueError):e.action('application_control',bad)
        e.freeze(software=True)
        with self.assertRaises(ValueError):e.action('application_control',{'action':'stop'})
        e.state['current']=None
        e.phase='capturing'
        with self.assertRaises(ValueError):e.action('application_control',{'action':'restart'})
        e.phase='watching'; before=copy.deepcopy(e.state)
        result=e.action('application_control',{'action':'stop'})
        self.assertTrue(result['accepted']);self.assertTrue(e.stop_event.is_set())
        self.assertEqual(e.phase,'stopping');self.assertFalse(e.status()['application_control_available'])
        with self.assertRaises(ValueError):e.action('capture')
        with self.assertRaises(ValueError):e.action('application_control',{'action':'restart'})
        with patch('application_control.os.execv') as execute:e.application_control.finish();execute.assert_not_called()
        self.assertEqual(e.state,before);self.assertEqual(sum(c.shutters for c in cards.values()),0)

    def test_restart_preserves_live_or_dry_without_reopening_windows(self):
        for live in (False,True):
            e,_=self.controlled();e.config['printer']['enabled']=live
            e.action('application_control',{'action':'restart'})
            with patch('application_control.os.execv') as execute:e.application_control.finish()
            command=execute.call_args.args[1]
            self.assertIn('--live-printing' if live else '--dry-run',command)
            self.assertNotIn('--open-pages',command);self.assertNotIn('--ds40-profile',command)
            self.assertIn(str(self.cfgpath.resolve()),command)

    def test_failed_camera_cleanup_cannot_start_another_owner(self):
        e,_=self.controlled();e.action('application_control',{'action':'restart'})
        e.workers['A'].cleanup_error='USB release unconfirmed'
        with patch('application_control.os.execv') as execute:
            with self.assertRaisesRegex(RuntimeError,'cleanup'):e.application_control.finish()
            execute.assert_not_called()

    def test_operator_auth_and_token_required(self):
        e,_=self.controlled(start=True)
        with patch.dict(os.environ,{'STRIPSHOT_OPERATOR_PASSWORD':'test-only-password'}):client=create_app(e).test_client()
        auth={'Authorization':'Basic '+base64.b64encode(b'operator:test-only-password').decode()}
        self.assertEqual(client.post('/api/application-control',json={'action':'stop'}).status_code,401)
        self.assertEqual(client.post('/api/application-control',json={'action':'stop'},headers=auth).status_code,403)
        page=client.get('/operator',headers=auth)
        token=re.search(rb'name="stripshot-token" content="([^"]+)"',page.data).group(1).decode()
        self.assertEqual(client.post('/api/application-control',json={'action':'stop'},headers={**auth,'X-Stripshot-Token':token}).status_code,200)
        self.assertIn(b'application-restart',page.data);self.assertIn(b'application-stop',page.data)

    def test_real_demo_process_restarts_same_pid_then_stops_cleanly(self):
        # Isolated simulated-camera process: exercises socket, worker and lock cleanup.
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        save_json(self.cfgpath,{'demo':True,'camera_mode':'software','kiosk_mode':True,'port':port,'data_dir':str(self.root/'data')})
        auth='Basic '+base64.b64encode(b'operator:test-only-password').decode()
        def request(path,body=None,token=None):
            headers={'Authorization':auth}
            if token:headers['X-Stripshot-Token']=token
            if body is not None:headers['Content-Type']='application/json'
            with urlopen(Request(f'http://127.0.0.1:{port}'+path,headers=headers,
                                 data=json.dumps(body).encode() if body is not None else None),timeout=2) as response:
                data=response.read()
            return data if path=='/operator' else json.loads(data)
        def ready(old=None):
            deadline=time.monotonic()+25
            while time.monotonic()<deadline:
                try:
                    state=request('/api/status')
                    if state['phase']=='watching' and state['instance_id']!=old:return state
                except OSError:pass
                time.sleep(.1)
            self.fail('Demo process did not become ready')
        def token():return re.search(rb'name="stripshot-token" content="([^"]+)"',request('/operator')).group(1).decode()
        with open(self.root/'process.log','wb') as log:
            proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parents[1]/'app.py'),'--config',str(self.cfgpath)],
                env={**os.environ,'STRIPSHOT_OPERATOR_PASSWORD':'test-only-password'},stdout=log,stderr=log)
            try:
                state=ready();ident=state['instance_id'];pid=proc.pid
                settings=[{'scale_x_percent':90,'offset_x_px':4,'scale_y_percent':99,'offset_y_px':-2}]*4
                request('/api/overlay-settings',settings,token())
                root=self.root/'data'
                before={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
                self.assertTrue(request('/api/application-control',{'action':'restart'},token())['accepted'])
                state=ready(ident)
                self.assertEqual(proc.pid,pid);self.assertIsNone(proc.poll())
                self.assertEqual(state['overlay_settings'],settings);self.assertFalse(state['printing_enabled'])
                self.assertTrue(request('/api/application-control',{'action':'stop'},token())['accepted'])
                self.assertEqual(proc.wait(timeout=20),0)
                after={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
                self.assertEqual(before,after)
                with self.assertRaises(OSError):request('/api/status')
            finally:
                if proc.poll() is None:proc.terminate();proc.wait(timeout=20)
