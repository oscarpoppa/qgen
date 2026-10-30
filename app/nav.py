"""Going back: where a page's Back button, or the redirect after an action, should go.

Only addresses on this site are followed. A `next=` in a link, or the page the browser
says it came from (Referer), could otherwise send someone to another website straight
after signing in or after pressing a button (an "open redirect")."""
from urllib.parse import urlsplit, parse_qs, parse_qsl, urlencode, urlunsplit

from flask import request


def _this_host(parts):
    """Whether a full address (urlsplit parts) is on this site. The live site is behind nginx,
    which passes its name on without the port ("localhost" for "localhost:8080"): then the
    same name on any port counts, since the port the browser used isn't known here."""
    host = request.host
    if parts.netloc == host:
        return True
    if host.startswith('['):  # [::1]:8080
        name, _, rest = host[1:].partition(']')
        port = rest[1:]
    else:
        name, _, port = host.partition(':')
    return not port and parts.hostname is not None and parts.hostname == name.lower()


def safe_next(target, fallback=None):
    """target if it's a page on this site (a path, or a full address on this host), as a
    path; else fallback."""
    if not target or not isinstance(target, str):
        return fallback
    target = target.strip()
    #browsers treat a backslash like a slash ("/\evil.example" is another site)
    if '\\' in target or any(ord(c) < 32 for c in target):
        return fallback
    parts = urlsplit(target)
    if parts.scheme or parts.netloc:
        if parts.scheme not in ('http', 'https') or not _this_host(parts):
            return fallback
    if not parts.path.startswith('/') or parts.path.startswith('//'):
        return fallback
    return urlunsplit(('', '', parts.path, parts.query, parts.fragment))


def back_to(fallback):
    """Where to go after an action: the page it was done on (if on this site), else fallback."""
    return safe_next(request.referrer, fallback)


def next_arg(fallback=None):
    """The page named by ?next= (or a form's next field), if it's on this site."""
    return safe_next(request.values.get('next'), fallback)


#lit up once, on arrival (what was just saved or moved): not carried back to the page again
_ONCE = ('show', 'moved')


def _without_once(path, **extra):
    """path with its ?show= / ?moved= dropped (and extra set), the rest of its address kept."""
    parts = urlsplit(path)
    q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in _ONCE and k not in extra]
    q += [(k, str(v)) for k, v in extra.items()]
    return urlunsplit(('', '', parts.path, urlencode(q), parts.fragment))


def back_to_list(list_endpoint):
    """After an action on something in a list (delete, restore...): back to that list as it was
    (the page it was done on: its folder tab, filter and Show choice), else the list from the start."""
    from flask import url_for
    path = safe_next(request.referrer)
    #(done in the Trash, e.g. its Delete for good: back to the Trash as it was, not to the list; the owner, 2026-10-27)
    if path and _match(path)[0] in (list_endpoint, 'qgen.archive'):
        return _without_once(path)
    return url_for(list_endpoint)


def back_after_save(list_endpoint, item_id, new=False):
    """After saving in an editor: back to the page it was opened from (the form's next), and
    when that's the list (or there's none), the list with what was saved lit up (?show=), on
    the folder tab that was open there (?tab=)."""
    from flask import url_for
    target = next_arg()
    if target and _match(target)[0] != list_endpoint:
        if new:  # (something new: shown in its list, wherever the editor was opened from)
            return url_for(list_endpoint, show=item_id)
        return target
    if target:  # the list as it was left (tab, filter, Show), with what was saved lit up
        return _without_once(target, show=item_id)
    return url_for(list_endpoint, show=item_id)


def kept_tab():
    """The folder tab (?tab=, static/js/folderfilter.js) open on the page an action was sent
    from, so going back there opens the same folder; None when there was none."""
    path = safe_next(request.referrer)
    return parse_qs(urlsplit(path).query).get('tab', [None])[0] if path else None


