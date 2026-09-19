"""Disconnected/blocked native operations modelled without USB or prints."""
import copy
import os
import queue
import socket
import threading
import unittest
from unittest.mock import MagicMock, patch
import app
from app import create_app
from application_control import ApplicationControl
from camera import CameraWorker, GPhotoCamera
from storage import ProcessLock, save_json
from test_stripshot import eventually
import test_software_app


class USBReleaseTests(unittest.TestCase):
    def worker(self, exit_error=None):
        adapter = GPhotoCamera('mock-port', 'mock-serial')
        native = adapter.camera = MagicMock()
        adapter.preview_started = True
        adapter.open = MagicMock(side_effect=RuntimeError('USB disconnected'))
        adapter._set = MagicMock(side_effect=RuntimeError('USB setting unavailable'))
        native.exit.side_effect = exit_error
        worker = CameraWorker('A', adapter, queue.Queue(), mode='software', baseline_required=False)
        worker.start(); worker.join(2)
        self.assertFalse(worker.is_alive())
        native.capture.assert_not_called()
        return worker, native

    def test_settings_failure_with_successful_exit_is_not_unconfirmed_release(self):
        worker, native = self.worker()
        self.assertIsNone(worker.cleanup_error)
        self.assertIn('USB setting unavailable', worker.cleanup_warning)
        self.assertIsNone(worker.adapter.camera)
        native.exit.assert_called_once()
        self.assertEqual(worker.stage, 'closed')

    def test_failed_exit_retains_handle_and_blocks_reconnect(self):
        worker, native = self.worker(RuntimeError('exit failed'))
        self.assertIn('exit failed', worker.cleanup_error)
        self.assertIs(worker.adapter.camera, native)
        self.assertEqual(worker.stage, 'release unconfirmed')


class ShutdownRecoveryTests(unittest.TestCase):
    setUp = test_software_app.SoftwareAppTests.setUp
    tearDown = test_software_app.SoftwareAppTests.tearDown
    engine = test_software_app.SoftwareAppTests.engine

    def test_stop_and_restart_wait_for_blocked_close_with_status_and_lock(self):
        for action in ('stop', 'restart'):
            with self.subTest(action=action):
                e, cards = self.engine(start=False)
                entered, release = threading.Event(), threading.Event()
                def close():
                    entered.set()
                    if not release.wait(8): raise RuntimeError('test cleanup deadline')
                cards['A'].close = close
                e.config['kiosk_mode'] = True
                e.application_control = control = ApplicationControl(e, self.cfgpath)
                e.start(); eventually(lambda:e.phase == 'watching')
                before = copy.deepcopy(e.state)
                owner = ProcessLock(e.root)
                try:
                    with patch('application_control.os.kill') as signal, patch('application_control.os.execv') as execute:
                        control.start()
                        self.assertTrue(e.request('application_control', {'action':action}).result(2)['accepted'])
                        self.assertTrue(entered.wait(3))
                        eventually(lambda:control.state == 'blocked')
                        # HTTP stays available while the coordinator and cameras stop.
                        with patch.dict(os.environ, {'STRIPSHOT_OPERATOR_PASSWORD':'test-only-password'}):
                            client = create_app(e).test_client()
                        state = client.get('/api/kiosk/status').json
                        self.assertEqual(state['phase'], 'stopping')
                        self.assertIn('Camera A', control.status()['message'])
                        with self.assertRaises(RuntimeError): ProcessLock(e.root)
                        signal.assert_not_called(); execute.assert_not_called()
                        with self.assertRaises(RuntimeError): control.finish() if action == 'restart' else e.request('capture').result(1)
                        release.set()
                        eventually(lambda:signal.called)
                        self.assertEqual(control.state, 'closing')
                        self.assertEqual(e.cleanup_blockers(), [])
                        control.finish()
                        self.assertEqual(execute.call_count, 1 if action == 'restart' else 0)
                        self.assertEqual(e.state, before)
                        self.assertEqual(sum(c.shutters for c in cards.values()), 0)
                finally:
                    release.set(); control.close(); e.stop(); owner.close()

    def test_unconfirmed_release_keeps_operator_open_and_never_signals_restart(self):
        e, cards = self.engine(start=False)
        cards['A'].close = MagicMock(side_effect=RuntimeError('USB release failed'))
        e.config['kiosk_mode'] = True
        e.application_control = control = ApplicationControl(e, self.cfgpath)
        e.start(); eventually(lambda:e.phase == 'watching')
        try:
            with patch('application_control.os.kill') as signal, patch('application_control.os.execv') as execute:
                control.start(); e.request('application_control', {'action':'restart'}).result(2)
                eventually(lambda:control.state == 'blocked')
                self.assertIn('USB release failed', control.status()['message'])
                signal.assert_not_called(); execute.assert_not_called()
        finally: control.close()

    def test_coordinator_is_also_required_to_finish_before_restart(self):
        e, _ = self.engine(start=False); e.config['kiosk_mode'] = True; e.phase = 'error'
        control = ApplicationControl(e, self.cfgpath); control.request({'action':'restart'})
        with patch.object(e.thread, 'is_alive', return_value=True), patch('application_control.os.execv') as execute:
            with self.assertRaisesRegex(RuntimeError, 'Coordinator'): control.finish()
            execute.assert_not_called()

    def test_idle_reconnect_can_be_stopped_but_held_batch_cannot(self):
        e, _ = self.engine(start=False); e.config['kiosk_mode'] = True; e.phase = 'reconnecting'
        control = ApplicationControl(e, self.cfgpath)
        self.assertTrue(control.available())
        e.freeze(software=True)
        with self.assertRaises(ValueError): control.request({'action':'stop'})

    def test_busy_port_prevents_camera_discovery_even_with_a_different_data_directory(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0)); listener.listen()
            config={'demo':False, 'camera_mode':'software', 'port':listener.getsockname()[1],
                    'data_dir':str(self.root/'different-data'),
                    'cameras':{'A':{'serial':'test-a'},'B':{'serial':'test-b'}}}
            save_json(self.cfgpath, config)
            with patch('sys.argv', ['app.py','--config',str(self.cfgpath)]), patch('app.signal.signal'), patch('app.live_cameras') as cameras:
                with self.assertRaises(OSError): app.main()
                cameras.assert_not_called()
