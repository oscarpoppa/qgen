"""A photo of two facing book pages (a spread), found and cut in two (the owner, 2026-10-23: a photo of pages
16 and 17 was read as one page and the right page was lost).

The two pages meet at the book's spine, where the paper dips into shadow: a dark line that runs
most of the pages' height, near the middle of the photo. A page's edge against the desk is a step,
not a dip, and a fold or column gap on one page isn't a dark line the whole way down, so those
aren't taken for it. split() says where to cut, or None; it never needs the AI.
"""
import numpy as np
from PIL import Image

WIDTH = 500          # the photo is looked at this wide
BANDS = 10           # horizontal strips the spine must show in, one after another
NEED = 7             # ...at least this many of them, all at about the same place
FROM, TO = 0.30, 0.70   # the spine is in the middle of the photo
DIP = 25             # how much darker (0-255) than both sides the spine is, at least
SIDE = (0.05, 0.13)  # where "both sides" are, as a share of the photo's width beside the spine
WANDER = 0.04        # how far the spine may drift from strip to strip (share of the width)
TALL = (0.20, 0.85)  # the strips are taken between these heights of the photo
PERCENTILE = 80      # the paper's own brightness in a column, not its ink or pictures
SOFT = 14             # the spine's shading changes this much at most from one column to the next (a picture's or a box's edge is a step)


def _profile(gray, y0, y1):
    """Each column's typical brightness over these rows, a little smoothed."""
    prof = np.percentile(gray[y0:y1], PERCENTILE, axis=0)
    k = np.ones(5) / 5
    return np.convolve(prof, k, mode='same')


def _dip_at(prof, x, w):
    """How much darker than both sides the column x is (the smaller of the two differences)."""
    a0, a1 = int(SIDE[0] * w), int(SIDE[1] * w)
    if x - a1 < 0 or x + a1 >= len(prof):
        return -1
    left = prof[x - a1:x - a0].mean()
    right = prof[x + a0:x + a1].mean()
    here = prof[x - 2:x + 3].min()
    #(shading is gradual: a step anywhere beside it is an edge of something printed or of the page)
    if np.abs(np.diff(prof[x - a1:x + a1 + 1])).max() > SOFT:
        return -1
    return min(left, right) - here


def find(img):
    """The spine's place across the photo (0-1), or None when this isn't a photo of two facing pages."""
    im = img.convert('L')
    if im.width < 200 or im.height < 200:
        return None
    h = max(1, round(im.height * WIDTH / im.width))
    gray = np.asarray(im.resize((WIDTH, h), Image.BILINEAR), dtype=float)
    w = WIDTH
    top, bottom = int(TALL[0] * h), int(TALL[1] * h)
    step = (bottom - top) // BANDS
    if step < 4:
        return None
    found = []
    for i in range(BANDS):
        prof = _profile(gray, top + i * step, top + (i + 1) * step)
        best, at = DIP, None
        for x in range(int(FROM * w), int(TO * w)):
            d = _dip_at(prof, x, w)
            #(a dip that is also the lowest point close by: the spine, not a slope)
            if d > best and prof[x] <= prof[max(0, x - 6):x + 7].min() + 0.5:
                best, at = d, x
        found.append(at)
    xs = [x for x in found if x is not None]
    if len(xs) < NEED:
        return None
    mid = float(np.median(xs))
    near = [x for x in xs if abs(x - mid) <= WANDER * w]
    if len(near) < NEED:
        return None
    return float(np.mean(near)) / w


def split(img):
    """[left page, right page] cut at the spine, or None. The cut is at the spine, so each half is a photo
    of one page for the usual page finder (it straightens each, leaving out the desk)."""
    at = find(img)
    if at is None:
        return None
    x = round(img.width * at)
    return [img.crop((0, 0, x, img.height)), img.crop((x, 0, img.width, img.height))]
