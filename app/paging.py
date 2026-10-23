"""Long lists, 20 at a time (the owner, 2026-10-23): any list that can grow without end (Problems,
Quizzes, Pictures, Other files, People, the results pages) sends the page only the rows to show,
for the folder, the typed words (?q=), the sort (?sort= and ?dir=) and the page (?page=) asked for.
The pager under the list (templates/_pager.html) links to the other pages; nothing else about a
list's rows changes."""
import math
from urllib.parse import urlencode

from flask import request

PAGE_SIZE = 20


class Page:
    """One page of a list: .items (the rows to draw), .total (how many match the words typed),
    .all (how many in the folder before them), .number, .count (pages), .q, .sort, .dir."""

    def __init__(self, items, total, everything, number, count, q, sort, dirn, size, keys=()):
        self.items, self.total, self.all = items, total, everything
        self.keys = list(keys)  # [id, name] of every match, on every page: "Check all 57" (static/js/checked.js)
        self.number, self.count, self.q, self.sort, self.dir, self.size = number, count, q, sort, dirn, size
        self.label = self.icon = None  # (the Checked folder's own words, set by the page)
        self.weight = None  # what the counts count when it isn't the things (Grading: attempts waiting), set by the page

    @property
    def first(self):
        return (self.number - 1) * self.size + 1 if self.total else 0

    @property
    def last(self):
        return min(self.number * self.size, self.total)

    def url(self, **changes):
        """This address with some of its words changed (None takes one out); ?page=1 is no ?page=."""
        args = {k: v for k, v in request.args.items() if k not in ('show', 'moved')}
        for k, v in changes.items():
            if v is None or v == '':
                args.pop(k, None)
            else:
                args[k] = v
        if str(args.get('page')) == '1':
            args.pop('page', None)
        query = urlencode(args)
        return request.path + ('?' + query if query else '')

    def window(self):
        """The page numbers to link: the first, the last and a few around this one; None is a gap."""
        want = {1, self.count, self.number, self.number - 1, self.number + 1, self.number - 2, self.number + 2}
        out, last = [], 0
        for n in sorted(x for x in want if 1 <= x <= self.count):
            if n - last > 1:
                out.append(None)
            out.append(n)
            last = n
        return out


def paginate(items, name_of=None, sorts=None, show=None, size=PAGE_SIZE, args=None, weight_of=None):
    """The page of items the address asks for. items: the folder's things, in their usual order.
    name_of(item) -> the words ?q= is looked for in; sorts: {'title': key function...} (a key of None
    or '' goes last, either way); show: the id of a thing to land on (?show=, lit up on arrival)."""
    args = request.args if args is None else args
    everything = len(items)
    q = (args.get('q') or '').strip()
    if q and name_of:
        low = q.lower()
        items = [i for i in items if low in (name_of(i) or '').lower()]
    #(no ?sort=: the page's usual order, newest first)
    sort = args.get('sort') if sorts and args.get('sort') in sorts else None
    dirn = 'desc' if args.get('dir') == 'desc' else 'asc'
    if sort:
        keyed = [(sorts[sort](i), i) for i in items]
        full = [p for p in keyed if p[0] not in (None, '')]
        gaps = [p for p in keyed if p[0] in (None, '')]
        full.sort(key=lambda p: p[0], reverse=dirn == 'desc')
        items = [p[1] for p in full + gaps]
    total = len(items)
    count = max(1, math.ceil(total / size))
    try:
        number = int(args.get('page') or 1)
    except ValueError:
        number = 1
    if show:
        for at, item in enumerate(items):
            if str(getattr(item, 'id', '')) == str(show):
                number = at // size + 1
                break
    number = min(max(number, 1), count)
    keys = [[getattr(i, 'id', None), (name_of(i) if name_of else '') or ''] for i in items] if count > 1 else ()
    page = Page(items[(number - 1) * size:number * size], total, everything, number, count, q, sort, dirn, size, keys)
    if weight_of:
        page.weight = sum(weight_of(i) for i in items)  # (what the counts count, e.g. attempts, over every match)
    return page
