#!/usr/bin/env python3
"""One desktop entry: reuse a running kiosk or start it and open its pages."""
import argparse
import fcntl
import getpass
import json
import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen
from config import load_config


def running(base_url):
    try:
        with urlopen(base_url + '/api/kiosk/status', timeout=1) as response:
            status = json.load(response)
        return isinstance(status, dict) and status.get('application') == 'stripshot' and status.get('kiosk_mode') is True
    except (OSError, ValueError, URLError):
        return False


def occupied_port_message(base_url, port):
    # Report listener identity only; never inspect environment/arguments or kill
    # a process based on its port. A failed HTTP probe does not prove an orphan.
    owners = []
    try:
        result = subprocess.run(['ss', '-ltnp', f'sport = :{port}'],
                                capture_output=True, text=True, timeout=2)
        owners = sorted(set(re.findall(r'\("([^"\n]+)",pid=(\d+),', result.stdout)))
    except (OSError, subprocess.TimeoutExpired):
        pass
    identity = ', '.join(f'PID {pid} ({name})' for name, pid in owners) or 'the listener could not be identified'
    return (f'The kiosk port {port} is already occupied; {identity}. '
            f'The existing service did not answer as Stripshot. Open {base_url}/operator and check '
            'the existing Stripshot terminal: it may be starting, stopping, or waiting on a camera. '
            'If another program owns the port, resolve that conflict before starting. '
            'No cameras were opened and no process was stopped.')


def open_pages(base_url, profile, operator_only=False):
    subprocess.Popen(['xdg-open', base_url + '/operator'], start_new_session=True)
    if operator_only:
        return
    profile = Path(profile)
    profile.mkdir(parents=True, exist_ok=True)
    urls = [base_url + path for path in ('/kiosk', '/view/A', '/view/B')]
    if shutil.which('firefox'):
        command = ['firefox', '--no-remote', '--profile', str(profile)]
        for url in urls:
            command += ['--new-window', url]
        subprocess.Popen(command, start_new_session=True)
    else:
        browser = shutil.which('chromium') or shutil.which('google-chrome')
        if not browser:
            print('Install Firefox or Chromium to open guest windows. Links are on the operator page.', flush=True)
            return
        for url in urls:
            subprocess.Popen([browser, '--no-first-run', '--user-data-dir=' + str(profile),
                              '--new-window', url], start_new_session=True)


def open_when_ready(base_url, profile):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if running(base_url):
            try:
                open_pages(base_url, profile)
            except OSError as exc:
                print('Could not open browser pages: ' + str(exc), flush=True)
            return
        time.sleep(.5)
    print('Browser startup timed out. Check this terminal; no restart was attempted.', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--live-printing', action='store_true', help='Explicitly enable future session prints')
    args = parser.parse_args(argv)
    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    if config['host'] not in ('127.0.0.1', 'localhost') or config['camera_mode'] != 'software':
        raise ValueError('Desktop startup requires a loopback software-camera configuration')
    base = 'http://127.0.0.1:' + str(config['port'])
    profile = config_path.parent / 'guest-browser'
    if running(base):
        print('Stripshot is already running. Opening its operator page; no second owner started.', flush=True)
        open_pages(base, profile, operator_only=True)
        return 0
    # Covers repeated clicks while the first window is still asking for a password.
    with open(config_path.parent / '.stripshot-desktop.lock', 'a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if running(base):
                open_pages(base, profile, operator_only=True)
            print('An existing Stripshot launch owns the desktop lock. Check its terminal and '
                  + base + '/operator; it may be starting or stopping. No second owner started.', flush=True)
            return 0
        with socket.socket() as check:
            # Match the server: recently closed connections in TIME_WAIT are not
            # another listener. This never takes a port from an active listener.
            check.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                check.bind(('127.0.0.1', config['port']))
            except OSError:
                if running(base):
                    open_pages(base, profile, operator_only=True)
                    return 0
                raise RuntimeError(occupied_port_message(base, config['port'])) from None
        if not Path(config['data_dir']).is_dir():
            raise ValueError('Saved-photo folder is missing: ' + config['data_dir'] + '. No replacement was created.')
        password = os.environ.get('STRIPSHOT_OPERATOR_PASSWORD') or getpass.getpass('Operator password (at least 12 characters): ')
        if len(password) < 12:
            raise ValueError('Operator password must contain at least 12 characters')
        # Keep the launch lock through exec and the existing start-kiosk wrapper.
        os.set_inheritable(lock.fileno(), True)
        command = ['bash', str(Path(__file__).resolve().parent / 'start-kiosk'),
                   '--config', str(config_path), '--open-pages']
        if args.live_printing:
            command.append('--live-printing')
        os.execvpe('bash', command, {**os.environ, 'STRIPSHOT_PYTHON': sys.executable, 'STRIPSHOT_OPERATOR_PASSWORD': password})


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print('Stripshot could not start: ' + str(exc), file=sys.stderr, flush=True)
        raise SystemExit(1)
