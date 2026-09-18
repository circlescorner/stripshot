import base64
import copy
import os
import re
import time
import unittest
from unittest.mock import patch
from app import create_app
from config import validate_preview_fps
import test_software_app
from test_stripshot import eventually


class PreviewSettingsTests(unittest.TestCase):
    setUp = test_software_app.SoftwareAppTests.setUp
    tearDown = test_software_app.SoftwareAppTests.tearDown
    engine = test_software_app.SoftwareAppTests.engine

    def test_saved_rate_applies_to_both_workers_restart_and_frame_header(self):
        self.cfg['preview_fps'] = 3
        e, cards = self.engine()
        e.request('preview_settings', {'fps':10}).result(5)
        self.assertEqual(e.status()['preview_fps'], 10)
        self.assertTrue(all(w.preview_fps == 10 for w in e.workers.values()))
        self.assertEqual(create_app(e).test_client().get('/api/preview/A.jpg').headers['X-Preview-FPS'],'10')
        start = e.workers['A'].frame_sequence
        eventually(lambda: e.workers['A'].frame_sequence >= start+5, timeout=2)
        self.assertEqual(sum(c.shutters for c in cards.values()), 0)
        e.stop()
        restarted, _ = self.engine(start=False)
        self.assertEqual(restarted.config['preview_fps'], 10)
        self.assertTrue(all(w.preview_fps == 10 for w in restarted.workers.values()))
        self.assertEqual(restarted.reconnected_adapter(restarted.workers['A']), restarted.workers['A'].adapter)

    def test_invalid_busy_and_failed_save_leave_rate_unchanged(self):
        self.cfg['preview_fps'] = 3
        e, _ = self.engine(start=False); e.phase = 'watching'
        for candidate in (None, {}, {'fps':0}, {'fps':16}, {'fps':True}, {'fps':float('nan')}, {'fps':'5'}, {'fps':5,'extra':1}):
            with self.assertRaises(ValueError): e.action('preview_settings',candidate)
        with patch('batch.save_json',side_effect=OSError('disk full')):
            with self.assertRaises(OSError): e.action('preview_settings',{'fps':5})
        e.freeze(software=True)
        frozen = copy.deepcopy(e.state['current'])
        with self.assertRaises(ValueError): e.action('preview_settings',{'fps':5})
        self.assertEqual(e.state['current'],frozen)
        self.assertEqual(e.config['preview_fps'],3)
        self.assertTrue(all(w.preview_fps == 3 for w in e.workers.values()))

    def test_operator_authentication_and_csrf_required(self):
        self.cfg.update(preview_fps=3,kiosk_mode=True)
        e,_=self.engine()
        with patch.dict(os.environ, {'STRIPSHOT_OPERATOR_PASSWORD':'test-only-password'}):
            client=create_app(e).test_client()
        self.assertEqual(client.post('/api/preview-settings',json={'fps':5}).status_code,401)
        auth={'Authorization':'Basic '+base64.b64encode(b'operator:test-only-password').decode()}
        self.assertEqual(client.post('/api/preview-settings',headers=auth,json={'fps':5}).status_code,403)
        page=client.get('/operator',headers=auth)
        token=re.search(rb'name="stripshot-token" content="([^"]+)"',page.data).group(1).decode()
        self.assertEqual(client.post('/api/preview-settings',json={'fps':5},headers={**auth,'X-Stripshot-Token':token}).status_code,200)
        self.assertEqual(e.config['preview_fps'],5)

    def test_configuration_bounds_preserve_disabled_default(self):
        for value in (0,1,3,5,10,15): validate_preview_fps(value)
        for value in (-1,.5,16,float('inf'),False):
            with self.assertRaises(ValueError): validate_preview_fps(value)
