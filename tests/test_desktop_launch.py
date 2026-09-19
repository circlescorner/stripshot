import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import desktop_launch as desktop


class DesktopLaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / 'photos'; self.data.mkdir()
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps({'demo':True, 'camera_mode':'software', 'data_dir':str(self.data), 'port':8090}))
    def tearDown(self): self.temp.cleanup()

    def test_existing_kiosk_only_opens_operator_and_never_starts_owner(self):
        with patch.object(desktop,'running',return_value=True), patch.object(desktop,'open_pages') as pages, patch.object(desktop.os,'execvpe') as execute:
            self.assertEqual(desktop.main(['--config',str(self.config)]),0)
            self.assertTrue(pages.call_args.kwargs['operator_only'])
            execute.assert_not_called()

    def test_start_reuses_config_and_does_not_enable_printing(self):
        with patch.object(desktop,'running',return_value=False), patch.object(desktop.socket,'socket'), patch.object(desktop.getpass,'getpass',return_value='private-test-password'), patch.dict(os.environ,{'STRIPSHOT_OPERATOR_PASSWORD':''}), patch.object(desktop.os,'execvpe',side_effect=RuntimeError('exec boundary')) as execute:
            with self.assertRaisesRegex(RuntimeError,'exec boundary'):desktop.main(['--config',str(self.config)])
            command=execute.call_args.args[1]
            self.assertIn('--open-pages',command)
            self.assertNotIn('--live-printing',command)
            self.assertNotIn('--ds40-profile',command)
            self.assertIn(str(self.config),command)
            self.assertEqual(execute.call_args.args[2]['STRIPSHOT_OPERATOR_PASSWORD'],'private-test-password')
        self.assertEqual(list(self.data.iterdir()),[])

    def test_missing_data_stops_before_password_or_exec(self):
        cfg=json.loads(self.config.read_text());cfg['data_dir']=str(self.root/'missing');self.config.write_text(json.dumps(cfg))
        with patch.object(desktop,'running',return_value=False), patch.object(desktop.socket,'socket'), patch.object(desktop.getpass,'getpass') as password, patch.object(desktop.os,'execvpe') as execute:
            with self.assertRaisesRegex(ValueError,'folder is missing'):desktop.main(['--config',str(self.config)])
            password.assert_not_called();execute.assert_not_called()
        self.assertFalse((self.root/'missing').exists())

    def test_busy_port_stops_without_camera_start(self):
        with patch.object(desktop,'running',return_value=False), patch.object(desktop.socket,'socket') as sock, patch.object(desktop.os,'execvpe') as execute:
            sock.return_value.__enter__.return_value.bind.side_effect=OSError('in use')
            with self.assertRaisesRegex(RuntimeError,'already occupied'):desktop.main(['--config',str(self.config)])
            execute.assert_not_called()

    def test_second_click_while_password_pending_starts_nothing(self):
        with open(self.root/'.stripshot-desktop.lock','a+') as lock:
            desktop.fcntl.flock(lock,desktop.fcntl.LOCK_EX | desktop.fcntl.LOCK_NB)
            with patch.object(desktop,'running',return_value=False), patch.object(desktop.os,'execvpe') as execute:
                self.assertEqual(desktop.main(['--config',str(self.config)]),0)
                execute.assert_not_called()

    def test_browser_windows_keep_guest_profile_separate(self):
        with patch.object(desktop.shutil,'which',return_value='/usr/bin/firefox'), patch.object(desktop.subprocess,'Popen') as popen:
            desktop.open_pages('http://127.0.0.1:8090',self.root/'browser')
            self.assertEqual(popen.call_count,2)
            self.assertEqual(popen.call_args_list[0].args[0],['xdg-open','http://127.0.0.1:8090/operator'])
            command=popen.call_args_list[1].args[0]
            self.assertIn('--no-remote',command)
            for path in ('/kiosk','/view/A','/view/B'):self.assertIn('http://127.0.0.1:8090'+path,command)
            self.assertNotIn('http://127.0.0.1:8090/operator',command)

    def test_page_opening_waits_for_server_without_retrying_start(self):
        with patch.object(desktop,'running',side_effect=[False,True]) as probe, patch.object(desktop.time,'sleep'), patch.object(desktop,'open_pages') as pages:
            desktop.open_when_ready('http://127.0.0.1:8090',self.root/'browser')
            self.assertEqual(probe.call_count,2);pages.assert_called_once()
