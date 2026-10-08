"""The AI helper's buttons ("Fill in for me", "Fill in the values", "✨ Fill list") answer in
the background: the AI can take longer than the site lets one page request run (gunicorn
stops a request after 30 seconds, nginx waits 60), so a request only checks and starts the
work, and the page asks every couple of seconds until the answer is ready.

Each job is a small JSON file (AI_JOB_DIR): {"user", "pending"} while it runs, then
{"user", "status", "body"}; the page reads it once and it's removed. Any worker can answer
the page's question, since they all see the same folder. Jobs nobody collected are removed
after an hour (the per-minute sweep in app/__init__.py)."""
import json
import os
import re
import threading
import time
import uuid

from flask import current_app

STUCK = 5 * 60   # seconds: a job still running this long was cut off (the site restarted)
KEEP = 60 * 60   # seconds: answers nobody collected


def job_dir():
    folder = current_app.config['AI_JOB_DIR']
    os.makedirs(folder, exist_ok=True)
    return folder


def _path(job):
    return os.path.join(job_dir(), job + '.json')


def _write(job, data):
    tmp = _path(job) + '.tmp'
    with open(tmp, 'w') as fh:
        json.dump(data, fh)
    os.replace(tmp, _path(job))  # never half-written for a reader


def start(user_id, run):
    """Run `run()` -> (body dict, status) in the background; returns the job's id.
    AI_JOBS = 'inline' runs it before returning (for tests of the job route)."""
    job = uuid.uuid4().hex
    _write(job, {'user': user_id, 'pending': True, 'at': time.time()})
    app = current_app._get_current_object()

    def work():
        with app.app_context():
            try:
                body, status = run()
            except Exception as exc:  # never leave the page waiting forever
                app.logger.exception('AI helper job failed: {}'.format(exc))
                body, status = {'ok': False, 'error': 'Something went wrong. Please try again.'}, 500
            _write(job, {'user': user_id, 'status': status, 'body': body, 'at': time.time()})
            if app.config.get('AI_JOBS') != 'inline':
                from app import db
                db.session.remove()  # this thread's database connection
    if app.config.get('AI_JOBS') == 'inline':
        work()  # tests of the job route: done before the first question
    else:
        threading.Thread(target=work, daemon=True).start()
    return job


def collect(job, user_id):
    """(body, status): the answer (then the job is gone), or {'pending': True} while it runs."""
    if not re.fullmatch(r'[0-9a-f]{32}', job or ''):
        return {'ok': False, 'error': 'That request isn’t known. Please try again.'}, 404
    try:
        with open(_path(job)) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {'ok': False, 'error': 'That request isn’t known. Please try again.'}, 404
    if data.get('user') != user_id:
        return {'ok': False, 'error': 'That request isn’t known. Please try again.'}, 404
    if data.get('pending'):
        if time.time() - data.get('at', 0) > STUCK:
            os.remove(_path(job))
            return {'ok': False, 'error': 'The AI helper took too long. Please try again.'}, 504
        return {'ok': True, 'pending': True}, 202
    os.remove(_path(job))
    return data.get('body') or {'ok': False}, data.get('status') or 500


def remove_old(now=None):
    """Answers nobody collected (the page was closed): removed after an hour."""
    now = now or time.time()
    folder = current_app.config.get('AI_JOB_DIR')
    if not folder or not os.path.isdir(folder):
        return 0
    gone = 0
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        try:
            if now - os.path.getmtime(path) > KEEP:
                os.remove(path)
                gone += 1
        except OSError:
            pass
    return gone
