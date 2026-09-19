#!/usr/bin/env python3
"""Run the operator dashboard and the single Stripshot coordinator."""
import argparse
import hmac
import json
import logging
import os
import signal
import getpass
import secrets
import time
import re
from pathlib import Path
from flask import Flask, abort, jsonify, render_template, request, send_file, Response, g
from werkzeug.exceptions import HTTPException
from batch import Engine
from camera import DemoCamera, discover, live_cameras
from config import load_config
from storage import ProcessLock
from preview import register_preview


def create_app(engine):
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
    register_preview(app, engine.workers, engine.config['demo'])
    token = secrets.token_urlsafe(32)
    guest_token = secrets.token_urlsafe(32)
    kiosk_mode = engine.config.get('kiosk_mode', False)
    password = os.environ.get('STRIPSHOT_OPERATOR_PASSWORD', '')
    if kiosk_mode and len(password) < 12:
        raise ValueError('Set STRIPSHOT_OPERATOR_PASSWORD to at least 12 characters for kiosk mode')

    def operator_authenticated():
        auth = request.authorization
        return bool(auth and auth.username == 'operator' and
                    hmac.compare_digest((auth.password or '').encode(), password.encode()))


    @app.before_request
    def protect_actions():
        g.request_started = time.monotonic()
        public = (request.path in ('/kiosk', '/api/kiosk/status', '/api/capture', '/favicon.ico', '/slideshow', '/api/slideshow', '/api/monitor/status')
                  or request.path.startswith(('/static/', '/view/', '/api/preview/', '/slideshow/photos/'))
                  or request.path == '/' and kiosk_mode)
        if kiosk_mode and not public and not operator_authenticated():
            return Response('Operator sign-in required', 401,
                            {'WWW-Authenticate': 'Basic realm="Stripshot operator"'})
        if request.method == 'POST':
            supplied = request.headers.get('X-Stripshot-Token', '')
            allowed = hmac.compare_digest(supplied, token)
            if request.path == '/api/capture':
                allowed = allowed or hmac.compare_digest(supplied, guest_token)
            if not allowed:
                abort(403, 'Reload the dashboard before making changes')

    @app.after_request
    def headers(response):
        elapsed = time.monotonic() - g.request_started
        if elapsed >= 1:
            app.logger.warning('Slow request %s %s: %.3fs (%s)', request.method, request.path, elapsed, response.status_code)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.errorhandler(Exception)
    def error(exc):
        code = exc.code if isinstance(exc, HTTPException) else 400 if isinstance(exc, (ValueError, RuntimeError)) else 500
        app.logger.warning('Request failed %s %s: %s', request.method, request.path, exc)
        return jsonify(error=str(exc)), code

    @app.get('/favicon.ico')
    def favicon():
        return Response(status=204)

    @app.get('/kiosk')
    def kiosk():
        if engine.config['camera_mode'] != 'software':
            abort(404)
        return render_template('kiosk.html', token=guest_token)

    @app.get('/api/kiosk/status')
    def kiosk_status():
        state = engine.status()
        return jsonify(application='stripshot', kiosk_mode=kiosk_mode, session_id=guest_token, phase=state['phase'], counts=state['counts'],
                       ready=(state['capture_mode'] == 'software' and state['phase'] == 'watching'
                              and not state['current'] and not state['capture_busy']),
                       printing_enabled=state['printing_enabled'],
                       last_id=state['last']['id'] if state['last'] else None,
                       last_status=state['last']['status'] if state['last'] else None)

    @app.get('/')
    @app.get('/operator')
    def index():
        if request.path == '/' and kiosk_mode:
            return kiosk()
        return render_template('index.html', token=token, demo=engine.config['demo'],
                               previews=bool(engine.config.get('preview_fps', 0)),
                               software=engine.config['camera_mode'] == 'software')

    @app.get('/api/status')
    def status():
        return jsonify(engine.status())

    @app.get('/api/printer')
    def printer():
        return jsonify(engine.printer.cached_details())

    @app.post('/api/<action>')
    def action(action):
        if action not in ('reset', 'acknowledge', 'retry', 'demo', 'capture', 'resume_capture', 'abandon_capture', 'reconnect'):
            abort(404)
        if action in ('reset', 'demo') and engine.status()['phase'] != 'watching':
            raise ValueError('Wait until the appliance is watching')
        engine.request(action).result(timeout=130)
        return jsonify(ok=True)

    @app.get('/api/monitor/status')
    def monitor_status():
        return jsonify(engine.monitor_status())

    @app.get('/slideshow')
    def slideshow():
        return render_template('slideshow.html')

    @app.get('/api/slideshow')
    def slideshow_catalog():
        with engine.lock:
            settings = dict(engine.display)
        return jsonify(settings=settings, photos=engine.gallery.catalog(settings['source']))

    @app.get('/slideshow/photos/<batch_id>/<name>')
    def slideshow_photo(batch_id, name):
        try:
            path = engine.gallery.image(batch_id,name)
        except (OSError, ValueError):
            abort(404)
        return send_file(path,mimetype='image/jpeg')

    @app.post('/api/slideshow-settings')
    def slideshow_settings():
        engine.request('slideshow_settings',request.get_json()).result(timeout=130)
        return jsonify(ok=True)

    @app.get('/photos')
    def saved_photos():
        photos = engine.gallery.catalog('all')
        sheets = engine.gallery.catalog('sheets')
        batches = {}
        for item in photos + sheets:
            batches.setdefault(item['batch_id'], []).append(item)
        return render_template('photos.html', folder=str(engine.root / 'batches'),
                               batches=list(reversed(list(batches.items()))))

    @app.get('/photos/<batch_id>/<name>')
    def saved_original(batch_id, name):
        try:
            path = engine.gallery.original(batch_id, name)
        except (OSError, ValueError):
            abort(404)
        return send_file(path, mimetype='image/png' if name == 'sheet.png' else 'image/jpeg')

    @app.get('/api/calibration-target')
    def calibration_target():
        return jsonify(engine.calibration_print.latest())

    @app.get('/calibration-targets/<ident>/sheet.png')
    def calibration_sheet(ident):
        return send_file(engine.calibration_print.directory(ident)/'sheet.png',mimetype='image/png')

    @app.post('/api/operator-tools/<action>')
    def operator_tools_action(action):
        if action not in ('scan_prepare', 'scan_propose', 'scan_apply', 'calibration_prepare','calibration_print',
                          'calibration_measure','calibration_acknowledge'):
            abort(404)
        return jsonify(engine.request(action,request.get_json(silent=True) or {}).result(timeout=130))

    @app.get('/api/scan-alignment')
    def scan_alignment_status():
        return jsonify(engine.scan_alignment.status())

    @app.post('/api/scan-alignment/<ident>/<int:strip>')
    def scan_alignment_upload(ident, strip):
        request.max_content_length = 40 * 1024 * 1024
        if 'file' not in request.files: raise ValueError('Choose a scan file')
        return jsonify(engine.request('scan_upload', ident, strip, request.files['file'].read()).result(timeout=130))

    @app.get('/api/scan-alignment/<ident>/preview/<scan_id>.jpg')
    def scan_alignment_preview(ident, scan_id):
        if not re.fullmatch('[0-9a-f]{32}', scan_id): abort(404)
        directory = engine.calibration_print.directory(ident)
        path = directory / f'scan-{scan_id}.jpg'
        if not path.is_file(): abort(404)
        return send_file(path, mimetype='image/jpeg')

    @app.post('/api/calibration')
    def calibration():
        engine.request('calibration',request.get_json()).result(timeout=130)
        return jsonify(ok=True)

    @app.post('/api/session-settings')
    def session_settings():
        engine.request('session_settings',request.get_json()).result(timeout=130)
        return jsonify(ok=True)

    @app.post('/api/printing-settings')
    def printing_settings():
        return jsonify(engine.request('printing_settings', request.get_json()).result(timeout=130))

    @app.post('/api/application-control')
    def application_control():
        return jsonify(engine.request('application_control', request.get_json()).result(timeout=130))

    @app.post('/api/overlay-settings')
    def overlay_settings():
        engine.request('overlay_settings', request.get_json()).result(timeout=130)
        return jsonify(ok=True)

    @app.post('/api/dry-run')
    def dry_run():
        return jsonify(engine.request('dry_run').result(timeout=130))

    def dry_run_directory(ident):
        if not re.fullmatch(r'dry-[0-9a-f]{32}',ident):
            abort(404)
        directory = engine.root / 'dry-runs' / ident
        if not (directory / 'manifest.json').is_file():
            abort(404)
        return directory

    @app.get('/dry-runs/<ident>')
    def dry_run_view(ident):
        dry_run_directory(ident)
        return render_template('dry_run.html',ident=ident)

    @app.get('/dry-runs/<ident>/sheet.png')
    def dry_run_sheet(ident):
        return send_file(dry_run_directory(ident)/'sheet.png',mimetype='image/png')

    @app.post('/api/preview-settings')
    def preview_settings():
        engine.request('preview_settings', request.get_json()).result(timeout=130)
        return jsonify(ok=True)

    @app.post('/api/layout')
    def layout():
        candidate = request.get_json()
        engine.request('layout', candidate).result(timeout=130)
        return jsonify(ok=True)

    @app.post('/api/overlays/<int:index>')
    def upload(index):
        if 'file' not in request.files:
            raise ValueError('Choose a PNG overlay')
        engine.request('overlay', index, request.files['file'].read()).result(timeout=130)
        return jsonify(ok=True)

    @app.get('/overlays/<int:index>.png')
    def overlay(index):
        if index not in (1, 2, 3, 4):
            abort(404)
        path = engine.root / 'overlays' / f'strip{index}.png'
        if not path.is_file():
            return send_file(Path(app.static_folder) / 'empty-overlay.svg', mimetype='image/svg+xml')
        return send_file(path, mimetype='image/png')

    @app.get('/batches/<batch_id>/preview.jpg')
    def preview(batch_id):
        # Only the current/last batch is exposed; arbitrary file access is never accepted.
        state = engine.status()
        allowed = {b['id'] for b in (state['current'], state['last']) if b}
        if batch_id not in allowed:
            abort(404)
        path = engine.root / 'batches' / batch_id / 'preview.jpg'
        if not path.is_file():
            abort(404)
        return send_file(path, mimetype='image/jpeg')

    return app


