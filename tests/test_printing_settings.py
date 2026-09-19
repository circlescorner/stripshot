import base64
import copy
import json
import re
import unittest
from concurrent.futures import Future
from unittest.mock import patch

import test_kiosk
from test_stripshot import eventually


class PrintingSettingsTests(unittest.TestCase):
    setUp = test_kiosk.KioskTests.setUp
    tearDown = test_kiosk.KioskTests.tearDown
    engine = test_kiosk.KioskTests.engine
    app = test_kiosk.KioskTests.app
    live_config = test_kiosk.KioskTests.live_config

    def configured(self, start=True):
        self.live_config()
        self.cfg['printer'].update(enabled=False, software_print_authorized=False,
                                   strip_offsets_px=[26,16,6,-2], sheet_offset_y_px=2,
                                   operator_calibration_authorized=True)
        return self.engine(start=start)

    def test_toggle_is_idle_only_strict_and_preserves_calibration_and_data(self):
        e, cards = self.configured(start=False)
        e.phase = 'watching'
        original = copy.deepcopy(e.config['printer'])
        with patch('printer.subprocess.run', side_effect=AssertionError('No printing on mode change')):
            for invalid in (None, {}, {'enabled':1}, {'enabled':'true'}, {'enabled':True,'extra':0}):
                with self.assertRaises(ValueError): e.action('printing_settings',invalid)
            for phase in ('capturing','rendering','submitting','capture_held','print_uncertain','error','reconnecting'):
                e.phase = phase
                self.assertFalse(e.status()['printing_change_available'])
                with self.assertRaises(ValueError): e.action('printing_settings',{'enabled':True})
            e.phase = 'watching'
            e.state['current'] = {'stage':'preparing'}
            with self.assertRaises(ValueError): e.action('printing_settings',{'enabled':True})
            e.state['current'] = None
            e.capture_futures = [Future()]
            with self.assertRaises(ValueError): e.action('printing_settings',{'enabled':True})
            e.capture_futures = []
            for enabled in (True, True, False, False):
                self.assertEqual(e.action('printing_settings',{'enabled':enabled}),{'printing_enabled':enabled})
                self.assertEqual(e.status()['printing_enabled'],enabled)
                self.assertEqual(e.printer.config['enabled'],enabled)
                self.assertEqual(e.config['printer']['strip_offsets_px'],original['strip_offsets_px'])
                self.assertEqual(e.config['printer']['sheet_offset_y_px'],2)
                self.assertEqual(e.config['printer']['options'],original['options'])
            self.assertEqual(sum(c.shutters for c in cards.values()),0)
            self.assertFalse((e.root/'batches').exists())
        restarted,_ = self.configured(start=False)
        self.assertFalse(restarted.status()['printing_enabled'])

    def test_demo_and_unqualified_printer_cannot_enable(self):
        e,_ = self.engine(start=False)
        e.phase = 'watching'
        with self.assertRaises(ValueError): e.action('printing_settings',{'enabled':True})
        e,_ = self.configured(start=False)
        e.phase = 'watching'
        e.config['printer']['queue'] = 'other'
        with self.assertRaises(ValueError): e.action('printing_settings',{'enabled':True})
        self.assertFalse(e.status()['printing_enabled'])
        e.config['camera_mode'] = 'events';e.software = False
        with self.assertRaises(ValueError): e.action('printing_settings',{'enabled':True})

    def test_operator_auth_and_token_required_and_guest_status_updates(self):
        e,_ = self.configured()
        client = self.app(e).test_client()
        auth = {'Authorization':'Basic '+base64.b64encode(b'operator:test-only-password').decode()}
        guest = re.search(rb'name="stripshot-token" content="([^"]+)"',client.get('/').data).group(1).decode()
        page = client.get('/operator',headers=auth)
        self.assertIn(b'id="printing-toggle"',page.data)
        token = re.search(rb'name="stripshot-token" content="([^"]+)"',page.data).group(1).decode()
        endpoint = '/api/printing-settings'
        self.assertEqual(client.post(endpoint,json={'enabled':True},headers={'X-Stripshot-Token':guest}).status_code,401)
        for wrong in ('',guest):
            self.assertEqual(client.post(endpoint,json={'enabled':True},headers={**auth,'X-Stripshot-Token':wrong}).status_code,403)
        for enabled in (True,False):
            response = client.post(endpoint,json={'enabled':enabled},headers={**auth,'X-Stripshot-Token':token})
            self.assertEqual(response.status_code,200)
            self.assertEqual(client.get('/api/kiosk/status').get_json()['printing_enabled'],enabled)

    def test_only_new_live_batch_prints_once_old_dry_batches_unchanged(self):
        e,_ = self.configured()
        with patch('printer.subprocess.run') as submit:
            submit.return_value.returncode=0
            submit.return_value.stdout='request id is DNP_DS40-99 (1 file(s))\n'
            submit.return_value.stderr=''
            results=[]
            for enabled in (False,True,False):
                e.request('printing_settings',{'enabled':enabled}).result(5)
                previous = e.status()['last']
                e.request('capture').result(5)
                eventually(lambda:e.status()['last'] is not None and e.status()['last'] != previous)
                results.append(e.status()['last'])
            self.assertEqual([r['status'] for r in results],['dry_run','submitted','dry_run'])
            self.assertEqual(submit.call_count,1)
            old=json.loads((e.root/'batches'/results[0]['id']/'manifest.json').read_text())
            self.assertEqual(old['status'],'dry_run')
            self.assertFalse(old['printer']['enabled'])
            self.assertEqual(old['printer']['strip_offsets_px'],[26,16,6,-2])
