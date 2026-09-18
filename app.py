#!/usr/bin/env python3
"""Run the operator dashboard and the single Stripshot coordinator."""
import argparse
import hmac
import json
import logging
import secrets
from pathlib import Path
from flask import Flask, abort, jsonify, render_template, request, send_file
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

    @app.before_request
    def protect_actions():
        if request.method == 'POST' and not hmac.compare_digest(request.headers.get('X-Stripshot-Token', ''), token):
            abort(403, 'Reload the dashboard before making changes')

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.errorhandler(Exception)
    def error(exc):
        code = exc.code if isinstance(exc, HTTPException) else 400 if isinstance(exc, (ValueError, RuntimeError)) else 500
        app.logger.warning('Request failed: %s', exc)
        return jsonify(error=str(exc)), code

    @app.get('/')
    def index():
        return render_template('index.html', token=token, demo=engine.config['demo'],
                               previews=bool(engine.config.get('preview_fps', 0)),
                               software=engine.config['camera_mode'] == 'software')

    @app.get('/api/status')
    def status():
        return jsonify(engine.status())

    @app.get('/api/printer')
    def printer():
        return jsonify(status=engine.printer.status())

    @app.post('/api/<action>')
    def action(action):
        if action not in ('reset', 'acknowledge', 'retry', 'demo', 'capture', 'resume_capture', 'abandon_capture'):
            abort(404)
        if action in ('reset', 'demo') and engine.status()['phase'] != 'watching':
            raise ValueError('Wait until the appliance is watching')
        engine.request(action).result(timeout=130)
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
    parser.add_argument('--discover', action='store_true', help='Read attached camera serials, then exit')
    parser.add_argument('--dev-server', action='store_true', help='Use Werkzeug for local development only')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    if args.discover:
        print(json.dumps(discover(), indent=2))
        return
    config = load_config(args.config)
    lock = ProcessLock(config['data_dir'])
    engine = None
    try:
        adapters = ({c: DemoCamera(Path(config['data_dir']) / 'demo-cards', c) for c in ('A', 'B')}
                    if config['demo'] else live_cameras(config))
        engine = Engine(config, adapters)
        app = create_app(engine)
        engine.start()
        if args.dev_server:
            app.run(host=config['host'], port=config['port'], threaded=True, use_reloader=False)
        else:
            from waitress import serve
            serve(app, host=config['host'], port=config['port'], threads=4)
    finally:
        if engine is not None:
            engine.stop()
        lock.close()


if __name__ == '__main__':
    main()
