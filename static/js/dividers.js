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

  function stretch(el) {
    if (!el.offsetParent) return;
    //(a table row first, whatever's inside it, e.g. the folded box a quiz's attempts are in)
    var holder = el.closest('tr') || (el.parentElement && el.parentElement.closest(HOLDER));
    if (!holder) return;
    var r = holder.getBoundingClientRect(), e = el.getBoundingClientRect();
    //(a row: just inside its edges; a card or pop-over: to the edges of its padding)
    var cs = getComputedStyle(holder);
    var padL = holder.tagName === 'TR' ? 12 : parseFloat(cs.paddingLeft) + parseFloat(cs.borderLeftWidth);
    var padR = holder.tagName === 'TR' ? 12 : parseFloat(cs.paddingRight) + parseFloat(cs.borderRightWidth);
    el.style.setProperty('--line-l', Math.round(r.left + padL - e.left) + 'px');
    el.style.setProperty('--line-r', Math.round(e.right - r.right + padR) + 'px');
  }

  //a quiz's attempts: each one's button right under the quiz's own button, at the row's right end
  function underRowButton(li) {
    var row = li.closest('tr'), cell = row && row.querySelector('td.actions');
    if (!cell || !li.offsetParent) return;
    //(centered under it: the attempts' buttons are smaller than the quiz's; a row with nothing to
    //view has no button of its own, so the place one would be: the cell's right end, inside it)
    var own = cell.querySelector('.quiz-row-actions > :first-child'), mid;
    if (own) { var o = own.getBoundingClientRect(); mid = (o.left + o.right) / 2; }
    else { var c = cell.getBoundingClientRect(); mid = c.right - parseFloat(getComputedStyle(cell).paddingRight) - 17; }
    li.style.setProperty('--act-r', Math.round(li.getBoundingClientRect().right - mid) + 'px');
  }

  //an open row's contents (after its heading part) on their own shade, end to end across the row
  function foldBody(d) {
    var row = d.closest('tr');
    if (!row || !d.open || !d.offsetParent) return;
    var r = row.getBoundingClientRect(), e = d.getBoundingClientRect();
    var start = d.querySelector('[data-fold-body]'), sum = d.querySelector(':scope > summary');
    var top = start ? start.getBoundingClientRect().top : sum ? sum.getBoundingClientRect().bottom : e.top;
    d.style.setProperty('--body-top', Math.round(top - e.top) + 'px');
    //(just inside the row's own outline)
    d.style.setProperty('--body-l', Math.round(r.left + 1 - e.left) + 'px');
    d.style.setProperty('--body-r', Math.round(e.right - r.right + 1) + 'px');
  }

  var queued = false;
  function all() {
    queued = false;
    document.querySelectorAll('td.attempt-buttons').forEach(function (td) { level(td.closest('tr')); });
    document.querySelectorAll(LINED).forEach(stretch);
    document.querySelectorAll('tr > td > details.row-fold[open]').forEach(foldBody);
    document.querySelectorAll('ol.attempt-list > li').forEach(underRowButton);
  }
  function soon() {
    if (!queued) { queued = true; requestAnimationFrame(all); }
  }
  all();
  //(again whenever a list changes size: a row opened or folded, fonts or pictures in, badges
  //resized; more dependable than watching clicks, the owner 2026-10-20)
  if (window.ResizeObserver) {
    var watch = new ResizeObserver(soon);
    document.querySelectorAll('table').forEach(function (t) {
      if (t.querySelector('ol.attempt-list, td.attempt-buttons, details.row-fold')) watch.observe(t);
    });
  }
  //(and once the page's fonts and pictures are in: they change the widths)
  window.addEventListener('load', soon);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(soon);
  window.addEventListener('resize', soon);
  //(a folded row or box opened, or a pop-over shown: measured once it shows)
  document.addEventListener('toggle', soon, true);
  document.addEventListener('click', function () { setTimeout(soon, 0); }, true);
  //(the page's boxes opened or folded as remembered)
  document.addEventListener('qgen-boxes-ready', soon);
})();
