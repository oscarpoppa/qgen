/* The faint lines between entries listed one under another (a quiz's attempts, who's online, a
   scan's pages, any .divided list) run end to end across what holds them: a table row's whole
   width, not just its cell; otherwise the card, box or pop-over they're in. On Results, each
   attempt's date and score (one cell) and its buttons (the next cell) are made the same height,
   so the line runs straight across both; on My quizzes each attempt's button is put right under
   the quiz's own (the owner, 2026-10-20). Drawn by app.css (--line-l/r, --act-r). */
(function () {
  var LINED = 'ol.attempt-list, ol.attempt-list > li + li, td.attempts > .result-attempt ~ .result-attempt, ' +
              '.online-people > li + li, .scan-progress-list > li + li, .divided > * + *';
  var HOLDER = '.pop-card, .online-pop, .scan-pop, .card, .box, details';

  function level(row) {
    var left = row.querySelectorAll('td.attempts > .result-attempt');
    var right = row.querySelectorAll('td.attempt-buttons > .result-attempt');
    var i, a, b, note, ha, hb;
    for (i = 0; i < left.length && i < right.length; i++) {
      left[i].style.minHeight = right[i].style.minHeight = '';
    }
    for (i = 0; i < left.length && i < right.length; i++) {
      a = left[i]; b = right[i];
      note = a.nextElementSibling && a.nextElementSibling.classList.contains('result-attempt-note') ? a.nextElementSibling : null;
      ha = a.offsetHeight + (note ? note.offsetHeight : 0);
      hb = b.offsetHeight;
      if (hb > ha) a.style.minHeight = (a.offsetHeight + hb - ha) + 'px';
      else if (ha > hb) b.style.minHeight = ha + 'px';
    }
  }

  //(in a folded box: nothing shows, so nothing is measured; found without laying the page out. Measuring a
  //hundred folded rows one after another, each after a change, took a fifth of a second on People: the owner, 2026-10-24)
  function folded(el) { return !!el.closest('details:not([open])'); }

  //(every line measured first, then all of them set: the page is laid out once)
  function stretchAll(els) {
    var seen = [];
    els.forEach(function (el) {
      if (folded(el) || !el.offsetParent) return;
      //(a table row first, whatever's inside it, e.g. the folded box a quiz's attempts are in)
      var holder = el.closest('tr') || (el.parentElement && el.parentElement.closest(HOLDER));
      if (!holder) return;
      var r = holder.getBoundingClientRect(), e = el.getBoundingClientRect();
      //(a row: just inside its edges; a card or pop-over: to the edges of its padding)
      var cs = getComputedStyle(holder);
      var padL = holder.tagName === 'TR' ? 12 : parseFloat(cs.paddingLeft) + parseFloat(cs.borderLeftWidth);
      var padR = holder.tagName === 'TR' ? 12 : parseFloat(cs.paddingRight) + parseFloat(cs.borderRightWidth);
      seen.push([el, Math.round(r.left + padL - e.left) + 'px', Math.round(e.right - r.right + padR) + 'px']);
    });
    seen.forEach(function (s) { s[0].style.setProperty('--line-l', s[1]); s[0].style.setProperty('--line-r', s[2]); });
  }

  //a quiz's attempts: each one's button right under the quiz's own button, at the row's right end
  //(measures only; gives back what to set, so every attempt is measured before any is changed)
  function underRowButton(li) {
    var row = li.closest('tr'), cell = row && row.querySelector('td.actions');
    if (!cell || folded(li) || !li.offsetParent) return null;
    //(centered under it: the attempts' buttons are smaller than the quiz's; a row with nothing to
    //view has no button of its own, so the place one would be: the cell's right end, inside it)
    //(the row's own Start / Continue / View if it has one; never its Move control, which is about
    //the row's folder, not an attempt)
    //(a group of icons, a student page's attempt line: its right end at the cell's right end, under
    //the row's own icons; the owner, 2026-10-21)
    var own = li.querySelector('.attempt-act-group') ? null : cell.querySelector('.quiz-row-actions > :not(.move-mini):not(form):first-child'), mid;
    if (own) { var o = own.getBoundingClientRect(); mid = (o.left + o.right) / 2; }
    else { var c = cell.getBoundingClientRect(); mid = c.right - parseFloat(getComputedStyle(cell).paddingRight) - 17; }
    var v = Math.round(li.getBoundingClientRect().right - mid) + 'px';
    return function () { li.style.setProperty('--act-r', v); };
  }

  //an open row's table (Grading's students, a problem's answers) takes its column edges from the
  //list's own columns, so Handed in sits under Attempts, To grade under To grade (the owner, 2026-10-23:
  //"line up in a columnar fashion across the site"); a stacked (phone) list keeps its own widths
  function alignColumns(d) {
    var outer = d.closest('table'), inner = d.querySelector(':scope > .answer-rows > table');
    if (!outer || !inner || !d.open || !d.offsetParent) return;
    var oh = outer.querySelector(':scope > thead'), ih = inner.querySelectorAll(':scope > thead th');
    //(only the list's headings that show: a narrow list hides some, and their width of 0 squeezed the table's columns to nothing)
    var ot = oh ? Array.prototype.filter.call(oh.querySelectorAll('th'), function (th) { return th.getBoundingClientRect().width > 0; }) : [];
    //(a list of one column, Problem history's "Quiz": nothing to line up with, so the inner table keeps its own
    //widths; fixing them there made its last column the row's whole width and the row grew without end, the
    //Student column 33 million pixels wide, found 2026-10-24)
    //(and a table of more columns than the list's, Problem history's 7 under its 5: the two left over had no width at all)
    if (!oh || getComputedStyle(oh).display === 'none' || ot.length < 2 || !ih.length || ih.length > ot.length) {
      ih.forEach(function (th) { th.style.width = ''; });
      inner.style.tableLayout = '';
      return;
    }
    inner.style.tableLayout = 'fixed';
    var n = ih.length, m = ot.length, start = ih[0].getBoundingClientRect().left;
    var mapped = Math.min(n, m) - 1, edge = start;
    for (var i = 0; i < n; i++) {
      var w = '';
      if (i < mapped) {
        //(the words line up, not the cells' edges: a cell's own padding counts)
        var next = ot[i + 1].getBoundingClientRect().left + (parseFloat(getComputedStyle(ot[i + 1]).paddingLeft) || 0) - (parseFloat(getComputedStyle(ih[i + 1]).paddingLeft) || 0);
        w = Math.round(next - edge) + 'px'; edge = next;
      }
      else if (i === n - 1 && n >= m) w = Math.round(ot[m - 1].getBoundingClientRect().width) + 'px';
      if (ih[i].style.width !== w) { ih[i].style.width = w; unsettled = true; }
    }
    //(never wider than the list itself: a row widened by its own table moves the list's headings, which widened the
    //table again, without end (Problem history, 33 million pixels: found 2026-10-24); then it keeps its own widths)
    var sum = 0;
    ih.forEach(function (th) { sum += parseFloat(th.style.width) || 0; });
    if (sum > outer.getBoundingClientRect().width + 2) {
      ih.forEach(function (th) { th.style.width = ''; });
      inner.style.tableLayout = '';
      return;
    }
    //(the last column takes what's left, so a table wider than its fixed columns doesn't spread the extra over all of them)
    var total = inner.getBoundingClientRect().width, used = 0;
    for (var k = 0; k < n - 1; k++) used += parseFloat(ih[k].style.width) || 0;
    var rest = Math.max(0, Math.round(total - used)) + 'px';
    if (n - 1 === mapped && ih[n - 1].style.width !== rest) { ih[n - 1].style.width = rest; unsettled = true; }
  }

  //an open row's contents (after its heading part) on their own shade, end to end across the row
  //(measures only; gives back what to set: every open row measured before any is changed, one layout for Expand all's 33
  //rows instead of one a row; the owner, 2026-10-24)
  function foldBody(d) {
    var row = d.closest('tr');
    if (!row || !d.open || !d.offsetParent) return null;
    var r = row.getBoundingClientRect(), e = d.getBoundingClientRect();
    var start = d.querySelector('[data-fold-body]'), sum = d.querySelector(':scope > summary');
    var top = start ? start.getBoundingClientRect().top : sum ? sum.getBoundingClientRect().bottom : e.top;
    var set = {};
    set['--body-top'] = Math.round(top - e.top) + 'px';
    //(just inside the row's own outline)
    set['--body-l'] = Math.round(r.left + 1 - e.left) + 'px';
    //(how far the row's name cell is from the row's left edge: a list with a check column starts its cell after it; an open row's groups
    //start the same distance in from the row's edge on every list, People's as Results by quiz's: the owner, 2026-10-24)
    var cell = d.closest('td');
    if (cell) set['--cell-offset'] = Math.max(0, Math.round(cell.getBoundingClientRect().left - r.left)) + 'px';
    //(what's inside can take its width from this one (an open row's contents run the row's width), so
    //the row settles only after it's applied: measured again until it stops changing; Problem
    //history's answers stopped short of the row's end otherwise)
    var right = Math.round(e.right - r.right + 1) + 'px';
    return function () {
      for (var k in set) d.style.setProperty(k, set[k]);
      if (d.style.getPropertyValue('--body-r') !== right) { d.style.setProperty('--body-r', right); unsettled = true; }
    };
  }
  function batch(els, measure) {
    var sets = Array.prototype.map.call(els, measure);
    sets.forEach(function (f) { if (f) f(); });
  }

  var queued = false, unsettled = false, again = 0;
  function all() {
    queued = false;
    unsettled = false;
    document.querySelectorAll('td.attempt-buttons').forEach(function (td) { if (!folded(td)) level(td.closest('tr')); });
    stretchAll(Array.prototype.slice.call(document.querySelectorAll(LINED)));
    batch(document.querySelectorAll('tr > td > details.row-fold[open]'), foldBody);
    document.querySelectorAll('tr > td > details.row-fold[open]').forEach(alignColumns);
    batch(document.querySelectorAll('ol.attempt-list > li, .result-group-head'), underRowButton);
    if (unsettled && again < 3) { again++; soon(); } else again = 0;
  }
  function soon() {
    if (!queued) { queued = true; requestAnimationFrame(all); }
  }
  all();
  //(again whenever a list changes size: a row opened or folded, fonts or pictures in, badges
  //resized; more dependable than watching clicks, the owner 2026-10-20)
  var watch = window.ResizeObserver ? new ResizeObserver(soon) : null;
  function watchAll() {
    if (!watch) return;
    //(the tables swapped out let go of, so they aren't kept alive: the code critic, 2026-10-25)
    watch.disconnect();
    document.querySelectorAll('table').forEach(function (t) {
      if (t.querySelector('ol.attempt-list, td.attempt-buttons, details.row-fold')) watch.observe(t);
    });
  }
  watchAll();
  //(a list swapped in without a reload, after a sort or a drop: static/js/sorttable.js, folders.js)
  document.addEventListener('qgen-swapped', function () { watchAll(); soon(); });
  //(and once the page's fonts and pictures are in: they change the widths)
  window.addEventListener('load', soon);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(soon);
  window.addEventListener('resize', soon);
  //(a folded row or box opened, or a pop-over shown: measured once it shows)
  document.addEventListener('toggle', soon, true);
  document.addEventListener('click', function () { setTimeout(soon, 0); }, true);
  //(the page's boxes opened or folded as remembered)
  document.addEventListener('qgen-boxes-ready', soon);

  //an open row's heading (the person, the quiz) stays in sight at the top of its scrolling list while
  //its contents scroll under it, until the next row comes (the owner, 2026-10-21); .row-stuck gives it
  //its band, only while it's stuck (in place, the band would cover the row's other cells)
  //(speed, the owner 2026-10-22: only the open rows are measured, and every measurement is taken
  //before anything is written, so the page is laid out once, not once a row: it took half a second
  //on Problems' 259 rows, at load and on every scroll)
  function stick() {
    document.querySelectorAll('.folder-filter-list.folder-scroll').forEach(function (list) {
      var head = list.querySelector('thead'), hh = head ? head.offsetHeight : 0;
      var lt = list.getBoundingClientRect().top + hh;
      var open = Array.prototype.map.call(list.querySelectorAll('tr > td > details.row-fold[open] > summary'), function (sm) {
        return { sm: sm, h: sm.offsetHeight, row: sm.parentElement.closest('tr').getBoundingClientRect(), e: sm.getBoundingClientRect() };
      });
      list.style.setProperty('--thead-h', hh + 'px');
      list.querySelectorAll('summary.row-stuck').forEach(function (sm) { if (!sm.parentElement.open) sm.classList.remove('row-stuck'); });
      open.forEach(function (m) {
        //(how tall its heading is: a table inside the open row pins its own headings just under it,
        //the owner 2026-10-22)
        m.sm.parentElement.style.setProperty('--sum-h', m.h + 'px');
        //(its band from the row's left edge to its right, just inside the row's outline)
        m.sm.style.setProperty('--stuck-l', Math.round(m.row.left + 1 - m.e.left) + 'px');
        m.sm.style.setProperty('--stuck-r', Math.round(m.e.right - m.row.right + 1) + 'px');
        m.sm.classList.toggle('row-stuck', m.row.top < lt - 2 && m.row.bottom > lt + m.h);
      });
    });
  }
  document.addEventListener('scroll', function () { requestAnimationFrame(stick); }, true);
  //(once for a burst of rows opening, Expand all: not once a row, the owner 2026-10-24)
  document.addEventListener('toggle', function () { clearTimeout(stick._t); stick._t = setTimeout(stick, 0); }, true);
  window.addEventListener('load', stick);
})();
