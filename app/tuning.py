"""Technical settings an administrator can change on Settings -> Technical settings.

Each value is stored in the Setting table as "tune.<key>"; a missing or unreadable one
means the default, so nothing changes until someone edits a value and a bad row can't
break a page. Values are read once per request (every server process reads the
database, so a change applies everywhere at the next page).
"""
from datetime import timedelta

from flask import current_app, has_app_context, has_request_context, request

PREFIX = 'tune.'
CACHE = 'qgen.tuning'

#the AI helper's requests use adaptive thinking and the "default" refusal fallback;
#these models accept both and answer within the helper's time limit
AI_MODELS = [('claude-opus-5', 'Claude Opus 5 (the one used so far)'),
             ('claude-opus-5-5', 'Claude Opus 5.5 (newer, a little cheaper)'),
             ('claude-sonnet-5-5', 'Claude Sonnet 5.5 (faster, about half the price)')]

GROUPS = [('online', 'Online & refresh'), ('quizzes', 'Quizzes & messages'),
          ('ai', 'AI helper'), ('security', 'Sign-in & security')]


def _t(key, group, label, help, unit, default, low=None, high=None, choices=None):
    return {'key': key, 'group': group, 'label': label, 'help': help, 'unit': unit,
            'default': default, 'min': low, 'max': high, 'choices': choices}


TUNABLES = [
    _t('online_window', 'online', 'Online window',
       'Someone counts as online if a page of theirs checked in within this long (and they haven\'t logged out).',
       'minutes', 2, 1, 30),
    _t('recently', 'online', '"Active in the last …"',
       'How far back the "Active in the last hour" list on the Dashboard and the online menu looks.',
       'minutes', 60, 5, 1440),
    _t('poll_seconds', 'online', 'Pages check in every',
       'How often every open page asks for new messages and notices (this also keeps people "online").',
       'seconds', 30, 10, 300),
    _t('dashboard_seconds', 'online', 'Dashboard refreshes every',
       'How often the Dashboard reloads its boxes while it\'s open.',
       'seconds', 30, 10, 600),
    _t('due_soon_days', 'online', '"Due soon" on the Dashboard',
       'The Dashboard\'s "not handed in, due within …" tile counts quizzes closing within this many days.',
       'days', 2, 1, 14),
    _t('list_grading', 'online', 'Dashboard: grading queue shows', 'How many attempts waiting for grading are listed.',
       'items', 5, 3, 50),
    _t('list_handins', 'online', 'Dashboard: recent hand-ins shows', 'How many recent hand-ins are listed.',
       'items', 10, 3, 50),
    _t('list_assigned', 'online', 'Dashboard: "Assigned, not handed in yet" shows', 'How many are listed.',
       'items', 10, 3, 50),
    _t('grace_minutes', 'quizzes', 'Grace after a quiz\'s time is up',
       'Answers still count for this long after the time limit or closing time (for slow connections).',
       'minutes', 2, 0, 15),
    _t('max_api_answer', 'quizzes', 'Longest answer sent through the app\'s API',
       'For answers sent by an app using the API. (Answers typed on the website aren\'t limited.)',
       'characters', 20000, 1000, 200000),
    _t('max_message', 'quizzes', 'Longest message', 'The most characters one message can have.',
       'characters', 2000, 200, 20000),
    _t('ai_hourly', 'ai', 'Requests per teacher per hour',
       'How many times each teacher can use the AI helper in an hour.', 'requests', 30, 1, 500),
    _t('ai_model', 'ai', 'Claude model', 'Which Claude model the AI helper uses.', 'choice', 'claude-opus-5',
       choices=AI_MODELS),
    _t('min_password', 'security', 'Shortest password', 'For new passwords (existing ones keep working).',
       'characters', 8, 6, 64),
    _t('lockout_tries', 'security', 'Wrong passwords before a pause',
       'After this many wrong passwords for one username, logging in is paused.', 'tries', 10, 3, 50),
    _t('lockout_minutes', 'security', 'Length of the pause',
       'How long logging in is paused, and how far back wrong passwords are counted.', 'minutes', 15, 1, 240),
    _t('token_days', 'security', 'New app tokens last',
       'How long a newly made API token works (tokens already made keep their date).', 'days', 90, 1, 365),
]
BY_KEY = {t['key']: t for t in TUNABLES}


