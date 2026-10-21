"""A quiz taken on the scanned page itself (the owner, 2026-10-18).

QuizScan says what each problem on a page is and where its printed words are. This module
looks at the page picture to find, for each problem, the places a student answers:

- an answer box printed on the page (a frame, mostly empty inside) or an answer line
  (a long, thin line, as in "7 + 5 = ____");
- for a choice problem, the little box or circle printed before each choice.

A problem whose numbers change for each student also gets the area of its printed wording,
which the take page covers with white and writes that student's version on, in a font
picked to look like the page's.

A problem where nothing is found is taken the usual way, under the page.

Boxes are fractions of the page, {'left', 'top', 'right', 'bottom'}, like QuizScan's.
"""
import os
import re

import numpy as np

CONTRAST = 40       # ink: this much darker than the paper around it (pale circles before choices too)
FONTS = {           # the fonts a covered problem can be written in: static/fonts/<file>
    'NotoSans-Bold.ttf': ('sans', 700), 'NotoSans-Regular.ttf': ('sans', 400),
    'NotoSerif-Bold.ttf': ('serif', 700), 'NotoSerif-Regular.ttf': ('serif', 400),
}
OPERATORS = '+-−×÷*/'


def frac(x0, y0, x1, y1, W, H):
    return {'left': round(x0 / W, 4), 'top': round(y0 / H, 4), 'right': round(x1 / W, 4), 'bottom': round(y1 / H, 4)}


def px(box, W, H):
    return (int(round(box['left'] * W)), int(round(box['top'] * H)), int(round(box['right'] * W)), int(round(box['bottom'] * H)))


def _components(mask):
    """[(x0, y0, x1, y1, ink pixels)] for each blob of ink."""
    from scipy import ndimage
    lab, _n = ndimage.label(mask, structure=np.ones((3, 3), bool))
    out = []
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        if sl is None:
            continue
        ys, xs = sl
        out.append((xs.start, ys.start, xs.stop, ys.stop, int((lab[sl] == i).sum())))
    return out


def ink_mask(gray, contrast=None):
    """Where the page has ink: darker than the paper around it by CONTRAST. Smoothed first,
    so a photo of a screen (its fine stripes) or a grainy scan doesn't count as ink, and
    judged against the nearby paper, so a shadow or a gray backdrop doesn't either."""
    from scipy import ndimage
    H, W = gray.shape
    smooth = ndimage.gaussian_filter(gray.astype(np.float32), max(1.0, W / 1200))
    k = max(15, int(W / 60)) | 1
    paper = ndimage.grey_closing(smooth, size=(k, k))
    return (paper - smooth) > (CONTRAST if contrast is None else contrast)


def _blank_out(mask, boxes, X0, Y0):
    """mask with these page-pixel boxes cleared (pictures, the problem's number...)."""
    mask = mask.copy()
    for (x0, y0, x1, y1) in boxes:
        mask[max(0, y0 - Y0):max(0, y1 - Y0), max(0, x0 - X0):max(0, x1 - X0)] = False
    return mask


def _char_height(comps, H):
    """The height of the printed letters and digits around here (median of letter-sized blobs)."""
    hs = [c[3] - c[1] for c in comps if 0.006 * H <= c[3] - c[1] <= 0.06 * H and (c[2] - c[0]) <= 2.5 * (c[3] - c[1])]
    return float(np.median(hs)) if hs else 0.02 * H


def _frame(comps, ink, X0, Y0, box_px, W, H):
    """The printed answer box in a problem: a big frame, mostly empty inside. The rightmost
    one when there are several. (x0, y0, x1, y1) in page pixels, or None."""
    x0, y0, x1, y1 = box_px
    best = None
    for (a, b, c, d, n) in comps:
        w, h = c - a, d - b
        if w < 0.04 * W or h < 0.5 * (y1 - y0) or h < 0.015 * H or n > 0.35 * w * h:
            continue
        # empty inside: almost no ink in the middle part
        mx, my = max(2, int(0.18 * w)), max(2, int(0.18 * h))
        inside = ink[b + my:d - my, a + mx:c - mx]
        if inside.size == 0 or inside.mean() > 0.03:
            continue
        # the frame really goes round: ink near all four edges
        edge = ink[b:d, a:c]
        k = max(2, int(0.08 * min(w, h)))
        if not (edge[:k].any() and edge[-k:].any() and edge[:, :k].any() and edge[:, -k:].any()):
            continue
        if best is None or a > best[0]:
            best = (a, b, c, d)
    if best is None:
        return None
    a, b, c, d = best
    return (a + X0, b + Y0, c + X0, d + Y0)


def _lines(comps, ch, H=0):
    """Answer lines: long, thin, solid blobs. [(x0, y0, x1, y1)] relative to the region."""
    out = []
    for (a, b, c, d, n) in comps:
        w, h = c - a, d - b
        #(a grainy photo thickens a line: up to nearly half a letter's height, the owner, 2026-10-20)
        if h <= max(3, 0.45 * ch, 0.006 * H) and w >= 2.5 * ch and n >= 0.5 * w * h:
            out.append((a, b, c, d))
    return out


def _ruled_runs(ink, ch):
    """Answer lines that touch something else (a mark or a smudge on the line, the owner,
    2026-10-20): unbroken runs of ink at least 2.5 letters long, a few rows thick at most.
    [(x0, y0, x1, y1)] relative to the region."""
    rows = {}
    for y in range(ink.shape[0]):
        for a, b in _runs(ink[y], int(2.5 * ch)):
            rows.setdefault(y, []).append((a, b))
    out = []
    for y in sorted(rows):
        for a, b in rows[y]:
            for o in out:
                if o[3] >= y - 1 and a < o[2] and b > o[0]:
                    o[1], o[3] = min(o[1], y), y + 1
                    o[0], o[2] = min(o[0], a), max(o[2], b)
                    break
            else:
                out.append([a, y, b, y + 1])
    return [tuple(o) for o in out if o[3] - o[1] <= max(3, 0.45 * ch)]


def _marks(full, region, exclude, ch, want):
    """The boxes or circles printed before each choice, in reading order: [(x0, y0, x1, y1)]
    in page pixels, or None when there aren't exactly `want` of them."""
    found = _ring_candidates(full, region, exclude, ch)
    return _pick_marks(found, ch, want)


def _ring_candidates(full, region, exclude, ch, words_after=True):
    """Every little box or circle in a region that could be a choice's mark: [(box, stands alone)].
    words_after: only ones with words just to their right ("☐ Lion"); not for a table of TRUE /
    FALSE boxes whose words are in a heading above."""
    X0, Y0, X1, Y1 = region
    #(not blanked out: QuizScan's boxes round pictures and other problems are loose and can reach
    #over a column of boxes, cutting them in half, as on a page of pictures each with its choices
    #beside it; a box is left out only when it sits well inside one: the owner, 2026-10-19)
    mask = full[Y0:Y1, X0:X1]
    inner = [(x0 + 0.2 * (x1 - x0), y0 + 0.2 * (y1 - y0), x1 - 0.2 * (x1 - x0), y1 - 0.2 * (y1 - y0))
             for (x0, y0, x1, y1) in exclude]
    found = []  # (box, stands alone)
    for (a, b, c, d, n) in _components(mask):
        w, h = c - a, d - b
        if not (0.5 * ch <= h <= 2.6 * ch and 0.7 <= w / max(h, 1) <= 1.5):
            continue
        cx, cy = X0 + (a + c) / 2, Y0 + (b + d) / 2
        if any(e0 <= cx <= e1 and f0 <= cy <= f1 for (e0, f0, e1, f1) in inner):
            continue
        mx, my = max(1, int(0.25 * w)), max(1, int(0.25 * h))
        middle = mask[b + my:d - my, a + mx:c - mx].mean()
        if middle > 0.35 or (n > 0.5 * w * h and middle > 0.02):
            continue  # not hollow (a letter "o" is thicker for its size; a thick-edged box is empty inside)
        # a ring: ink along all four sides, as a box or a circle has (a check mark or a
        # drawing's curl doesn't); a tiny round button is let off lighter
        sub = mask[b:d, a:c]
        t = max(1, int(0.25 * min(w, h)))
        if min(sub[:t].any(axis=0).mean(), sub[-t:].any(axis=0).mean(),
               sub[:, :t].any(axis=1).mean(), sub[:, -t:].any(axis=1).mean()) < (0.2 if max(w, h) < 14 else 0.45):
            continue
        # words to its right
        right = mask[b:d, c + 1:min(mask.shape[1], c + int(4 * w))]
        if words_after and not (right.size and right.any()):
            continue
        # standing on its own: no ink right up against its left (a letter has its word around it)
        left = mask[b:d, max(0, a - int(0.4 * w)):max(0, a - 1)]
        found.append(((a + X0, b + Y0, c + X0, d + Y0), not (left.size and left.any())))
    return found


def _pick_marks(found, ch, want):
    if len(found) < want:
        return None
    # a problem's boxes are all of a size: the sets of `want` that match, the one whose boxes
    # stand on their own most of all when there are several (a picture's curl or a check mark
    # beside the line is another size)
    size = lambda m: (m[2] - m[0], m[3] - m[1])
    best = None
    for ref, _alone in found:
        same = [(m, al) for m, al in found if abs(size(m)[0] - size(ref)[0]) <= 0.2 * size(ref)[0] + 2
                and abs(size(m)[1] - size(ref)[1]) <= 0.2 * size(ref)[1] + 2]
        if len(same) != want:
            continue
        score = sum(1 for _m, al in same if al)
        if best is None or score > best[0]:
            best = (score, [m for m, _al in same])
    if best is None:
        alone = [m for m, al in found if al]
        if len(alone) != want:
            return None
        best = (0, alone)
    # reading order: by line, then left to right
    return sorted(best[1], key=lambda m: (round(((m[1] + m[3]) / 2) / max(1.0, 0.8 * ch)), m[0]))


