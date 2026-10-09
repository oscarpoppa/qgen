"""Going back: where a page's Back button, or the redirect after an action, should go.

Only addresses on this site are followed. A `next=` in a link, or the page the browser
says it came from (Referer), could otherwise send someone to another website straight
after signing in or after pressing a button (an "open redirect")."""
from urllib.parse import urlsplit, urlunsplit

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


def back_after_save(list_endpoint, item_id):
    """After saving in an editor: back to the page it was opened from (the form's next), and
    when that's the list (or there's none), the list with what was saved lit up (?show=)."""
    from flask import url_for
    target = next_arg()
    if target and _match(target)[0] != list_endpoint:
        return target
    return url_for(list_endpoint, show=item_id)


#pages a Back button can name, by endpoint: a name, or a function of the page's arguments
#(the hubs people go out from and come back to; anything else uses the page's own Back)
def _named(endpoint, args):
    from app import db
    from app.user.models import User
    from app.qgen.models import VQuiz
    fixed = {
        'qgen.dashboard': 'Dashboard', 'qgen.review_list': 'Grading', 'qgen.list_users': 'Results by student',
        'qgen.results_by_quiz': 'Results by quiz', 'qgen.list_vquizzes': 'Quizzes', 'qgen.list_vprobs': 'Problems',
        'user.userdet': 'Users', 'messages.inbox': 'Messages', 'messages.teachers_page': 'Messages between teachers',
        'qgen.archive': 'Archive', 'user.home': 'Home', 'user.mypage': 'My quizzes',
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
        return "{}'s student page".format(name) if name else None
    if endpoint == 'messages.conversation':
        name = user('student_id')
        return 'Messages: {}'.format(name) if name else None
    if endpoint == 'qgen.quiz_results_page':
        title = quiz('vqid')
        return 'Quiz history: {}'.format(title) if title else None
    if endpoint in ('qgen.list_vquiz', 'qgen.view_vquiz'):
        return quiz('vqid')
    if endpoint == 'qgen.problem_results':
        from app.qgen.models import VProblem
        vp = db.session.get(VProblem, int(args['vpid'])) if str(args.get('vpid', '')).isdigit() else None
        return 'Problem history: {}'.format(vp.title or 'Untitled') if vp else None
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
    """"Dashboard", "sam's student page"... for a page someone can go back to, or None."""
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
    'qgen.list_user': 'Student page',
    'qgen.quiz_results_page': 'Quiz history',
    'qgen.archived': 'See it in the Archive',
    'messages.conversation': 'Open the messages',
}


def link_kind(link):
    """The endpoint a stored link (a notice's) goes to, or None."""
    path = safe_next(link)
    return _match(path)[0] if path else None


def link_label(link, for_student=False):
    """The words for a notice's link: "Grade it", "See results"... ("Open" if it's unknown)."""
    kind = link_kind(link)
    if kind == 'qgen.qtake':
        return 'Go to the quiz' if for_student else 'See results'
    return LINK_LABELS.get(kind, 'Open')
