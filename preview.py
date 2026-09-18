"""Bounded cached JPEG responses: HTTP clients never call a camera directly."""
from flask import abort, make_response, render_template


def register_preview(app, workers, demo=False):
    @app.get('/view/<label>')
    def monitor(label):
        if label not in workers:
            abort(404)
        return render_template('monitor.html', label=label, demo=demo)

    @app.get('/api/preview/<label>.jpg')
    def frame(label):
        if label not in workers:
            abort(404)
        worker = workers[label]
        data = worker.latest_frame()
        if data is None:
            response = make_response('Preview unavailable', 503)
        else:
            response = make_response(data)
            response.mimetype = 'image/jpeg'
        response.headers['Cache-Control'] = 'no-store'
        return response