def main():
    parser = argparse.ArgumentParser(description='Stripshot dual-camera print appliance')
    parser.add_argument('--config', default='config.json')
    parser.add_argument('--open-pages', action='store_true', help='Open operator, guest and camera pages when the server is ready')
    parser.add_argument('--discover', action='store_true', help='Read attached camera serials, then exit')
    parser.add_argument('--dev-server', action='store_true', help='Use Werkzeug for local development only')
    parser.add_argument('--kiosk', action='store_true', help='Serve the guest kiosk and protect operator controls')
    parser.add_argument('--ds40-profile', action='store_true', help='Apply the accepted DS40 calibration for new batches')
    parser.add_argument('--live-printing', action='store_true', help='Explicitly authorize one automatic print per new software batch')
    parser.add_argument('--dry-run', action='store_true', help='Keep printing disabled, including after an operator restart')
    args = parser.parse_args()
    if args.live_printing and args.dry_run: parser.error('Choose live printing or dry run, not both')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    if args.discover:
        print(json.dumps(discover(), indent=2))
        return
    config = load_config(args.config)
    if args.kiosk:
        config['kiosk_mode'] = True
    if config.get('kiosk_mode'):
        if config['camera_mode'] != 'software' or config['host'] not in ('127.0.0.1', 'localhost'):
            raise ValueError('Kiosk requires software mode on loopback only')
        if not os.environ.get('STRIPSHOT_OPERATOR_PASSWORD'):
            os.environ['STRIPSHOT_OPERATOR_PASSWORD'] = getpass.getpass('Operator password (at least 12 characters): ')
        if len(os.environ['STRIPSHOT_OPERATOR_PASSWORD']) < 12:
            raise ValueError('Operator password must contain at least 12 characters')
    if args.ds40_profile:
        from qualification import DS40_OPTIONS, DS40_OFFSETS
        config['printer'].update(queue='DNP_DS40', options=dict(DS40_OPTIONS), strip_offsets_px=list(DS40_OFFSETS))
    if args.dry_run:
        config['printer'].update(enabled=False, software_print_authorized=False)
    if args.live_printing:
        if not config.get('kiosk_mode') or config['demo']:
            raise ValueError('Live printing requires a real-camera kiosk configuration')
        config['printer'].update(enabled=True, software_print_authorized=True)
        from qualification import validate_software_printing
        validate_software_printing(config['printer'], config['demo'])
    print('Kiosk: http://%s:%s/kiosk' % (config['host'], config['port']), flush=True)
    print('Operator: http://%s:%s/operator' % (config['host'], config['port']), flush=True)
    print('Printing: ' + ('LIVE — one job per completed new batch' if config['printer']['enabled'] else 'disabled'), flush=True)
    # SIGTERM from the service follows the same cleanup path as Ctrl+C.
    def terminate(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, terminate)
    lock = ProcessLock(config['data_dir'])
    engine = None
    server = None
    try:
        adapters = ({c: DemoCamera(Path(config['data_dir']) / 'demo-cards', c) for c in ('A', 'B')}
                    if config['demo'] else live_cameras(config))
        engine = Engine(config, adapters)
        from application_control import ApplicationControl
        engine.application_control = ApplicationControl(engine, args.config, args.dev_server)
        engine.application_control.start()
        app = create_app(engine)
        engine.start()
        if args.open_pages:
            import threading
            from desktop_launch import open_when_ready
            threading.Thread(target=open_when_ready, args=(
                'http://127.0.0.1:' + str(config['port']),
                Path(args.config).resolve().parent / 'guest-browser'), daemon=True).start()
        if args.dev_server:
            app.run(host=config['host'], port=config['port'], threaded=True, use_reloader=False)
        else:
            from waitress import create_server
            server = create_server(app, host=config['host'], port=config['port'], threads=4)
            server.print_listen('Serving on http://{}:{}')
            server.run()
    except KeyboardInterrupt:
        pass
    finally:
        if server is not None: server.close()
        if engine is not None:
            engine.stop()
        lock.close()
    if engine is not None: engine.application_control.finish()


if __name__ == '__main__':
    main()