def _cells(full, box_px, exclude, want):
    """Table cells to mark an answer in, on a problem's line: like the T and F columns of a
    true/false table ("Circle True (T) or False (F)"). The cells right of the problem's words
    that are empty, or hold only a short heading such as "T". [(x0, y0, x1, y1)] in page
    pixels, left to right, or None when there aren't exactly `want` of them (the owner,
    2026-10-18)."""
    H, W = full.shape
    x0, y0, x1, y1 = box_px
    h = max(1, y1 - y0)
    # the table's lines around the problem: the ruled lines above and below it...
    def ruled_row(y_from, y_to, step):
        for y in range(y_from, y_to, step):
            #(one unbroken run, not just a lot of ink: a long line of text isn't a ruled line)
            if 0 <= y < H and _runs(full[y, x0:W], int(0.6 * (W - x0))):
                return y
        return None
    top = ruled_row(y0 + h // 2, max(0, y0 - h), -1)
    bottom = ruled_row(y0 + h // 2, min(H, y1 + h), 1)
    if top is None or bottom is None or bottom - top < 0.5 * h:
        return None
    # ...and the upright lines between them, from the problem's words to the right
    band = full[top + 2:bottom - 1, :]
    upright = band.mean(axis=0) > 0.85
    lines, x = [], max(0, x0)
    while x < W:
        if upright[x]:
            start = x
            while x < W and upright[x]:
                x += 1
            lines.append((start, x))
        x += 1
    cells = []
    for (a1, a2), (b1, b2) in zip(lines, lines[1:]):
        c0, c1 = a2, b1
        if c1 - c0 < 0.6 * h or c1 <= x1 - 2:
            continue  # too narrow, or the problem's own words
        inside = full[top + 3:bottom - 2, c0 + 3:c1 - 2]
        if inside.size and inside.mean() < 0.12:
            cells.append((c0, top + 1, c1, bottom))
    if len(cells) != want:
        return None
    return cells


def _rows_of_marks(full, page, pictures, ch, want, boxes):
    """A list of questions each with its own line of marks (TRUE / FALSE boxes at the end of each
    line): the lines of same-sized marks, close together, matched to the questions by where they
    are, allowing for QuizScan's boxes all sitting a little off (half a line, say). A question
    whose line doesn't show all `want` marks (a banner over one) is left out. [marks or None],
    one per question (the owner, 2026-10-18)."""
    H, W = full.shape
    found = [m for m, _alone in _ring_candidates(full, (0, 0, W, H), pictures, ch, words_after=False)]
    if len(found) < want:
        return None
    size = lambda m: (m[2] - m[0], m[3] - m[1])
    best = []
    for ref in found:
        same = [m for m in found if abs(size(m)[0] - size(ref)[0]) <= 0.2 * size(ref)[0] + 2
                and abs(size(m)[1] - size(ref)[1]) <= 0.2 * size(ref)[1] + 2]
        if len(same) > len(best):
            best = same
    if not best:
        return None
    mh = float(np.median([size(m)[1] for m in best])); mw = float(np.median([size(m)[0] for m in best]))
    rows = []
    for m in sorted(best, key=lambda m: (m[1] + m[3]) / 2):
        cy = (m[1] + m[3]) / 2
        if rows and abs(cy - rows[-1][0]) <= 0.5 * mh:
            rows[-1][1].append(m)
        else:
            rows.append([cy, [m]])
    lines = []
    for cy, ms in rows:
        ms = sorted(ms, key=lambda m: m[0])
        # one question's marks are close together (not three questions side by side, as on a
        # page of picture questions in columns)
        if len(ms) > want or any(b[0] - a[2] > 8 * mw for a, b in zip(ms, ms[1:])):
            continue
        lines.append((cy, ms))
    # the columns the full lines' marks stand in: a line missing a mark (a banner over it) still
    # counts when its marks stand in those columns; a stray shape elsewhere doesn't
    full_lines = [ms for _cy, ms in lines if len(ms) == want]
    if not full_lines:
        return None
    cols = [float(np.median([ms[k][0] for ms in full_lines])) for k in range(want)]
    lines = [(cy, ms) for cy, ms in lines if all(min(abs(m[0] - c) for c in cols) <= mw for m in ms)]
    if len(lines) < max(2, len(boxes) // 2):
        return None
    centers = [(b[1] + b[3]) / 2 for b in boxes]
    if len(lines) == len(boxes):
        #a line per question: in order, top to bottom (QuizScan's boxes can be spaced a little
        #differently from the page's lines, so a line can drift further off down the page)
        return [ms if len(ms) == want else None for _cy, ms in lines]
    gaps = sorted(b - a for a, b in zip(centers, centers[1:]) if b > a)
    spacing = gaps[len(gaps) // 2] if gaps else 3 * mh
    tol = 0.35 * spacing
    # the shift that lines the most questions up with a line of marks
    best_d, best_n = 0.0, -1
    for c in centers:
        for cy, _ms in lines:
            d = cy - c
            n = sum(1 for c2 in centers if any(abs(cy2 - (c2 + d)) <= tol for cy2, _ in lines))
            if n > best_n or (n == best_n and abs(d) < abs(best_d)):
                best_d, best_n = d, n
    if best_n < max(2, len(boxes) // 2):
        return None
    out, used = [], set()
    for c in centers:
        near = min(range(len(lines)), key=lambda k: abs(lines[k][0] - (c + best_d)))
        cy, ms = lines[near]
        if abs(cy - (c + best_d)) <= tol and near not in used and len(ms) == want:
            out.append(ms); used.add(near)
        else:
            out.append(None)
    return out


def _text_lines(ink, ch):
    """The lines of text in a region: [(top, bottom)], split where a row has no ink."""
    rows = np.nonzero(ink.any(axis=1))[0]
    if not rows.size:
        return []
    #(split at any blank row: choices printed one per line can sit very close together; a piece
    #too short to be a line of letters, like a frame's edge or the dot of an i, isn't one)
    lines, start = [], rows[0]
    for a, b in zip(rows, rows[1:]):
        if b - a > 1:
            lines.append((start, a + 1)); start = b
    lines.append((start, rows[-1] + 1))
    return [(a, b) for a, b in lines if b - a >= 0.6 * ch]


def _groups(line_ink, gap):
    """The pieces of a line of text split where the blank is wider than `gap`: [(left, right)]."""
    cols = np.nonzero(line_ink.any(axis=0))[0]
    if not cols.size:
        return []
    out, start = [], cols[0]
    for a, b in zip(cols, cols[1:]):
        if b - a > gap:
            out.append((start, a + 1)); start = b
    out.append((start, cols[-1] + 1))
    return out


def _lettered(full, region, exclude, ch, want, box_bottom=None):
    """Choices printed with letters and nothing to check ("a. Blue   b. Red   c. Brown" on a
    line, or "A. Horse" one per line), as a student circles one (the owner, 2026-10-19): the
    last lines of the problem holding exactly `want` choices. Each choice's letter (the mark,
    circled when picked) and the whole choice (what's clicked), in page pixels, in reading
    order; None when the lines don't split into `want` choices that each start with a letter."""
    X0, Y0, X1, Y1 = region
    ink = _blank_out(full[Y0:Y1, X0:X1], exclude, X0, Y0)
    #(a "line" much taller than the letters below the problem's own box is a picture, e.g. a border
    #of holly under the last problem; inside the box it may be two choice lines touching)
    below = (box_bottom - Y0) if box_bottom is not None else ink.shape[0]
    lines = [(a, b) for a, b in _text_lines(ink, ch) if b - a <= 1.8 * ch or a < below - 0.3 * ch]
    #(two choice lines touching: cut at the row with the least ink)
    split = []
    for a, b in lines:
        if b - a > 1.8 * ch:
            prof = ink[a:b].sum(axis=1)
            lo = int(0.3 * (b - a)); hi = int(0.7 * (b - a))
            cut = a + lo + int(np.argmin(prof[lo:hi]))
            split += [(a, cut), (cut + 1, b)]
        else:
            split.append((a, b))
    lines = split
    picked, count = [], 0
    for top, bottom in reversed(lines):
        groups = _groups(ink[top:bottom], 1.6 * ch)
        if count + len(groups) > want:
            return None
        picked.insert(0, (top, bottom, groups))
        count += len(groups)
        if count == want:
            break
    if count != want or len(picked) == len(lines):
        return None  # (it's all choices and no question: not this kind of page)
    marks, rows, parts = [], [], []
    for top, bottom, groups in picked:
        for a, b in groups:
            words = _groups(ink[top:bottom, a:b], 0.22 * ch)
            if len(words) < 2:
                return None
            la, lb = words[0]
            if lb - la > 1.6 * ch:
                return None  # (doesn't start with a letter like "a." or "B.")
            size = max(lb - la, bottom - top)
            cx, cy = X0 + a + (la + lb) / 2, Y0 + (top + bottom) / 2
            marks.append((int(cx - size * 0.75), int(cy - size * 0.75), int(cx + size * 0.75), int(cy + size * 0.75)))
            #(where its letter and its words are printed exactly, to write them again if need be)
            def tight(x0, x1):
                rows_ = np.nonzero(ink[top:bottom, a + x0:a + x1].any(axis=1))[0]
                return (X0 + a + x0, Y0 + top + int(rows_[0]), X0 + a + x1, Y0 + top + int(rows_[-1]) + 1)
            parts.append({'letter': tight(la, lb), 'words': tight(words[1][0], words[-1][1])})
            rows.append((X0 + a - int(0.3 * ch), Y0 + top - int(0.25 * ch), X0 + b + int(0.3 * ch), Y0 + bottom + int(0.25 * ch)))
    return marks, rows, parts


def color_to_black(img, boxes):
    """The page picture with colored writing in these boxes made the same dark as the page's
    black writing (an answer key prints the right choice in red or brown; on the quiz it would
    give the answer away), in its own letters; anything not colored is left as it is (the owner,
    2026-10-19). Returns a copy."""
    from PIL import Image
    a = np.asarray(img.convert('RGB')).astype(np.float32)
    parts, colored_all, black_all = [], [], []
    for (x0, y0, x1, y1) in boxes:
        x0, y0 = max(0, x0), max(0, y0)
        part = a[y0:y1, x0:x1]
        if not part.size:
            continue
        sat = part.max(axis=2) - part.min(axis=2)
        dark = part.min(axis=2)
        colored = sat > 25
        parts.append((y0, y1, x0, x1, colored))
        colored_all.append(dark[colored & (dark < 200)])
        black_all.append(dark[~colored & (dark < 200)])
    colored_all = np.concatenate(colored_all) if colored_all else np.array([])
    black_all = np.concatenate(black_all) if black_all else np.array([])
    if not colored_all.size:
        return img.convert('RGB').copy()
    #(how dark the darkest colored ink is, and the black ink, so the one is scaled to the other;
    #each colored pixel's darkest channel is its share of ink, so soft edges stay soft)
    c = float(np.percentile(colored_all, 5))
    b = float(np.percentile(black_all, 5)) if black_all.size else 25.0
    k = (255.0 - b) / max(1.0, 255.0 - c)
    for (y0, y1, x0, x1, colored) in parts:
        part = a[y0:y1, x0:x1]
        gray = 255.0 - (255.0 - part.min(axis=2)) * k
        for ch_ in range(3):
            plane = part[..., ch_]
            plane[colored] = gray[colored]
    return Image.fromarray(a.clip(0, 255).astype(np.uint8))


def _colored_share(rgb, box):
    """How much of the ink in a box is colored (an answer key's red or brown)."""
    x0, y0, x1, y1 = box
    part = rgb[max(0, y0):y1, max(0, x0):x1].astype(np.int16)
    if not part.size:
        return 0.0
    ink = part.min(axis=2) < 170
    if not ink.any():
        return 0.0
    return float(((part.max(axis=2) - part.min(axis=2)) > 40)[ink].mean())


def erase_answers(img, slots):
    """A page printed with its answers in an answer column (an answer key): each answer erased, in
    the paper's own color, leaving the table's ruled lines (the rows that are mostly ink) as they
    are (the owner, 2026-10-19). Returns (picture, changed?)."""
    boxes = [(s['erase'], bool(s.get('erase_plain'))) for s in slots.values() if s.get('erase')]
    if not boxes:
        return img, False
    from scipy import ndimage
    out = np.asarray(img.convert('RGB')).copy()
    H, W = out.shape[:2]
    full = ink_mask(np.asarray(img.convert('L')))
    for b, plain in boxes:
        x0, y0, x1, y1 = px(b, W, H)
        ink = full[y0:y1, x0:x1].copy()
        if not ink.size:
            continue
        if plain:
            #(an answer printed on a plain line, after its question: no table lines to keep, and a
            #letter's strokes in a box that tight would pass for them)
            area = out[y0:y1, x0:x1]
            paper = area[~full[y0:y1, x0:x1]]
            area[:] = np.median(paper, axis=0).astype(np.uint8) if paper.size else 255
            continue
        #(the whole cell painted, not just the dark pixels: the pale edges of letters would stay
        #as gray ghosts; the table's lines, and a pixel either side of them, are kept)
        rules = ndimage.binary_dilation(ink.mean(axis=1) > 0.8, iterations=1)
        uprights = ndimage.binary_dilation(ink.mean(axis=0) > 0.8, iterations=1)
        ink = np.ones_like(ink)
        ink[rules] = False
        ink[:, uprights] = False
        area = out[y0:y1, x0:x1]
        paper = area[~full[y0:y1, x0:x1]]
        color = np.median(paper, axis=0).astype(np.uint8) if paper.size else np.array([255, 255, 255], np.uint8)
        area[ink] = color
    from PIL import Image
    return Image.fromarray(out), True


def clean_answer_key(img, page, slots, font_dir):
    """A page printed as an answer key (its right choices in color, or color and bold) gives the
    answers away. Then every lettered choice on it is written again, all alike, in the font closest
    to the page's own, at the same place and size; the letters stay where they were printed, so the
    circle a student draws still goes round them (the owner, 2026-10-19). Returns (picture, changed?)."""
    from PIL import Image, ImageDraw, ImageFont
    rgb = np.asarray(img.convert('RGB'))
    H, W = rgb.shape[:2]
    probs = {p['id']: p for p in page.get('problems') or []}
    lettered = [(pid, s) for pid, s in slots.items() if s.get('lettered') and s.get('parts')]
    if not lettered:
        return img, False
    boxes = [px(pt['words'], W, H) for _pid, s in lettered for pt in s['parts']]
    shares = [_colored_share(rgb, b) for b in boxes]
    if not any(x > 0.3 for x in shares):
        return img, False
    #first the colored answers made black; that's enough unless they're bolder than the rest too
    rows = [px(r, W, H) for _pid, s in lettered for r in s['rows']]
    img = color_to_black(img, rows)
    rgb = np.asarray(img.convert('RGB'))
    def density(b):
        x0, y0, x1, y1 = b
        part = rgb[max(0, y0):y1, max(0, x0):x1]
        return float((part.min(axis=2) < 140).mean()) if part.size else 0.0
    answers = [density(b) for b, sh in zip(boxes, shares) if sh > 0.3]
    others = [density(b) for b, sh in zip(boxes, shares) if sh < 0.05]
    if not answers or not others or np.median(answers) < 1.12 * np.median(others):
        return img, True
    # the page's own black, and the font closest to its plain (not colored) choices
    plain, samples, fake = [], {}, {}
    for pid, s in lettered:
        choices = probs.get(pid, {}).get('choices') or []
        for k, pt in enumerate(s['parts']):
            if k < len(choices) and _colored_share(rgb, px(pt['words'], W, H)) < 0.05 and len(samples) < 6:
                key = '{}:{}'.format(pid, k)
                fake[key] = {'text': pt['words']}
                samples[key] = choices[k]
            plain.append(px(pt['words'], W, H))
    font_name = pick_font(img, page, fake, samples, font_dir) if samples else 'NotoSans-Regular.ttf'
    darks = np.concatenate([rgb[y0:y1, x0:x1].reshape(-1, 3) for (x0, y0, x1, y1) in plain]) if plain else np.zeros((1, 3))
    darks = darks[darks.min(axis=1) < 120]
    ink_color = tuple(int(v) for v in np.median(darks, axis=0)) if darks.size else (30, 30, 30)
    if max(ink_color) - min(ink_color) > 40:
        ink_color = (30, 30, 30)
    out = img.convert('RGB').copy()
    draw = ImageDraw.Draw(out)
    #one size for every choice: the one that makes each plain choice's words as wide as printed
    probe = ImageFont.truetype(os.path.join(font_dir, font_name), 100)
    fits = []
    for pid, s in lettered:
        choices = probs.get(pid, {}).get('choices') or []
        for k, pt in enumerate(s['parts']):
            if k < len(choices) and _colored_share(np.asarray(img.convert('RGB')), px(pt['words'], W, H)) < 0.05:
                wx0, _a, wx1, _b = px(pt['words'], W, H)
                width = probe.getlength(choices[k])
                if width > 0:
                    fits.append(100.0 * (wx1 - wx0) / width)
    size = int(round(float(np.median(fits)))) if fits else 14
    font = ImageFont.truetype(os.path.join(font_dir, font_name), max(6, size))
    for pid, s in lettered:
        p = probs.get(pid, {})
        choices = p.get('choices') or []
        text = p.get('text') or ''
        for k, pt in enumerate(s['parts']):
            if k >= len(choices):
                continue
            lx0, ly0, lx1, ly1 = px(pt['letter'], W, H)
            wx0, wy0, wx1, wy1 = px(pt['words'], W, H)
            # the letter as printed ("a." or "B."), found in QuizScan's text before this choice
            m = re.search(r'([A-Za-z])\s*([.)])\s*' + re.escape(choices[k]), text)
            label = (m.group(1) + m.group(2)) if m else 'ABCDEFGH'[k] + '.'
            cap = max(4, ly1 - ly0)
            # cover the printed choice with the paper around it
            area = rgb[max(0, ly0 - 3):wy1 + 3, max(0, lx0 - 3):wx1 + 3].reshape(-1, 3)
            paper = tuple(int(v) for v in np.median(area[area.min(axis=1) > 180], axis=0)) if (area.min(axis=1) > 180).any() else (255, 255, 255)
            pad = max(2, int(0.15 * cap))
            draw.rectangle((lx0 - pad, min(ly0, wy0) - pad, max(wx1, lx1) + pad, max(ly1, wy1) + pad), fill=paper)
            base = ly1  # (letters stand on the line the printed letter stood on)
            draw.text((lx0, base), label, font=font, fill=ink_color, anchor='ls')
            draw.text((wx0, base), choices[k], font=font, fill=ink_color, anchor='ls')
    return out, True


def _runs(row, minlen):
    """[(start, end)] of the runs of True in a row at least minlen long."""
    d = np.diff(np.concatenate(([0], row.astype(np.int8), [0])))
    starts, ends = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
    return [(a, b) for a, b in zip(starts, ends) if b - a >= minlen]


def _drawn_boxes(ink, ch):
    """Answer boxes drawn as a rectangle (square or rounded corners), found by their edges, so
    they count even when they touch other ink, e.g. a box sitting on a speech bubble's border
    (the owner, 2026-10-19: _frame needs the box to be a blob of its own). A box: a top and a
    bottom edge of the same length, sides joining them, empty inside. [(x0, y0, x1, y1)] in the
    region's pixels."""
    h, w = ink.shape
    edges = []  # [y0, y1, x0, x1]: rows of a straight edge, a line or two thick
    for y in range(h):
        for a, b in _runs(ink[y], int(2.5 * ch)):
            for e in edges:
                if y - e[1] <= 2 and abs(a - e[2]) <= 3 and abs(b - e[3]) <= 3:
                    e[1] = y + 1
                    break
            else:
                edges.append([y, y + 1, a, b])
    edges = [e for e in edges if e[1] - e[0] <= max(3, 0.35 * ch)]
    out = []
    for top in edges:
        for bot in edges:
            gap = bot[0] - top[1]
            if not (0.8 * ch <= gap <= 5 * ch):
                continue
            tol = max(4, int(0.06 * (top[3] - top[2])))
            if abs(top[2] - bot[2]) > tol or abs(top[3] - bot[3]) > tol:
                continue
            a, b = min(top[2], bot[2]), max(top[3], bot[3])
            r = int(0.5 * gap) + 2  # (rounded corners: the sides stand a little outside the edges)
            k = max(3, int(0.2 * gap))
            mid = ink[top[1]:bot[0]]
            left = mid[:, max(0, a - r):a + k].any(axis=1).mean()
            right = mid[:, max(0, b - k):min(w, b + r)].any(axis=1).mean()
            if left < 0.7 or right < 0.7:
                continue
            inside = ink[top[1] + 2:bot[0] - 2, a + k:b - k]
            if not inside.size:
                continue
            #(a line crossing it, like the bubble's border it sits on, isn't writing inside it)
            rows = inside.mean(axis=1)
            inside = inside[rows < 0.5]
            if inside.size and inside.mean() > 0.04:
                continue
            out.append((max(0, a - 1), top[0], min(w, b + 1), bot[1]))
    return out


def _answer_cell(full, box_px, ch):
    """A table with a column to answer in, right of the questions ("1. What number is on...? | 95"):
    the cell on the problem's row right of the upright line after its words. Its printed answer,
    when the page is an answer key, is erased from the page (the owner, 2026-10-19). (x0, y0, x1, y1)
    in page pixels, or None."""
    H, W = full.shape
    x0, y0, x1, y1 = box_px
    h = max(1, y1 - y0)
    cy = (y0 + y1) // 2
    def ruled(y_from, y_to, step):
        for y in range(y_from, y_to, step):
            #(one unbroken run, not just a lot of ink: a long line of text isn't a ruled line)
            if 0 <= y < H and _runs(full[y, x0:W], int(0.6 * (W - x0))):
                return y
        return None
    top, bottom = ruled(cy, max(-1, y0 - h), -1), ruled(cy, min(H, y1 + h), 1)
    if top is None and bottom is None:
        return None
    #(the first row of a table can have no ruled line above it, nor the last one below it: there
    #the column's upright line starts or stops)
    a, b = (top if top is not None else y0) + 2, (bottom if bottom is not None else y1) - 1
    if b - a < 1.2 * ch:
        return None
    upright = full[a:b].mean(axis=0) > 0.85
    for x in range(x0 + (x1 - x0) // 2, W):
        if upright[x]:
            if top is None:
                top = y0
                while top > 0 and full[top - 1, x]:
                    top -= 1
            if bottom is None:
                bottom = y1
                while bottom < H - 1 and full[bottom + 1, x]:
                    bottom += 1
            break
    if top is None or bottom is None or bottom - top < 1.2 * ch:
        return None
    band = full[top + 2:bottom - 1]
    upright = band.mean(axis=0) > 0.85
    x = x0 + (x1 - x0) // 2
    while x < W and not upright[x]:
        x += 1
    if x >= W:
        return None
    while x < W and upright[x]:
        x += 1
    c0 = x
    #(the column ends where the ruled lines above and below it end, whichever goes further: the
    #table's first line can stop at the column's line)
    end = c0
    for y in (top, bottom):
        e = c0
        while e < W and not upright[e] and full[max(0, y - 1):min(H, y + 2), e].any():
            e += 1
        end = max(end, e)
    if end - c0 < max(4 * ch, 0.08 * W):
        return None
    #(the question's own words are left of the line)
    if not full[top + 2:bottom - 1, x0:c0 - 2].any():
        return None
    return (c0 + 2, top + 2, end - 2, bottom - 1)


def _last_word(ink, X0, Y0, ch):
    """The last word of the last line of ink in a problem (its "???"), in page pixels, or None."""
    rows = np.nonzero(ink.any(axis=1))[0]
    if not rows.size:
        return None
    # the lines: runs of rows with ink, split where there's a gap
    lines, start = [], rows[0]
    for a, b in zip(rows, rows[1:]):
        if b - a > max(2, 0.25 * ch):
            lines.append((start, a + 1)); start = b
    lines.append((start, rows[-1] + 1))
    y0, y1 = lines[-1]
    cols = np.nonzero(ink[y0:y1].any(axis=0))[0]
    if not cols.size:
        return None
    # its words: split where the gap is wider than a space
    words, start = [], cols[0]
    for a, b in zip(cols, cols[1:]):
        if b - a > max(3, 0.45 * ch):
            words.append((start, a + 1)); start = b
    words.append((start, cols[-1] + 1))
    x0, x1 = words[-1]
    pad = int(0.25 * ch)
    return (X0 + x0 - pad, Y0 + y0 - pad, X0 + x1 + pad, Y0 + y1 + pad)


def _bands(full, x0, x1):
    """The printed lines in this stretch of the page, top to bottom: [(y0, y1)] in page pixels."""
    prof = full[:, max(0, x0):max(x0 + 1, x1)].sum(axis=1)
    on = prof >= max(2, 0.01 * (x1 - x0))
    out, start, gap = [], None, 0
    for y, v in enumerate(on):
        if v:
            if start is None:
                start = y
            gap = 0
        elif start is not None:
            gap += 1
            if gap > 2:
                if y - gap - start >= 4:
                    out.append((start, y - gap + 1))
                start, gap = None, 0
    if start is not None and len(on) - start >= 4:
        out.append((start, len(on)))
    return out


def snap_boxes(img_or_mask, page):
    """QuizScan's boxes put on the page's own printed lines (the owner, 2026-10-20: on a grainy,
    crooked photo its boxes crept down the page, a whole row off by the bottom). For each column
    of problems, the stretch and shift that best lays their boxes over the printed lines is
    found; then each one-line problem is moved onto its nearest line, unless two would share
    one. Returns the page with corrected boxes (a copy); boxes that already fit are left alone."""
    if hasattr(img_or_mask, 'convert'):
        full = ink_mask(np.asarray(img_or_mask.convert('L')))
    else:
        full = img_or_mask
    H, W = full.shape
    probs = [dict(p) for p in page.get('problems') or []]
    #(only problems printed on one line: others span several, and choice questions are matched
    #by their marks instead, _rows_of_marks)
    boxed = [p for p in probs if isinstance(p.get('box'), dict)
             and p.get('type') not in ('choice_one', 'choice_many', 'truefalse', 'paper', 'essay')
             and len([t for t in (p.get('text') or '').split('\n') if t.strip()]) == 1]
    #columns: problems whose boxes overlap side to side
    cols = []
    for p in sorted(boxed, key=lambda q: q['box']['left']):
        x0, _y0, x1, _y1 = px(p['box'], W, H)
        for c in cols:
            if x0 < c['x1'] and x1 > c['x0']:
                c['items'].append(p)
                c['x0'], c['x1'] = min(c['x0'], x0), max(c['x1'], x1)
                break
        else:
            cols.append({'x0': x0, 'x1': x1, 'items': [p]})
    for c in cols:
        items = c['items']
        if len(items) < 3:
            continue
        boxes = [px(p['box'], W, H) for p in items]
        bh = float(np.median([b[3] - b[1] for b in boxes]))
        #(lines about as tall as the problems' own: not a big title, not a speck)
        bands = [b for b in _bands(full, c['x0'], c['x1']) if 0.35 * bh <= b[1] - b[0] <= 1.8 * bh]
        if len(bands) < 2:
            continue
        mids = np.array([(a + b) / 2.0 for a, b in bands])
        cy = np.array([(b[1] + b[3]) / 2.0 for b in boxes])
        heights = sorted(b[3] - b[1] for b in boxes)
        cap = max(4.0, 0.6 * float(np.median(np.diff(np.sort(cy)))) if len(cy) > 1 else 0.02 * H)

        def cost(a, b):
            pred = a * cy[None, :] + np.atleast_1d(b)[:, None]
            k = np.clip(np.searchsorted(mids, pred), 1, len(mids) - 1)
            near = np.where(np.abs(pred - mids[k - 1]) <= np.abs(pred - mids[k]), k - 1, k)
            d = np.minimum(np.abs(pred - mids[k - 1]), np.abs(pred - mids[k]))
            #(two problems on one line is wrong: each costs as much as a miss)
            srt = np.sort(near, axis=1)
            twice = (np.diff(srt, axis=1) == 0).sum(axis=1)
            #(and the smaller the change from QuizScan's boxes, the better)
            return np.minimum(d, cap).sum(axis=1) + cap * twice + 0.02 * np.abs(np.atleast_1d(b)) + 20 * cap * abs(a - 1)

        best = (float(cost(1.0, 0.0)[0]), 1.0, 0.0)
        if best[0] <= 0.15 * cap * len(items):
            fit = (1.0, 0.0)
        else:
            for a in np.arange(0.85, 1.1501, 0.0025):
                bs = (mids[:, None] - a * cy[None, :]).ravel()
                bs = bs[np.abs(bs) <= 0.12 * H]
                if not bs.size:
                    continue
                cs = cost(a, bs)
                i = int(np.argmin(cs))
                if cs[i] < best[0] - 1e-6:
                    best = (float(cs[i]), float(a), float(bs[i]))
            fit = (best[1], best[2])
        a, b = fit
        pred = a * cy + b
        k = np.clip(np.searchsorted(mids, pred), 1, len(mids) - 1)
        near = np.where(np.abs(pred - mids[k - 1]) <= np.abs(pred - mids[k]), k - 1, k)
        taken = {}
        for i, n in enumerate(near):
            taken.setdefault(int(n), []).append(i)
        for i, p in enumerate(items):
            x0, y0, x1, y1 = boxes[i]
            h = y1 - y0
            n = int(near[i])
            band = bands[n]
            one_line = h <= 2.2 * (band[1] - band[0]) + 4
            if one_line and len(taken[n]) == 1 and abs(pred[i] - mids[n]) <= cap:
                pad = max(2, int(0.15 * (band[1] - band[0])))
                ny0, ny1 = min(band[0] - pad, int(round(mids[n] - h / 2.0))), max(band[1] + pad, int(round(mids[n] + h / 2.0)))
            else:
                ny0, ny1 = int(round(a * y0 + b)), int(round(a * y1 + b))
            ny0, ny1 = max(0, ny0), min(H, ny1)
            if ny1 - ny0 >= 4 and (ny0, ny1) != (y0, y1):
                p['box'] = frac(x0, ny0, x1, ny1, W, H)
                if p.get('number_box'):
                    nb = px(p['number_box'], W, H)
                    dy = ny0 - y0
                    p['number_box'] = frac(nb[0], max(0, nb[1] + dy), nb[2], min(H, nb[3] + dy), W, H)
    return dict(page, problems=probs)


def _printed_number(p, ink, ch, X0, Y0):
    """The printed number, e.g. "1 a.", when it has no box of its own: the first run of ink before
    a wide gap, so it's never covered over (the owner, 2026-10-20). [(x0, y0, x1, y1)] in page
    pixels, or []."""
    num = (p.get('number') or '').strip()
    if not num or not (p.get('text') or '').strip().startswith(num):
        return []
    #(a column with a speck or two of grain is still a gap, and so is a thin stray mark)
    from scipy import ndimage
    on = ndimage.binary_opening(ink.sum(axis=0) >= 3, structure=np.ones(max(2, int(0.2 * ch)), bool))
    cols = np.nonzero(on)[0]
    if not cols.size:
        return []
    gaps = np.nonzero(np.diff(cols) > 1.2 * ch)[0]
    if not gaps.size:
        return []
    end = cols[gaps[0]] + 1
    #(about as wide as the number's own letters, no more)
    if end - cols[0] > (len(num) + 1) * 0.9 * ch:
        return []
    rows = np.nonzero(ink[:, cols[0]:end].any(axis=1))[0]
    return [(int(cols[0] + X0), int(rows[0] + Y0), int(end + X0), int(rows[-1] + 1 + Y0))]


def _wording(ink, full, rgb, number, cut, ch, X0, Y0):
    """A problem's printed wording, to be covered and written again: its ink without its number,
    pictures and answer place. (box as fractions, paper color '#rrggbb') or (None, None)."""
    H, W = full.shape
    mask = _blank_out(ink, number + [cut], X0, Y0)
    if not mask.any():
        return None, None
    # (specks left over at the edges are not wording)
    keep = _components(mask)
    keep = [k for k in keep if ((k[3] - k[1]) >= 0.4 * ch or (k[2] - k[0]) >= 0.4 * ch) and k[4] >= 0.15 * ch * ch]
    #(the words come before the answer place on their line: a mark past its start, e.g. an
    #icon sitting on the line, isn't wording, the owner, 2026-10-20)
    before = [k for k in keep if k[2] <= cut[0] - X0 + 0.2 * ch]
    if before and cut[1] - Y0 <= np.median([k[3] for k in before]):
        keep = before
    if not keep:
        return None, None
    tx0, ty0 = min(k[0] for k in keep), min(k[1] for k in keep)
    tx1, ty1 = max(k[2] for k in keep), max(k[3] for k in keep)
    #(covered in the paper's own color, not white: a cream or colored page stays as it is)
    area = rgb[ty0 + Y0:ty1 + Y0, tx0 + X0:tx1 + X0]
    paper = area[~full[ty0 + Y0:ty1 + Y0, tx0 + X0:tx1 + X0]]
    color = '#%02x%02x%02x' % tuple(int(v) for v in np.median(paper, axis=0)) if paper.size else None
    return frac(tx0 + X0, ty0 + Y0, tx1 + X0, ty1 + Y0, W, H), color


def wording_box(img, p, answer):
    """For an answer place the teacher put on the page by hand (scan draft, the owner,
    2026-10-20): the problem's printed wording beside it, to cover and write each student's
    numbers over. (box, paper color) or (None, None)."""
    full = ink_mask(np.asarray(img.convert('L')))
    rgb = np.asarray(img.convert('RGB'))
    H, W = full.shape
    pictures = []
    x0, y0, x1, y1 = px(p['box'], W, H)
    padx, pady = int(0.012 * W), int(0.008 * H)
    X0, Y0, X1, Y1 = max(0, x0 - padx), max(0, y0 - pady), min(W, x1 + padx), min(H, y1 + pady)
    ink = _blank_out(full[Y0:Y1, X0:X1], pictures, X0, Y0)
    ch = _char_height(_components(ink), H)
    number = [px(p['number_box'], W, H)] if p.get('number_box') else _printed_number(p, ink, ch, X0, Y0)
    return _wording(ink, full, rgb, number, px(answer, W, H), ch, X0, Y0)


def _text_width(text):
    """About how wide a piece of printed text is, in letter widths: capitals and m/w wide, i/l/t
    and punctuation narrow (a plain letter count puts a word boundary a word off on a long line)."""
    w = 0.0
    for c in text:
        if c in 'mwMW':
            w += 1.45
        elif c.isupper() or c.isdigit():
            w += 1.15
        elif c in "iljtfr.,:;'’!|() ":
            w += 0.5
        else:
            w += 1.0
    return w


def _printed_answer(p, ink, number, ch, X0, Y0, X1):
    """An answer key's line, "1. What is the first book in the Bible? Genesis.": the question, then
    its answer printed after the "?" on the same line (the owner, 2026-10-20, "bible quiz2"). Returns
    (where the student types: from the answer's first word on, with room to write; the printed
    answer's words, to erase), in page pixels, or None when the line isn't one."""
    text = ' '.join((p.get('text') or '').split())
    said = ' '.join(str(p.get('answer') or '').split()).rstrip('.')
    m = re.match(r'^(.*\?)\s+(\S.*?)\.?$', text)
    if not m or not said:
        return None
    printed = m.group(2).rstrip('.')
    #(only when what follows the "?" is the problem's own answer, or starts with it: never a
    #question that just goes on after a "?")
    if not (printed.lower() == said.lower() or printed.lower().startswith(said.lower()) or said.lower().startswith(printed.lower())):
        return None
    words = _blank_out(ink, number, X0, Y0)
    lines = _text_lines(words, ch)
    if not lines:
        return None
    y0, y1 = lines[-1]
    #(a space between words: a fifth of a letter's height or more, 3 pixels on a small scan; the
    #letters of a word touch or sit a pixel apart)
    found = _groups(words[y0:y1], max(2.5, 0.22 * ch))
    if len(found) < 2:
        return None
    #(where the answer starts: the space between words nearest to where its letters' share of the
    #line puts it; counting words can be a word off, as a narrow space can go unseen; the owner,
    #2026-10-20)
    line_text = text.split('\n')[-1] if '\n' in (p.get('text') or '') else text
    share = _text_width(printed) / max(1.0, _text_width(line_text.rstrip('.')))
    left, c = found[0][0], found[-1][1]
    guess = c - share * (c - left)
    #(the answer's first word counted from the line's start (the question's words) and from its end
    #(the answer's): a narrow space gone unseen puts one of them a word off, so of the two the one
    #nearer the guess; the guess alone when neither fits)
    question = m.group(1).split('\n')[-1] if '\n' in (p.get('text') or '') else m.group(1)
    if len(found) == len(line_text.split()):
        k = len(question.split())  # every word seen: counted exactly
    else:
        counted = [i for i in (len(question.split()), len(found) - len(printed.split())) if 1 <= i < len(found)]
        k = min(counted or range(1, len(found)), key=lambda i: abs(found[i][0] - guess))
    a = found[k][0]
    #(not more than about the answer's length, and a real gap before it: else it isn't found)
    if (c - a) > (len(printed) + 4) * 0.9 * ch or a - found[k - 1][1] < 0.18 * ch:
        return None
    pad = max(2, int(0.2 * ch))
    erase = (X0 + a - pad, Y0 + y0 - pad, X0 + c + pad, Y0 + y1 + pad)
    #(room to type a longer answer than the printed one, up to the problem's right edge)
    right = max(X0 + c + pad, min(X1, X0 + a + int(14 * ch)))
    answer = (X0 + a - pad, Y0 + y0 - int(0.35 * ch), right, Y0 + y1 + int(0.35 * ch))
    return answer, erase


def find_slots(img, page, covered=()):
    """Where each problem on a QuizScan page is answered. img: the flat page (PIL); page:
    QuizScan's page dict; covered: ids of problems whose numbers change (their wording is
    covered and written again for each student).

    Returns {problem id: slot}. A slot is one of
      {'kind': 'field', 'answer': box, 'text': box or None, 'char': letter height}
      {'kind': 'choices', 'marks': [box...], 'rows': [box...]}
      {'kind': 'paper'}
    and problems not in it are taken the usual way, under the page."""
    #(a problem QuizScan couldn't place (no box) is answered under the page; the rest are found
    #without it: the owner, 2026-10-19)
    page = dict(page, problems=[p for p in page.get('problems') or [] if isinstance(p.get('box'), dict)],
                pictures=[p for p in page.get('pictures') or [] if isinstance(p.get('box'), dict)])
    full = ink_mask(np.asarray(img.convert('L')))
    #(QuizScan's boxes laid on the page's own lines first: snap_boxes, the owner, 2026-10-20)
    page = snap_boxes(full, page)
    #(for the little boxes and circles before choices: a more sensitive look, as some pages print
    #them in pale gray, and at the usual one their edges break up: the owner, 2026-10-19)
    pale = ink_mask(np.asarray(img.convert('L')), CONTRAST / 2)
    rgb = np.asarray(img.convert('RGB'))
    H, W = full.shape
    pictures = [px(p['box'], W, H) for p in page.get('pictures') or []]
    out = {}
    #a list of choice questions each with its line of marks: matched line by line, in order
    choice = [p for p in page.get('problems') or [] if p.get('type') in ('choice_one', 'choice_many', 'truefalse')]
    by_line = {}
    if len(choice) >= 3:
        wants = {len(p.get('choices') or []) or (2 if p.get('type') == 'truefalse' else 0) for p in choice}
        if len(wants) == 1 and min(wants) >= 2:
            want = wants.pop()
            hs = [px(p['box'], W, H) for p in choice]
            ch_all = float(np.median([b[3] - b[1] for b in hs])) * 0.6
            #(the usual look and the more sensitive one: whichever lines up more questions)
            tries = [_rows_of_marks(m, page, pictures, ch_all, want, hs) for m in (full, pale)]
            tries = [t for t in tries if t]
            lines = max(tries, key=lambda t: sum(1 for ms in t if ms)) if tries else None
            if lines:
                for p, ms in zip(choice, lines):
                    #(None: its line doesn't show all its marks: answered under the page, not
                    #guessed from QuizScan's box, which may be a line off)
                    by_line[p['id']] = ms or 'skip'
    for p in page.get('problems') or []:
        if p.get('type') == 'paper':
            out[p['id']] = {'kind': 'paper'}
            continue
        if p.get('type') == 'essay':
            continue
        box_px = px(p['box'], W, H)
        x0, y0, x1, y1 = box_px
        padx, pady = int(0.012 * W), int(0.008 * H)
        X0, Y0, X1, Y1 = max(0, x0 - padx), max(0, y0 - pady), min(W, x1 + padx), min(H, y1 + pady)
        number = [px(p['number_box'], W, H)] if p.get('number_box') else []
        ink = _blank_out(full[Y0:Y1, X0:X1], pictures, X0, Y0)
        comps = _components(ink)
        ch = _char_height(comps, H)
        if not number:
            number = _printed_number(p, ink, ch, X0, Y0)

        if p.get('type') in ('choice_one', 'choice_many', 'truefalse'):
            want = len(p.get('choices') or []) or (2 if p.get('type') == 'truefalse' else 0)
            if not want:
                continue
            region = (X0, Y0, min(W, X1 + padx), Y1)
            marks = by_line.get(p['id']) or _marks(full, region, pictures + number, ch, want) or _marks(pale, region, pictures + number, ch, want)
            if marks == 'skip':
                continue
            if not marks:
                #the boxes can be printed well away from the words, e.g. a column of TRUE / FALSE
                #boxes at the right edge: look across the page on the problem's own lines, leaving
                #out the other problems (the owner, 2026-10-18)
                others = [px(o['box'], W, H) for o in page['problems'] if o is not p]
                others = [(a - padx, b - pady, c + padx, d + pady) for (a, b, c, d) in others]
                marks = _marks(full, (0, Y0, W, Y1), pictures + number + others, ch, want) or _marks(pale, (0, Y0, W, Y1), pictures + number + others, ch, want)
            if not marks:
                #choices with letters and nothing to check: below the problem's box a little too
                #(QuizScan's box can stop short of the last line), never into the next problem
                below = [px(o['box'], W, H)[1] for o in page['problems'] if o is not p
                         and px(o['box'], W, H)[1] > y0 + 2 and px(o['box'], W, H)[0] < x1 and px(o['box'], W, H)[2] > x0]
                reach = min([y1 + int(3 * ch)] + [t - 2 for t in below])
                found = _lettered(full, (X0, Y0, X1, min(H, max(Y1, reach))), pictures + number, ch, want, box_bottom=y1)
                if found:
                    lm, lr, lp = found
                    out[p['id']] = {'kind': 'choices', 'lettered': True, 'marks': [frac(*m, W, H) for m in lm],
                                    'rows': [frac(*r, W, H) for r in lr],
                                    'parts': [{k: frac(*v, W, H) for k, v in pt.items()} for pt in lp]}
                    continue
                cells = _cells(full, box_px, pictures, want)
                if cells:
                    #(a cell is its own button: the whole cell, a circle drawn in it when picked)
                    out[p['id']] = {'kind': 'choices', 'cells': True, 'marks': [frac(*c, W, H) for c in cells],
                                    'rows': [frac(*c, W, H) for c in cells]}
                    continue
            if marks:
                rows = []
                printed = p.get('choices') or (['False', 'False'] if p.get('type') == 'truefalse' else [])
                for k, (a, b, c, d) in enumerate(marks):
                    # the choice's words: from the mark to the end of its words, never into the
                    # next choice on the same line nor across a wide gap
                    stop = W
                    if k < len(printed):
                        # (about as long as its printed words, at most)
                        stop = min(W, c + int((len(printed[k]) + 2) * 0.9 * ch))
                    for (a2, b2, c2, d2) in marks:
                        if a2 > a and b2 < d and d2 > b:
                            stop = min(stop, a2 - 2)
                    line = full[b:d, c:stop].any(axis=0)
                    last, gap = c, 0
                    for x, on in enumerate(line):
                        if on:
                            last, gap = c + x + 1, 0
                        else:
                            gap += 1
                            if gap > 3 * (c - a) and last > c:
                                break
                    rows.append(frac(a, b, min(stop, last + 4), d, W, H))
                out[p['id']] = {'kind': 'choices', 'marks': [frac(*m, W, H) for m in marks], 'rows': rows}
            continue

        # a number or a word to type: the printed box or line it goes in (an answer key's line,
        # "Question? Answer.", first: its answer printed where the student types)
        keyed = _printed_answer(p, ink, number, ch, X0, Y0, X1)
        frame = None if keyed else _frame(comps, ink, X0, Y0, box_px, W, H)
        answer = cut = erase = None
        if keyed:
            answer, keyed = keyed
            cut = answer
        elif not frame:
            drawn = _drawn_boxes(ink, ch)
            if drawn:
                a, b, c, d = max(drawn, key=lambda r: (r[0], r[1]))
                frame = (a + X0, b + Y0, c + X0, d + Y0)
        if keyed:
            pass
        elif frame:
            answer = frame
            cut = frame
        else:
            cell = _answer_cell(full, box_px, ch)
            if cell:
                answer = cut = cell
                if full[cell[1]:cell[3], cell[0]:cell[2]].any():
                    erase = cell
        if answer is None:
            #(a table's ruled line across the whole problem isn't an answer line)
            lines = [l for l in _lines(comps, ch, H) if l[2] - l[0] < 0.9 * (X1 - X0)]
            if not lines:
                lines = [l for l in _ruled_runs(ink, ch) if l[2] - l[0] < 0.9 * (X1 - X0)]
            if len(lines) == 1:
                a, b, c, d = lines[0]
                a, b, c, d = a + X0, b + Y0, c + X0, d + Y0
                above = ink[:max(0, b - Y0 - 1), max(0, a - X0):max(0, c - X0)]
                text_lines = [t for t in (p.get('text') or '').split('\n') if t.strip()]
                if text_lines and set(text_lines[-1].strip()) <= set('_ ') and above.any():
                    # a sum in a column: the answer goes under its line
                    answer = (a, d + int(0.15 * ch), c, min(H, d + int(1.6 * ch)))
                else:
                    answer = (a, max(0, b - int(1.5 * ch)), c, d)
                    #(on the problem's own printed line, e.g. "1- ______": centered on that line's
                    #words, so what's typed reads level with the number, not above it, while the
                    #answer line stays inside the box: the owner, 2026-10-20, the flags quiz)
                    row_mid = (y0 + y1) / 2.0
                    if (y1 - y0) <= 2.2 * ch and abs((b + d) / 2.0 - row_mid) <= 1.5 * ch:
                        h = answer[3] - answer[1]
                        top = int(round(row_mid - h / 2.0))
                        top = min(top, b)                    # the line never below the box...
                        top = max(top, d - h)                # ...nor above it
                        answer = (a, max(0, top), c, min(H, top + h))
                cut = (a, min(answer[1], b), c, max(answer[3], d))
        inline = False
        if answer is None:
            #no box or line: a question that ends in "???" (or "___" typed as text) is answered right
            #there, over its last word (the owner, 2026-10-18)
            lines_txt = [l for l in (p.get('text') or '').split('\n') if l.strip()]
            if lines_txt and re.search(r'(\?{2,}|_{3,}|\?)\s*$', lines_txt[-1]):
                #(without ruled lines and drawn frames, which aren't words)
                rules = [(a, b, c, d) for (a, b, c, d, n) in comps
                         if ((c - a) >= 2.5 * ch and (d - b) <= 0.3 * ch) or ((d - b) >= 2.5 * ch and (c - a) <= 0.3 * ch)
                         or ((c - a) >= 4 * ch and (d - b) >= 1.5 * ch and n < 0.25 * (c - a) * (d - b))]
                words = _blank_out(ink, number + [(a + X0, b + Y0, c + X0, d + Y0) for (a, b, c, d) in rules], X0, Y0)
                answer = _last_word(words, X0, Y0, ch)
                #(a word, not half the problem: anything bigger means the place wasn't found, and
                #the problem is answered under the page rather than over its own wording; the
                #owner, 2026-10-19)
                if answer and ((answer[2] - answer[0]) > 10 * ch or (answer[3] - answer[1]) > 3 * ch):
                    answer = None
                cut, inline = answer, True
        if answer is None:
            continue
        slot = {'kind': 'field', 'answer': frac(*answer, W, H), 'text': None, 'char': round(ch / H, 5)}
        if keyed:
            #(the printed answer erased in the paper's color; the student types where it was)
            slot['erase'] = frac(*keyed, W, H)
            slot['erase_plain'] = True
        if inline:
            slot['inline'] = True
        if erase:
            e0, e1 = erase[0], erase[2]
            spill = int(0.9 * ch)
            slot['erase'] = frac(e0, max(0, erase[1] - spill), e1, min(H, erase[3] + spill), W, H)
        if p['id'] in covered:
            text, paper = _wording(ink, full, rgb, number, cut, ch, X0, Y0)
            if text:
                slot['text'] = text
                if paper:
                    slot['paper'] = paper
        out[p['id']] = slot
    return out


def _ink_box(arr):
    ys, xs = np.nonzero(arr)
    if not xs.size:
        return None
    return arr[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def _sharp_first_line(gray_img, box_px):
    """A problem's printed words, first line only, as clean ink: blown up 4 times and cut sharply
    halfway between the paper and the ink (the ink detector's smoothing would make thin letters
    look bold and wipe out serifs on a small picture). None when there's nothing."""
    from PIL import Image
    x0, y0, x1, y1 = box_px
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    g = np.asarray(gray_img.crop((x0, y0, x1, y1)).resize(((x1 - x0) * 4, (y1 - y0) * 4), Image.LANCZOS)).astype(float)
    lo, hi = np.percentile(g, 3), np.percentile(g, 97)
    if hi - lo < 30:
        return None
    m = g < (lo + hi) / 2
    rows = np.nonzero(m.any(axis=1))[0]
    if not rows.size:
        return None
    end = rows[0]
    while end + 1 < m.shape[0] and m[end + 1].any():
        end += 1
    return _ink_box(m[:end + 1])


def pick_font(img, page, slots, samples, font_dir):
    """The font (a FONTS file) that looks most like the page's printed wording, judged on up
    to 6 covered problems' first lines: each font writes the same words at the printed height,
    not stretched sideways, so its width and weight count, and the drawing that overlaps the
    printed ink best wins. samples: {problem id: its printed words, as on the page}.
    NotoSans-Bold.ttf when there's nothing to judge by."""
    from PIL import Image, ImageDraw, ImageFont
    gray = img.convert('L')
    W, H = gray.size
    pairs = []
    for pid, words in samples.items():
        s = slots.get(pid) or {}
        words = (words or '').strip().split('\n')[0].strip()
        if not s.get('text') or not words:
            continue
        ink = _sharp_first_line(gray, px(s['text'], W, H))
        if ink is not None and ink.shape[0] > 8 and ink.shape[1] > 8:
            pairs.append((words, ink))
        if len(pairs) >= 6:
            break
    if not pairs:
        return 'NotoSans-Bold.ttf'
    best = (-1, 'NotoSans-Bold.ttf')
    for name in FONTS:
        try:
            font = ImageFont.truetype(os.path.join(font_dir, name), 200)
        except OSError:
            continue
        total = 0.0
        for words, ink in pairs:
            canvas = Image.new('L', (200 * (len(words) + 2), 400), 0)
            ImageDraw.Draw(canvas).text((20, 60), words, font=font, fill=255)
            drawn = _ink_box(np.asarray(canvas) > 127)
            if drawn is None:
                continue
            k = ink.shape[0] / drawn.shape[0]
            drawn = np.asarray(Image.fromarray(drawn.astype(np.uint8) * 255).resize((max(1, round(drawn.shape[1] * k)), ink.shape[0]))) > 127
            w = max(drawn.shape[1], ink.shape[1])
            a = np.zeros((ink.shape[0], w), bool); b = a.copy()
            a[:, :ink.shape[1]] = ink; b[:, :drawn.shape[1]] = drawn
            total += (a & b).sum() / max(1, (a | b).sum())
        if total / len(pairs) > best[0]:
            best = (total / len(pairs), name)
    return best[1]


def style_of(text):
    """How a covered problem's words are set in its box: 'equals' (one line ending in "=",
    spread across like "21 + 52 ="), 'column' (lines right-aligned, a sum written down)
    or 'left'."""
    lines = [l for l in (text or '').split('\n') if l.strip()]
    if len(lines) == 1 and lines[0].rstrip().endswith('='):
        return 'equals'
    if len(lines) > 1 and any(l.strip()[:1] in OPERATORS for l in lines[1:]):
        return 'column'
    return 'left'


def _skew(full):
    """How far the page's printed lines slope (radians, + when they run down to the right).
    The page is cut into upright strips; how far each strip's rows of ink sit above or below
    the next one's gives the slope (a straight line through those shifts)."""
    H, W = full.shape
    n = 8
    edges = np.linspace(int(0.05 * W), int(0.95 * W), n + 1).astype(int)
    profs = [full[:, edges[i]:edges[i + 1]].sum(axis=1).astype(np.float64) for i in range(n)]
    reach = max(4, int(0.03 * H))
    mid = n // 2
    ref = profs[mid] - profs[mid].mean()
    centers = (edges[:-1] + edges[1:]) / 2.0
    slopes = []
    for i in range(n):
        if i == mid or profs[i].sum() < 50 or profs[mid].sum() < 50:
            continue
        a = profs[i] - profs[i].mean()
        vals = []
        for d in range(-reach, reach + 1):
            vals.append(float((ref[max(0, -d):H - max(0, d)] * a[max(0, d):H - max(0, -d)]).sum()))
        k = int(np.argmax(vals))
        if vals[k] <= 0:
            continue
        at = float(k - reach)
        #(between whole pixels: the peak's own shape, for small slopes)
        if 0 < k < len(vals) - 1:
            l, c, r = vals[k - 1], vals[k], vals[k + 1]
            den = l - 2 * c + r
            if den < 0:
                at += 0.5 * (l - r) / den
        slopes.append(at / (centers[i] - centers[mid]))
    if len(slopes) < 2:
        return 0.0
    return float(np.arctan(np.median(slopes)))


def _margin_slope(full):
    """How far the page's left margins lean (dx per dy, + when they run right going down): the
    places where printed lines start, lined up in columns down the page. None when the page
    doesn't have a column of at least 4 line starts reaching over a quarter of its height."""
    H, W = full.shape
    starts = []
    for (a, b) in _bands(full, 0, W):
        if b - a > 0.06 * H:
            continue
        cols = full[a:b].any(axis=0)
        #(the start of each run of words: after a gap of at least 3% of the page's width)
        gap, last = int(0.03 * W), -W
        for x in np.nonzero(cols)[0]:
            if x - last > gap:
                starts.append(((a + b) / 2.0, float(x)))
            last = x
    if len(starts) < 4:
        return None
    starts.sort(key=lambda p: p[1])
    tol = 0.02 * W
    groups, cur = [], [starts[0]]
    for p in starts[1:]:
        if p[1] - cur[-1][1] <= tol / 2:
            cur.append(p)
        else:
            groups.append(cur)
            cur = [p]
    groups.append(cur)
    fits = []
    for g in groups:
        ys = [p[0] for p in g]
        if len(g) >= 4 and max(ys) - min(ys) >= 0.25 * H:
            k, _c = np.polyfit(ys, [p[1] for p in g], 1)
            fits.append((len(g), float(k)))
    if not fits:
        return None
    return float(np.average([k for n, k in fits], weights=[n for n, k in fits]))


def _edge_strips(gray):
    """Dark lines down the very edges of the page (the paper's own edge, the table or the next
    page showing past it, the owner, 2026-10-20), often slanting: a mask of their pixels, or
    None. Only within the outer 2% of the page, dark in most rows, with plain paper just inside;
    a picture or a printed border at the edge isn't one."""
    from scipy import ndimage
    H, W = gray.shape
    reach = max(3, int(0.02 * W))
    inner = max(4, int(0.03 * W))
    mask = np.zeros(gray.shape, bool)
    for side in ('left', 'right'):
        zone = gray[:, :reach] if side == 'left' else gray[:, W - reach:]
        dark = zone < 110
        if dark.any(axis=1).mean() < 0.8:
            continue
        inside = gray[:, reach:reach + inner] if side == 'left' else gray[:, W - reach - inner:W - reach]
        if inside.mean() <= 200:
            continue
        dark = ndimage.binary_dilation(dark, iterations=2)
        if side == 'left':
            mask[:, :reach] |= dark
        else:
            mask[:, W - reach:] |= dark
    return mask if mask.any() else None


def level_page(img, page, full=None):
    """The flat page made level (the owner, 2026-10-20: its printed lines run straight across,
    square with the top of the page), and the dark strips at its edges painted out. QuizScan's
    boxes are turned with it. Returns (image, page); both unchanged when it's already level.
    full: a bigger copy of the same page (the owner, 2026-10-20: pictures are cut from it), made
    level the same way as measured on img; then returns (image, page, full made level)."""
    out, page, how = _level_page(img, page)
    if full is None:
        return out, page
    return out, page, _level_like(full, how)


def _level_like(full, how):
    """A bigger copy of a page made level as _level_page measured on the smaller one: the same
    edge strips painted out, the same warp (worked in bands of rows, so a big page doesn't need
    much memory at once)."""
    from PIL import Image
    from scipy import ndimage
    if how is None:
        return full
    arr = np.asarray(full.convert('RGB')).copy()
    Hf, Wf = arr.shape[:2]
    if how['strips'] is not None:
        big = Image.fromarray(how['strips'].astype(np.uint8) * 255).resize((Wf, Hf), Image.NEAREST)
        arr[np.asarray(big) > 127] = how['paper']
    if how['map'] is None:
        return Image.fromarray(arr)
    h0, h1, v0, v1 = how['map']
    s = Wf / float(how['size'][0])          # the bigger page's pixels per measured page pixel
    cx, cy = Wf / 2.0, Hf / 2.0
    xx = np.arange(Wf, dtype=np.float32)[None, :]
    kv = v0 + v1 * xx / s
    out = np.empty_like(arr)
    chans = [np.ascontiguousarray(arr[:, :, i]) for i in range(3)]
    for y0 in range(0, Hf, 256):
        yy = np.arange(y0, min(Hf, y0 + 256), dtype=np.float32)[:, None]
        sx, sy = xx + kv * (yy - cy), yy + (h0 + h1 * yy / s) * (xx - cx)
        for i in range(3):
            out[y0:y0 + yy.shape[0], :, i] = ndimage.map_coordinates(chans[i], [sy, sx], order=1, mode='constant',
                                                                     cval=how['paper'][i])
    return Image.fromarray(out)


def _level_page(img, page):
    """level_page's work: (image, page, how it was made level for _level_like, or None)."""
    from PIL import Image
    rgb = img.convert('RGB')
    gray = np.asarray(rgb.convert('L'))
    full = ink_mask(gray)
    H, W = full.shape
    paper = tuple(int(v) for v in np.median(np.asarray(rgb)[~full], axis=0)) if (~full).any() else (255, 255, 255)
    changed = False
    strips = _edge_strips(gray)
    if strips is not None:
        arr = np.asarray(rgb).copy()
        arr[strips] = paper
        rgb = Image.fromarray(arr)
        full = ink_mask(np.asarray(rgb.convert('L')))
        changed = True
    #(rows run straight across and the left edges of the lines straight down, everywhere on the
    #page: a page photographed at a slant leans more at one end than the other, so each slope
    #is measured in each third of the page and straightened there, the owner, 2026-10-20)
    def slopes(mask, along):
        """[(middle, slope)] for each third of the page along `along` (0: rows, 1: columns)."""
        n = mask.shape[along]
        out = []
        for i in range(3):
            a, b = int(i * n / 3), int((i + 1) * n / 3)
            part = mask[a:b] if along == 0 else mask[:, a:b]
            if part.sum() < 0.002 * part.size:
                continue
            k = np.tan(_skew(part if along == 0 else part.T)) if along == 0 else np.tan(_skew(part.T))
            if abs(np.degrees(np.arctan(k))) <= 4:
                out.append(((a + b) / 2.0, float(k)))
        return out

    def fit(pts):
        """slope at place t: a straight line through the thirds' slopes (or one slope)."""
        if not pts:
            return 0.0, 0.0
        if len(pts) == 1:
            return pts[0][1], 0.0
        t, k = np.array([p[0] for p in pts]), np.array([p[1] for p in pts])
        g, c = np.polyfit(t, k, 1)
        return float(c), float(g)

    cx, cy = W / 2.0, H / 2.0

    def maps(full):
        #(the slope of the whole page first: a clean page (under 0.15°) is left as it is; then
        #each third's, where it agrees with the whole page's (pictures and sparse lines in a
        #third can give a wild reading))
        whole = np.tan(_skew(full))
        if abs(np.degrees(np.arctan(whole))) < 0.15:
            h0, h1 = 0.0, 0.0
        else:
            near = [(t, k) for t, k in slopes(full, 0) if abs(np.degrees(np.arctan(k) - np.arctan(whole))) <= 0.5]
            h0, h1 = fit(near) if len(near) >= 2 else (float(whole), 0.0)
        #(the lean of the margins: one slope for the page, or none when it has no clear margins)
        v = _margin_slope(full)
        #(only on a page that's crooked across too: a clean page's margins can wander a little
        #with indents and numbers, and it mustn't be bent for that)
        crooked = max(abs(h0 + h1 * y) for y in (0, H)) >= np.tan(np.radians(0.2))
        return h0, h1, (v if crooked and v is not None and abs(v) <= 0.07 else 0.0), 0.0

    def warp(im, h0, h1, v0, v1):
        """each place on the new page comes from (x + kv(x)·(y − cy), y + kh(y)·(x − cx)) on the old one"""
        from scipy import ndimage
        arr = np.asarray(im).astype(np.float32)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        kh = h0 + h1 * yy
        kv = v0 + v1 * xx
        sx, sy = xx + kv * (yy - cy), yy + kh * (xx - cx)
        chans = [ndimage.map_coordinates(arr[:, :, i], [sy, sx], order=1, mode='constant', cval=paper[i]) for i in range(3)]
        return Image.fromarray(np.clip(np.stack(chans, axis=2), 0, 255).astype(np.uint8))

    h0, h1, v0, v1 = maps(full)
    biggest = max(abs(h0 + h1 * y) for y in (0, H)) + max(abs(v0 + v1 * x) for x in (0, W))
    if np.degrees(np.arctan(biggest)) < 0.1:
        return (rgb, page, {'strips': strips, 'paper': paper, 'map': None, 'size': (W, H)}) if changed else (img, page, None)
    once = warp(rgb, h0, h1, v0, v1)
    #(looked at again once straightened: what's left over is taken out too)
    r = maps(ink_mask(np.asarray(once.convert('L'))))
    h0, h1, v0, v1 = h0 + r[0], h1 + r[1], v0 + r[2], v1 + r[3]
    rgb = warp(rgb, h0, h1, v0, v1)

    def move(x, y):
        """where a place on the old page lands on the new one (the map turned round, by steps)"""
        u, v = x, y
        for _ in range(6):
            u = x - (v0 + v1 * u) * (v - cy)
            v = y - (h0 + h1 * v) * (u - cx)
        return u, v

    def turn(box):
        if not isinstance(box, dict):
            return box
        x0, y0, x1, y1 = box['left'] * W, box['top'] * H, box['right'] * W, box['bottom'] * H
        pts = [move(x, y) for x in (x0, x1) for y in (y0, y1)]
        #(the box keeps its size: moved by its middle, not grown to hold its moved corners)
        mx, my = sum(p[0] for p in pts) / 4.0, sum(p[1] for p in pts) / 4.0
        w, h = x1 - x0, y1 - y0
        return frac(max(0, mx - w / 2), max(0, my - h / 2), min(W, mx + w / 2), min(H, my + h / 2), W, H)

    page = dict(page, problems=[dict(p, **{k: turn(p[k]) for k in ('box', 'number_box') if p.get(k)}) for p in page.get('problems') or []],
                pictures=[dict(p, box=turn(p.get('box'))) for p in page.get('pictures') or []])
    return rgb, page, {'strips': strips, 'paper': paper, 'map': (h0, h1, v0, v1), 'size': (W, H)}


def paper_color(img, box):
    """The paper's color in this box ('#rrggbb'): the middle of what isn't ink."""
    rgb = np.asarray(img.convert('RGB'))
    H, W = rgb.shape[:2]
    x0, y0, x1, y1 = px(box, W, H)
    area = rgb[y0:y1, x0:x1]
    if not area.size:
        return '#ffffff'
    ink = ink_mask(np.asarray(img.convert('L')))[y0:y1, x0:x1]
    paper = area[~ink] if (~ink).any() else area.reshape(-1, 3)
    return '#%02x%02x%02x' % tuple(int(v) for v in np.median(paper, axis=0))