def _clean(t, raw):
    """A stored or typed value as the right type, or None if it isn't valid."""
    if t['unit'] == 'choice':
        return raw if raw in [c[0] for c in t['choices']] else None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if t['min'] <= value <= t['max'] else None


def _stored():
    """{key: raw text} for every value someone has set."""
    from app import db
    from app.qgen.models import Setting
    try:
        rows = Setting.query.filter(Setting.key.like(PREFIX + '%')).all()
    except Exception:
        db.session.rollback()
        return {}
    return {r.key[len(PREFIX):]: r.value for r in rows}


def values():
    """{key: value} for every setting (defaults where none is set or it's unreadable)."""
    #kept for the length of one request (on the request itself: an app context, and so
    #flask.g, can outlive a request)
    if has_request_context() and request.environ.get(CACHE) is not None:
        return request.environ[CACHE]
    #outside the app (e.g. a script calling the AI helper directly): the defaults
    stored = _stored() if has_app_context() else {}
    out = {}
    for t in TUNABLES:
        value = _clean(t, stored[t['key']]) if t['key'] in stored else None
        out[t['key']] = t['default'] if value is None else value
    if has_request_context():
        request.environ[CACHE] = out
    return out


def get(key):
    return values()[key]


def is_default(key):
    return get(key) == BY_KEY[key]['default']


# ---------------------------------------------------------------- handy forms

def online_window():
    return timedelta(minutes=get('online_window'))


def seen_every():
    """How often "last seen" is written: at most once a minute, and always often enough
    that someone with a page open stays inside the online window (a check-in can come up
    to one check-in time after the last write; 10 seconds to spare)."""
    room = online_window() - timedelta(seconds=get('poll_seconds') + 10)
    return max(timedelta(seconds=10), min(timedelta(minutes=1), room))


def recently():
    return timedelta(minutes=get('recently'))


def due_soon():
    return timedelta(days=get('due_soon_days'))


def grace():
    return timedelta(minutes=get('grace_minutes'))


def poll_ms():
    return get('poll_seconds') * 1000


def dashboard_ms():
    return get('dashboard_seconds') * 1000


# ---------------------------------------------------------------- changing them

def validate(form):
    """The page's form -> ({key: value}, {key: error}). Nothing is valid unless all are."""
    chosen, errors = {}, {}
    for t in TUNABLES:
        raw = form.get(t['key'], '')
        value = _clean(t, raw)
        if value is None:
            errors[t['key']] = ('Please choose one of the listed models.' if t['unit'] == 'choice'
                                else 'Please give a whole number from {:,} to {:,}.'.format(t['min'], t['max']))
        else:
            chosen[t['key']] = value
    if 'online_window' in chosen and 'poll_seconds' in chosen:
        if chosen['online_window'] * 60 < 2 * chosen['poll_seconds']:
            errors['online_window'] = ('The online window must be at least twice the check-in time ({} seconds), '
                                       'or people on the site would keep dropping off between check-ins.'
                                       .format(chosen['poll_seconds']))
    return chosen, errors


def save(chosen, by):
    """Store the values; a value equal to its default is stored as "not set". Returns the
    keys that changed."""
    from app import db
    from app.qgen.models import Setting
    before = values()
    changed = []
    for key, value in chosen.items():
        if value == before[key]:
            continue
        row = db.session.get(Setting, PREFIX + key)
        if value == BY_KEY[key]['default']:
            if row is not None:
                db.session.delete(row)
        else:
            row = row or Setting(key=PREFIX + key)
            row.value = str(value)
            db.session.add(row)
        changed.append(key)
        current_app.logger.info('{} changed technical setting {}: {} -> {}'.format(by.username, key, before[key], value))
    db.session.commit()
    if has_request_context():
        request.environ.pop(CACHE, None)
    return changed


def reset(by, key=None):
    """Back to the default: one setting, or (key=None) all of them."""
    from app import db
    from app.qgen.models import Setting
    q = Setting.query.filter(Setting.key.like(PREFIX + '%'))
    if key:
        q = Setting.query.filter_by(key=PREFIX + key)
    q.delete(synchronize_session=False)
    db.session.commit()
    if has_request_context():
        request.environ.pop(CACHE, None)
    current_app.logger.info('{} reset {} to default'.format(by.username, 'technical setting ' + key if key else 'all technical settings'))
