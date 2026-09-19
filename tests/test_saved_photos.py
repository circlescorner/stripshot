import base64
import os
import unittest
from unittest.mock import patch
from app import create_app
import test_operator_tools


class SavedPhotosTests(unittest.TestCase):
    setUp=test_operator_tools.OperatorToolsTests.setUp
    tearDown=test_operator_tools.OperatorToolsTests.tearDown
    engine=test_operator_tools.OperatorToolsTests.engine
    completed=test_operator_tools.OperatorToolsTests.completed

    def test_gallery_shows_location_and_originals_without_mutating_them(self):
        e,cards=self.engine(start=False);source=self.completed(e)
        original=(source/'A01.jpg').read_bytes()
        client=create_app(e).test_client()
        page=client.get('/photos')
        self.assertEqual(page.status_code,200)
        self.assertIn(str(e.root/'batches').encode(),page.data)
        self.assertIn(('/photos/'+source.name+'/A01.jpg').encode(),page.data)
        with client.get('/photos/'+source.name+'/A01.jpg') as response:
            self.assertEqual(response.data,original)
        self.assertEqual((source/'A01.jpg').read_bytes(),original)
        self.assertEqual(sum(c.shutters for c in cards.values()),0)
        self.assertEqual(client.get('/photos/'+source.name+'/manifest.json').status_code,404)
        self.assertEqual(client.get('/photos/batch-'+'b'*32+'/A01.jpg').status_code,404)

    def test_gallery_requires_operator_auth_and_removed_storage_api_is_gone(self):
        e,_=self.engine(start=False);e.config['kiosk_mode']=True
        with patch.dict(os.environ,{'STRIPSHOT_OPERATOR_PASSWORD':'test-only-password'}):client=create_app(e).test_client()
        self.assertEqual(client.get('/photos').status_code,401)
        auth={'Authorization':'Basic '+base64.b64encode(b'operator:test-only-password').decode()}
        self.assertEqual(client.get('/photos',headers=auth).status_code,200)
        page=client.get('/operator',headers=auth).data
        self.assertIn(b'View saved photos and finished sheets',page)
        self.assertNotIn(b'storage-location-form',page)
        self.assertNotIn(b'storage-form',page)
        self.assertNotIn(b'retention-form',page)
        for action in ('storage_settings','storage_location','storage_export','storage_retention'):
            with self.assertRaisesRegex(ValueError,'Unknown action'):e.action(action,{})
