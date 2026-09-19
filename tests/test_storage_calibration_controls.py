import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from storage import ProcessLock, save_json
from storage_location import StorageLease, schedule_location, inventory
from photo_storage import PhotoStorage, DEFAULT
from qualification import DS40_OPTIONS, DS40_OFFSETS
import test_software_app


class StorageMigrationTests(unittest.TestCase):
    def test_migration_preserves_held_state_and_blocks_both_owners(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'old';root.mkdir();dest=Path(tmp)/'new'
            save_json(root/'state.json',{'current':{'stage':'capture_held','intent':'uncertain'}})
            (root/'original.jpg').write_bytes(b'exact bytes')
            before=inventory(root);schedule_location(root,str(dest))
            owner=ProcessLock(root)
            with self.assertRaises(RuntimeError):StorageLease({'data_dir':str(root)})
            self.assertFalse(dest.exists());owner.close()
            cfg={'data_dir':str(root)};lease=StorageLease(cfg)
            self.assertEqual(cfg['data_dir'],str(dest))
            for name,identity in before.items():self.assertEqual(inventory(dest)[name],identity)
            self.assertEqual((root/'original.jpg').read_bytes(),b'exact bytes')
            for location in (root,dest):
                with self.assertRaises(RuntimeError):StorageLease({'data_dir':str(location)})
            lease.close()
            direct=StorageLease({'data_dir':str(dest)})
            with self.assertRaises(RuntimeError):ProcessLock(root,allow_redirect=True)
            direct.close()

    def test_destination_race_preserves_existing_and_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'old';root.mkdir();dest=Path(tmp)/'new'
            (root/'evidence').write_bytes(b'preserve');schedule_location(root,str(dest));dest.mkdir()
            (dest/'foreign').write_text('do not replace')
            with self.assertRaises(ValueError):StorageLease({'data_dir':str(root)})
            self.assertEqual((dest/'foreign').read_text(),'do not replace')
            self.assertFalse((root/'storage-redirect.json').exists())

    def test_symlink_and_incomplete_destination_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'old';root.mkdir();dest=Path(tmp)/'new'
            (root/'linked').symlink_to('/etc/hosts');schedule_location(root,str(dest))
            with self.assertRaises(RuntimeError):StorageLease({'data_dir':str(root)})
            self.assertFalse(dest.exists())
            dest.mkdir();save_json(dest/'storage-incomplete.json',{})
            with self.assertRaises(RuntimeError):StorageLease({'data_dir':str(dest)})

    def test_export_no_overwrite_and_manual_review_never_deletes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'data';root.mkdir();dest=Path(tmp)/'backup';dest.mkdir()
            storage=PhotoStorage(root);settings={**DEFAULT,'enabled':True,'folder':str(dest),'originals':False}
            storage.save(settings)
            batch={'id':'batch-test','stage':'complete','completed_at':1,'storage':copy.deepcopy(storage.settings)}
            source=root/'batches'/batch['id'];source.mkdir(parents=True)
            save_json(source/'manifest.json',batch);(source/'sheet.png').write_bytes(b'sheet')
            record={'id':'batch-test','batch_id':batch['id'],'settings':copy.deepcopy(storage.settings)}
            storage.copy_job(record);copied=Path(record['destination'])/'sheet.png'
            self.assertEqual(copied.read_bytes(),b'sheet')
            copied.write_bytes(b'foreign')
            with self.assertRaisesRegex(RuntimeError,'overwrite'):storage.copy_job(record)
            storage.review({'note':'Keep all wedding originals'})
            self.assertEqual((source/'sheet.png').read_bytes(),b'sheet')


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
        for action in ('storage_settings','storage_location','storage_cancel','storage_retention','calibration_prepare','calibration_print','calibration_measure'):
            path='/api/operator-tools/'+action
            self.assertEqual(client.post(path,json={}).status_code,401)
            self.assertEqual(client.post(path,json={},headers=auth).status_code,403)
        page=client.get('/operator',headers=auth)
        token=re.search(rb'name="stripshot-token" content="([^"]+)"',page.data).group(1).decode()
        headers={**auth,'X-Stripshot-Token':token}
        self.assertEqual(client.post('/api/operator-tools/storage_cancel',json={},headers=headers).status_code,200)
        self.assertEqual(client.post('/api/operator-tools/calibration_prepare',json={},headers=headers).status_code,200)
        for ident in (b'storage-cancel',b'storage-migration-status',b'calibration-print',b'caliper-form'):
            self.assertIn(ident,page.data)

    def test_disabled_print_gate_and_storage_frozen(self):
        e,cards=self.engine(start=False);e.phase='watching'
        target=e.action('calibration_prepare')
        with patch('calibration_print.Printer.submit') as submit:
            with self.assertRaises(ValueError):e.action('calibration_print',{'id':target['id']})
            submit.assert_not_called()
        e.freeze(software=True);frozen=copy.deepcopy(e.state['current']['storage'])
        e.action('storage_settings',{**DEFAULT,'name':'Wedding'})
        self.assertEqual(e.state['current']['storage'],frozen)
        self.assertEqual(sum(c.shutters for c in cards.values()),0)

class MigrationRebootTests(unittest.TestCase):
    def test_inconsistent_ancestral_alias_never_opens_old_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            old=Path(tmp)/'old';old.mkdir();new=Path(tmp)/'new';new.mkdir()
            save_json(new/'storage-origin.json',{'source':str(old)})
            save_json(old/'state.json',{'old':'state'})
            with self.assertRaisesRegex(RuntimeError,'inconsistent'):StorageLease({'data_dir':str(new)})


    def test_missing_tmp_alias_is_recreated_without_new_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            old=Path(tmp)/'removed-tmp-alias';new=Path(tmp)/'permanent';new.mkdir()
            save_json(new/'storage-origin.json',{'source':str(old)})
            save_json(new/'state.json',{'held':'unchanged'})
            lease=StorageLease({'data_dir':str(new)})
            self.assertFalse((old/'state.json').exists())
            self.assertEqual(json.loads((old/'storage-redirect.json').read_text())['destination'],str(new))
            with self.assertRaises(RuntimeError):ProcessLock(old,allow_redirect=True)
            lease.close()