#pages a Back button can name, by endpoint: a name, or a function of the page's arguments
#(the hubs people go out from and come back to; anything else uses the page's own Back)
def _named(endpoint, args):
    from app import db
    from app.user.models import User
    from app.qgen.models import VQuiz
    fixed = {
        'qgen.dashboard': 'Dashboard', 'qgen.review_list': 'Grading', 'qgen.open_quizzes': 'Pending Quizzes', 'qgen.list_users': 'People',
        'qgen.list_vquizzes': 'Quizzes', 'qgen.list_vprobs': 'Problems',
        'user.userdet': 'People', 'messages.inbox': 'Messages', 'messages.teachers_page': 'Teachers’ Messages',
        'qgen.archive': 'Trash', 'user.home': 'Home', 'user.mypage': 'My Quizzes',
    }
    if endpoint in fixed:
        return fixed[endpoint]
    def user(key):
        u = db.session.get(User, int(args[key])) if str(args.get(key, '')).isdigit() else None
        return u.shown_name if u is not None else None
    def quiz(key):
        vq = db.session.get(VQuiz, int(args[key])) if str(args.get(key, '')).isdigit() else None
        return vq.title if vq else None
    if endpoint == 'qgen.list_user':
        name = user('uid')
        return 'Student History: {}'.format(name) if name else None
    if endpoint == 'messages.conversation':
        name = user('student_id')
        return 'Messages: {}'.format(name) if name else None
    if endpoint == 'qgen.quiz_results_page':
        title = quiz('vqid')
        return 'Quiz History: {}'.format(title) if title else None
    if endpoint in ('qgen.list_vquiz', 'qgen.view_vquiz'):
        return quiz('vqid')
    if endpoint == 'qgen.problem_results':
        from app.qgen.models import VProblem
        vp = db.session.get(VProblem, int(args['vpid'])) if str(args.get('vpid', '')).isdigit() else None
        return 'Problem History: {}'.format(vp.title or 'Untitled') if vp else None
    return None


def _match(path):
    """(endpoint, args) of a path on this site, or (None, None)."""
    from flask import current_app
    from werkzeug.exceptions import HTTPException
    from werkzeug.routing import RequestRedirect
    try:
        adapter = current_app.create_url_adapter(request)
        endpoint, args = adapter.match(path.split('?')[0].split('#')[0], method='GET')
        return endpoint, args
    except (HTTPException, RequestRedirect):
        return None, None


def place_name(path):
    """"Dashboard", "Student history: sam"... for a page someone can go back to, or None."""
    if not path:
        return None
    endpoint, args = _match(path)
    return _named(endpoint, args) if endpoint else None


def back(fallback_url, fallback_label):
    """Where this page's Back button goes, and what it says: the page named by ?next=, or
    the page they came from, when it's one people go back to; else the page's own choice."""
    for target in (request.values.get('next'), request.referrer):
        path = safe_next(target)
        if not path:
            continue
        endpoint, args = _match(path)
        if endpoint is None or (endpoint, args) == (request.endpoint, request.view_args):
            continue  # not this page itself (as after an action on it)
        label = _named(endpoint, args)
        if label:
            return path, label
    return fallback_url, fallback_label


#what a notice's or message's link opens, by the page it goes to
LINK_LABELS = {
    'qgen.review': 'Grade it',
    'qgen.list_user': 'Student history',
    'qgen.quiz_results_page': 'Quiz history',
    'qgen.archived': 'See it in the Trash',
    'messages.conversation': 'Open the messages',
}


def link_kind(link):
    """The endpoint a stored link (a notice's) goes to, or None."""
    path = safe_next(link)
    return _match(path)[0] if path else None


def link_label(link, for_student=False):
    """The words for a notice's link: "Grade it", "See results"... ("Open" if it's unknown)."""
    path = safe_next(link)
    kind, args = _match(path) if path else (None, None)
    if kind == 'qgen.qtake':
        if not for_student:
            return 'See results'
        #(a student's: the quiz while it's still to do, its results once handed in, e.g. a
        #"was graded" notice: the owner, 2026-10-20)
        #(the student's handed-in attempts looked up once per page, not once per notice: the code
        #critic, 2026-10-20)
        from flask import g
        from flask_login import current_user
        done = getattr(g, '_done_attempts', None)
        if done is None:
            from app.qgen.models import CQuiz
            uid = getattr(current_user, 'id', None)
            done = g._done_attempts = {i for (i,) in CQuiz.query.with_entities(CQuiz.id)
                                       .filter(CQuiz.assignee == uid, CQuiz.completed.is_(True))} if uid else set()
        try:
            cidx = int((args or {}).get('cidx'))
        except (TypeError, ValueError):
            cidx = None
        return 'See your results' if cidx in done else 'Go to the quiz'
    return LINK_LABELS.get(kind, 'Open')
