/* Scan workbook pages: the review page (app/qgen/templates/scan_review.html).
 * - while the AI reads, check on it and show each page as it's read (drawn again only when
 *   nothing has been changed yet: the pages read so far can be edited meanwhile, CA9)
 * - crop boxes over each page picture: drag to move, drag a corner to resize; they
 *   write "left,top,right,bottom" (fractions of the page) into their hidden input
 * - "+ Add a picture", remove, the question kind and "Use the page's numbers" switches
 * - "Check and show examples": the item as it stands, checked by the server (nothing saved)
 * - each problem's place on the page: a blue box to drag; Save is grayed until every checked
 *   problem has one */
(function () {
  function csrf() { return document.querySelector('meta[name=csrf-token]').content; }

  /* ---------- reading progress ---------- */
  var progress = document.getElementById('scan-progress');
  if (progress) {
    var words = { waiting: 'not read yet', reading: 'reading…', done: 'done ✓', error: 'didn’t make it', saved: 'generated' };  // (the thumbnails' tooltips)
    var steps = {};
    try { steps = JSON.parse(progress.dataset.steps || '{}'); } catch (x) {}
    //Pause: a plain button, sent by its own click
    document.addEventListener('click', function (e) {
      var pause = e.target.closest && e.target.closest('[data-scan-pause]');
      if (!pause) return;
      var f = document.getElementById('scan-form'), go = document.createElement('button');
      go.type = 'submit'; go.hidden = true; go.formNoValidate = true;
      go.setAttribute('formaction', pause.dataset.scanPause);
      f.appendChild(go); f.requestSubmit(go);
    });
    //(how each page stood when the page was drawn: a change is drawn again, unless something's been edited)
    var was = {};
    Array.prototype.forEach.call(document.querySelectorAll('.scan-strip li[data-n]'), function (li) {
      was[li.dataset.n] = (li.className.match(/scan-strip-(waiting|reading|done|error)/) || [])[1];
    });
    function edited() { return window.qgenIsChanged ? window.qgenIsChanged() : false; }
    //the timers (the owner, 2026-10-18): each page being read, its own time so far, and the whole reading so far in the
    //workbook's card, counted from the server's times (skew: how far this computer's clock is off), ticking every second
    var skew = 0, since = {}, allSince = null;
    function when(iso) { return iso ? new Date(iso).getTime() : null; }
    function mmss(ms) { var s = Math.max(0, Math.round(ms / 1000)); return Math.floor(s / 60) + ':' + ('0' + s % 60).slice(-2); }
    function showTime() {
      var now = Date.now() + skew;
      document.querySelectorAll('.scan-timer[data-timer-page]').forEach(function (t) {
        var at = since[t.dataset.timerPage];
        t.textContent = at ? mmss(now - at) : '';
      });
      var all = document.querySelector('.scan-timer[data-timer-all]');
      if (all && allSince !== null) all.textContent = 'in all ' + mmss(now - allSince);
    }
    setInterval(showTime, 1000);
    var poll = function () {
      fetch(progress.dataset.status, { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (s) {
        if (s.now) skew = when(s.now) - Date.now();
        allSince = when(s.since);
        since = {};
        s.pages.forEach(function (p) { if (p.state === 'reading') since[p.n] = when(p.since); });
        showTime();
        var done = 0;
        s.pages.forEach(function (p) {
          //(the thumbnail's outline and tooltip; the page's bar and its step, CI1/CI2)
          var li = document.querySelector('.scan-strip li[data-n="' + p.n + '"]');
          //(a read page with things to fix keeps its "!" from the server: the owner, 2026-10-25)
          if (li && !(p.state === 'done' && 'fix' in li.dataset)) {
            li.className = 'scan-strip-page scan-strip-' + p.state;
            var a = li.querySelector('a[data-state-tip]');
            if (a) a.title = 'Page ' + p.n + ': ' + (words[p.state] || p.state) + '. ' + a.dataset.stateTip;
            var badge = li.querySelector('[data-badge]');
            var drawn = document.querySelector('#scan-badges') && document.querySelector('#scan-badges').content.querySelector('[data-for="' + p.state + '"]');
            if (badge && drawn) badge.innerHTML = drawn.innerHTML;
          }
          var bar = document.querySelector('[data-bar-page="' + p.n + '"]'), step = document.querySelector('[data-step-page="' + p.n + '"]');
          var pr = p.progress || {};
          if (bar) {
            var known = pr.pct !== null && pr.pct !== undefined;
            bar.classList.toggle('is-unknown', !known);
            bar.style.width = (known ? pr.pct : 100) + '%';
          }
          if (step) step.textContent = pr.step ? (steps[pr.step] || '') + (pr.pct !== null && pr.pct !== undefined ? ' · ' + pr.pct + '%' : '') : '';
          if (p.state === 'done' || p.state === 'error') done += 1;
        });
        var now = s.pages.filter(function (p) { return p.state === 'reading'; })[0];
        var moved = s.pages.some(function (p) { return was[p.n] !== p.state; }) || !s.reading;
        //(a page started or finished: drawn again, so each page's box shows how it stands; not over
        //edits not saved yet, the owner 2026-10-24, CA9: then a finished page's box just goes)
        if (moved && !edited()) {
          //(drawn again in place, nothing blanks out: the pages' boxes, the thumbnails and the workbook's buttons;
          //the owner, 2026-10-25. Anything that doesn't line up: a reload, as before)
          if (!window.qgenScanSwap) { location.replace(location.href); return; }
          window.qgenScanSwap().then(function (ok) {
            if (!ok) { location.replace(location.href); return; }
            was = {};
            Array.prototype.forEach.call(document.querySelectorAll('.scan-strip li[data-n]'), function (li) {
              was[li.dataset.n] = (li.className.match(/scan-strip-(waiting|reading|done|error)/) || [])[1];
            });
            if (s.reading) { clearTimeout(asking); asking = setTimeout(poll, 3000); }
          });
          return;
        }
        //(with edits not saved yet the page isn't drawn again: once every page is read, the buttons that were waiting
        //for it work again, in place; the code critic, 2026-10-25)
        if (!s.reading) {
          document.querySelectorAll('[data-after-reading]').forEach(function (b) {
            b.disabled = false;
            b.title = b.dataset.afterReading;
            b.removeAttribute('data-after-reading');
          });
        }
        s.pages.forEach(function (p) {
          var bar = document.querySelector('#scan-page-' + p.n + ' .scan-progress-bar');
          if (bar && p.state === 'done') bar.hidden = true;
        });
        var line = document.getElementById('scan-progress-line');
        if (line) line.textContent = now
          ? 'Reading page ' + now.n + ' of ' + s.pages.length + '…'
          : done + ' of ' + s.pages.length + ' pages read';
        //(every 3 seconds while pages are read, live updates or not: the percent only moves by asking)
        if (s.reading) { clearTimeout(asking); asking = setTimeout(poll, 3000); }
      }).catch(function () { later(8000); });
    };
    //(with instant updates, static/js/push.js, it asks when the server says a page changed;
    //asking every few seconds is then only a backup: the owner, 2026-10-20)
    var asking = null;
    function later(ms) { clearTimeout(asking); asking = setTimeout(poll, window.qgenLive ? 60000 : ms); }
    document.addEventListener('qgen-changed', function () { clearTimeout(asking); asking = setTimeout(poll, 300); });
    later(2000);
  }

  var form = document.getElementById('scan-form');
  if (!form) return;

  /* ---------- crop boxes ---------- */
  function readBox(input) {
    var p = (input.value || '').split(',').map(parseFloat);
    if (p.length !== 4 || p.some(isNaN)) p = [0, 0, 1, 1];
    return { l: p[0], t: p[1], r: p[2], b: p[3] };
  }
  function writeBox(input, b) {
    input.value = [b.l, b.t, b.r, b.b].map(function (v) { return Math.round(v * 10000) / 10000; }).join(',');
    if (window.qgenChanged) window.qgenChanged();
  }
  function place(crop) {
    var input = document.getElementById(crop.dataset.for);
    if (!input) { crop.hidden = true; return; }
    var b = readBox(input);
    crop.style.left = (b.l * 100) + '%';
    crop.style.top = (b.t * 100) + '%';
    crop.style.width = ((b.r - b.l) * 100) + '%';
    crop.style.height = ((b.b - b.t) * 100) + '%';
  }
  function addHandles(crop) {
    ['nw', 'ne', 'sw', 'se'].forEach(function (c) {
      var h = document.createElement('span');
      h.className = 'crop-handle crop-' + c;
      h.dataset.corner = c;
      h.setAttribute('aria-hidden', 'true');
      crop.appendChild(h);
    });
  }
  function setUp(crop) {
    addHandles(crop);
    place(crop);
    crop.addEventListener('pointerdown', function (e) {
      if (e.button !== 0) return;
      e.preventDefault();
      var canvas = crop.parentElement, rect = canvas.getBoundingClientRect();
      var input = document.getElementById(crop.dataset.for);
      var start = readBox(input), x0 = e.clientX, y0 = e.clientY;
      var corner = e.target.dataset.corner || null;
      crop.setPointerCapture(e.pointerId);
      crop.classList.add('is-dragging');
      var MIN = 0.02;
      function move(ev) {
        var dx = (ev.clientX - x0) / rect.width, dy = (ev.clientY - y0) / rect.height;
        var b = { l: start.l, t: start.t, r: start.r, b: start.b };
        if (!corner) {
          var w = b.r - b.l, h = b.b - b.t;
          b.l = Math.min(Math.max(0, start.l + dx), 1 - w); b.r = b.l + w;
          b.t = Math.min(Math.max(0, start.t + dy), 1 - h); b.b = b.t + h;
        } else {
          if (corner.indexOf('w') !== -1) b.l = Math.min(Math.max(0, start.l + dx), b.r - MIN);
          if (corner.indexOf('e') !== -1) b.r = Math.max(Math.min(1, start.r + dx), b.l + MIN);
          if (corner.indexOf('n') !== -1) b.t = Math.min(Math.max(0, start.t + dy), b.b - MIN);
          if (corner.indexOf('s') !== -1) b.b = Math.max(Math.min(1, start.b + dy), b.t + MIN);
        }
        writeBox(input, b);
        place(crop);
      }
      function up() {
        crop.removeEventListener('pointermove', move);
        crop.removeEventListener('pointerup', up);
        crop.removeEventListener('pointercancel', up);
        crop.classList.remove('is-dragging');
      }
      crop.addEventListener('pointermove', move);
      crop.addEventListener('pointerup', up);
      crop.addEventListener('pointercancel', up);
    });
  }
  form.querySelectorAll('.crop').forEach(setUp);

  /* ---------- each problem's place on its page (the owner, 2026-10-20) ---------- */
  //a blue box dragged is placed; a page's Generate quiz stays grayed while a checked problem of its quiz has no place
  function itemOf(crop) {
    var m = /^p(\d+)i(\d+)-place$/.exec(crop.dataset.for);
    return m && form.querySelector('.scan-item[data-page="' + m[1] + '"][data-item="' + m[2] + '"]');
  }
  //what's to fix on each page (the owner, 2026-10-25, CL1): a problem kept in whose check says what's wrong gets its !,
  //each page its "N to fix", from the checks shown now (they change as problems are checked again)
  function refreshFix() {
    var fix = {};
    form.querySelectorAll('.scan-item').forEach(function (item) {
      var on = item.querySelector('.scan-include'), errs = item.querySelectorAll('.scan-check .error');
      var bad = !!(on && on.checked && errs.length), mark = item.querySelector('[data-item-bad]');
      if (mark) {
        mark.hidden = !bad;
        mark.title = Array.prototype.map.call(errs, function (e) { return e.textContent.trim(); }).join(' ');
      }
      if (bad) fix[item.dataset.page] = (fix[item.dataset.page] || 0) + 1;
      //(only a problem with something to fix opens; one open stays open until it's closed: the owner, 2026-10-25)
      var fold = item.querySelector('[data-fold-item]');
      if (fold && !item.classList.contains('is-open') && !item.classList.contains('has-error')) {
        fold.disabled = !bad;
        fold.title = bad ? fold.dataset.q : fold.dataset.off;
      }
    });
    form.querySelectorAll('details.scan-page[data-page]').forEach(function (pg) {
      var b = pg.querySelector('[data-fix-count]'), k = fix[pg.dataset.page] || 0;
      if (b) { b.hidden = !k; b.textContent = k + ' to fix'; }
    });
    return fix;
  }
  function refreshSave() {
    var fix = refreshFix();
    var waiting = [], items = [], pages = [];
    form.querySelectorAll('.crop-place').forEach(function (crop) {
      var item = itemOf(crop), placed = item && item.querySelector('[data-placed]');
      if (!crop.hidden && placed && placed.value !== '1') { waiting.push(crop.dataset.label); items.push(item); pages.push(item.dataset.page); }
    });
    //(each page's own Generate quiz: grayed while a problem of its quiz has no place; a joined page's stays grayed)
    form.querySelectorAll('[data-generate]').forEach(function (btn) {
      if (btn.hasAttribute('data-joined')) return;
      var group = btn.dataset.group.split(' '), gaps = [], bad = 0;
      pages.forEach(function (pg, k) { if (group.indexOf(pg) !== -1) gaps.push(waiting[k]); });
      group.forEach(function (pg) { bad += fix[pg] || 0; });
      btn.disabled = gaps.length > 0 || bad > 0;
      btn.title = bad ? 'Fix the problems marked ! first'
        : gaps.length ? 'Every problem needs its place on the page first (' + gaps.join(', ') + ')' : btn.dataset.tip;
    });
    //(each page's green check mark: shown once nothing on it waits for its place, the owner 2026-10-21)
    form.querySelectorAll('.scan-page').forEach(function (pg) {
      var ok = pg.querySelector('.scan-page-ok');
      if (!ok) return;
      var left = Array.prototype.some.call(pg.querySelectorAll('.crop-place'), function (crop) {
        var item = itemOf(crop), placed = item && item.querySelector('[data-placed]');
        return !crop.hidden && placed && placed.value !== '1';
      });
      ok.hidden = left || ok.dataset.errors === '1';
    });
  }
  function setUpPlace(crop) {
    crop.addEventListener('pointerdown', function () {
      var item = itemOf(crop);
      if (!item) return;
      item.querySelector('[data-placed]').value = '1';
      if (window.qgenChanged) window.qgenChanged();
      var line = item.querySelector('.scan-no-place');
      if (line) line.hidden = true;
      crop.classList.remove('is-missing', 'is-guessed');
      refreshSave();
    });
  }
  form.querySelectorAll('.crop-place').forEach(setUpPlace);
  /* the workbook's thumbnails (the owner, 2026-10-25): the link between two joins them into one quiz or splits them,
     and a thumbnail dragged left or right changes the order; either way the whole form goes with it, so edits are kept */
  var strip = document.querySelector('.scan-strip[data-arrange]');
  function arrange() {
    var go = document.createElement('button');
    go.type = 'submit'; go.hidden = true; go.formNoValidate = true;
    go.setAttribute('formaction', strip.dataset.arrange);
    form.appendChild(go);
    if (window.qgenLeaving) window.qgenLeaving();
    form.requestSubmit(go);
  }
  if (strip) {
    strip.addEventListener('click', function (e) {
      var b = e.target.closest && e.target.closest('button[data-join]');
      if (!b || b.disabled) return;
      var input = form.querySelector('input[name="p' + b.dataset.join + '-join_prev"]');
      if (!input) return;
      input.value = input.value ? '' : '1';
      arrange();
    });
    var dragged = null, before = null;
    strip.addEventListener('dragstart', function (e) {
      var li = e.target.closest && e.target.closest('li[draggable="true"]');
      if (!li) return;
      dragged = li;
      before = Array.prototype.slice.call(strip.children);   // (put back as it was when dropped where it started)
      li.classList.add('is-dragging');
      e.dataTransfer.effectAllowed = 'move';
      try { e.dataTransfer.setData('text/plain', li.dataset.n); } catch (x) {}
    });
    strip.addEventListener('dragover', function (e) {
      if (!dragged) return;
      var li = e.target.closest && e.target.closest('li.scan-strip-page');
      if (!li || li === dragged) return;
      e.preventDefault();
      var r = li.getBoundingClientRect();
      li.parentNode.insertBefore(dragged, e.clientX < r.left + r.width / 2 ? li : li.nextSibling);
    });
    strip.addEventListener('drop', function (e) { if (dragged) e.preventDefault(); });
    strip.addEventListener('dragend', function () {
      if (!dragged) return;
      dragged.classList.remove('is-dragging');
      dragged = null;
      var order = Array.prototype.map.call(strip.querySelectorAll('li.scan-strip-page'), function (li) { return li.dataset.n; });
      var was = order.slice().sort(function (a, b) { return a - b; });
      if (order.join(',') === was.join(',')) {
        //(nothing moved: the thumbnails and the links between them back in place, no reload; the owner, 2026-10-25)
        if (before) before.forEach(function (el) { strip.appendChild(el); });
        return;
      }
      document.getElementById('scan-order').value = order.join(',');
      arrange();
    });
  }
  refreshSave();
  //a problem's short row folds open to its fields, and closed again (the owner, 2026-10-25, CB3)
  function openItem(item, open) {
    item.classList.toggle('is-open', open);
    var b = item.querySelector('[data-fold-item]');
    if (b) b.setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  form.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-fold-item]');
    if (!b) return;
    var item = b.closest('.scan-item');
    openItem(item, !item.classList.contains('is-open'));
    if (!item.classList.contains('is-open')) refreshFix();
  });
  //a number in the notice: its page opened (pages start folded), then scrolled to
  form.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[data-jump]');
    if (!a) return;
    var item = document.getElementById(a.getAttribute('href').slice(1));
    if (!item) return;
    e.preventDefault();
    var page = item.closest('details');
    if (page) page.open = true;
    if (item.classList.contains('scan-item')) openItem(item, true);
    item.scrollIntoView({ block: 'center' });
  });

  //a picture's "save": grayed and checked, with why, while its menu sends it to a problem or a quiz, which saves it
  //in Pictures anyway (the owner, 2026-10-25, To do 48); back to as it was when the menu says Nothing
  function keepBox(row) {
    var use = row.querySelector('select.scan-use'), label = row.querySelector('.scan-pic-keep'), box = label && label.querySelector('input');
    if (!use || !box) return;
    if (!('tip' in label.dataset)) { label.dataset.tip = label.title; box.dataset.was = box.checked ? '1' : ''; }
    var v = use.value, m;
    if (!v) {
      if (box.disabled) box.checked = !!box.dataset.was;
      box.disabled = false;
      label.title = label.dataset.tip;
      return;
    }
    if (!box.disabled) box.dataset.was = box.checked ? '1' : '';
    box.checked = true;
    box.disabled = true;
    if ((m = /^item:(\d+):(\d+)$/.exec(v))) {
      label.title = 'Saved in Pictures with problem #' + (+m[2] + 1) + (m[1] !== row.dataset.page ? ' on page ' + m[1] : '') + ', which uses it';
    } else if ((m = /^quiz:(\d+)$/.exec(v))) {
      label.title = 'Saved in Pictures with the quiz from page ' + m[1] + ', which uses it';
    }
  }
  form.querySelectorAll('.scan-pic').forEach(keepBox);

  //"remove" on a picture hides its box (and puts it back when unchecked)
  form.addEventListener('change', function (e) {
    var t = e.target;
    if (t.classList.contains('scan-pic-remove')) {
      var row = t.closest('.scan-pic');
      var crop = form.querySelector('.crop[data-for="' + row.dataset.box + '"]');
      if (crop) crop.hidden = t.checked;
      row.classList.toggle('is-off', t.checked);
    }
    if (t.classList.contains('scan-include')) {
      var it = t.closest('.scan-item');
      it.classList.toggle('is-off', !t.checked);
      //(a problem left out needs no place)
      var place = form.querySelector('.crop-place[data-for="p' + it.dataset.page + 'i' + it.dataset.item + '-place"]');
      if (place) place.hidden = !t.checked;
      refreshSave();
    }
    if (t.classList.contains('scan-use') && t.closest('.scan-pic')) keepBox(t.closest('.scan-pic'));
    if (t.classList.contains('scan-use-page')) showFixed(t.closest('.scan-item'));
    if (t.classList.contains('scan-qtype')) showChoices(t.closest('.scan-item'));
    if (t.classList.contains('scan-kind')) showKind(t.closest('.scan-value'));
  });

  //a crop box the AI missed
  var added = 0, template = document.getElementById('scan-new-pic');
  function setUpAddPic(btn) {
    btn.addEventListener('click', function () {
      added += 1;
      var n = btn.dataset.page, pre = 'p' + n, id = 'new' + added;
      var html = template.innerHTML.replace(/__P__/g, pre).replace(/__ID__/g, id);
      var list = form.querySelector('.scan-pics[data-page="' + n + '"]');
      var wrap = document.createElement('div');
      wrap.innerHTML = html.trim();
      var row = wrap.firstElementChild;
      list.appendChild(row);
      var crop = document.createElement('div');
      crop.className = 'crop crop-new';
      crop.dataset.for = pre + '-' + id + '-box';
      crop.title = 'New picture: drag to move, drag the corners to resize';
      crop.innerHTML = '<span class="crop-label">' + (window.qgenIcon ? window.qgenIcon('picture') + ' ' : '') + 'new picture</span>';
      form.querySelector('.scan-canvas[data-page="' + n + '"]').appendChild(crop);
      setUp(crop);
      var label = row.querySelector('input[type=text]');
      if (label) label.focus();
    });
  }
  form.querySelectorAll('.scan-add-pic').forEach(setUpAddPic);

  /* ---------- an item's fields ---------- */
  var CHOICE = ['choice_one', 'choice_many'];
  function showFixed(item) {
    var fixed = item.querySelector('.scan-use-page');
    if (!fixed) return;
    item.querySelector('.scan-random').hidden = fixed.checked;
    item.querySelector('.scan-fixed').hidden = !fixed.checked;
  }
  function showChoices(item) {
    var q = item.querySelector('.scan-qtype');
    if (!q) return;
    item.querySelectorAll('.t-choice').forEach(function (el) { el.hidden = CHOICE.indexOf(q.value) === -1; });
  }
  function showKind(row) {
    var kind = row.querySelector('.scan-kind').value;
    row.dataset.kind = kind;
    row.querySelectorAll('[class*="k-"]').forEach(function (el) {
      var kinds = Array.prototype.filter.call(el.classList, function (c) { return c.indexOf('k-') === 0; });
      if (kinds.length) el.hidden = kinds.indexOf('k-' + kind) === -1;
    });
  }
  form.querySelectorAll('.scan-item').forEach(function (item) { showFixed(item); showChoices(item); });
  form.querySelectorAll('.scan-value').forEach(showKind);

  //a page's box swapped in (below): everything set up on it, as on the page's opening
  function setUpRoot(root) {
    root.querySelectorAll('.crop').forEach(setUp);
    root.querySelectorAll('.crop-place').forEach(setUpPlace);
    root.querySelectorAll('.scan-pic').forEach(keepBox);
    root.querySelectorAll('.scan-add-pic').forEach(setUpAddPic);
    root.querySelectorAll('.scan-item').forEach(function (item) { showFixed(item); showChoices(item); });
    root.querySelectorAll('.scan-value').forEach(showKind);
  }
  //while pages are read: the workbook as it is now, swapped in without a reload (the owner, 2026-10-25: pages should
  //update cleanly). Only with nothing edited (the caller checks); false when it doesn't line up, and the caller reloads
  window.qgenScanSwap = function () {
    if (!window.fetch || !window.DOMParser) return Promise.resolve(false);
    return fetch(location.href, { credentials: 'same-origin' }).then(function (r) {
      if (!r.ok || r.redirected) throw new Error('not the page');
      return r.text();
    }).then(function (html) {
      var doc = new DOMParser().parseFromString(html, 'text/html');
      var oldPages = form.querySelectorAll('.scan-page[id^="scan-page-"]'), newPages = doc.querySelectorAll('#scan-form .scan-page[id^="scan-page-"]');
      var newStrip = doc.querySelector('.scan-strip'), oldEnd = form.querySelector('.scan-batch-head .box-end'), newEnd = doc.querySelector('.scan-batch-head .box-end');
      if (!oldPages.length || oldPages.length !== newPages.length || !newStrip || !strip || !oldEnd || !newEnd) return false;
      for (var i = 0; i < oldPages.length; i++) if (oldPages[i].id !== newPages[i].id) return false;
      Array.prototype.forEach.call(oldPages, function (pg, k) {
        var fresh = document.importNode(newPages[k], true);
        //(a box that was open stays open)
        if (pg.tagName === 'DETAILS' && fresh.tagName === 'DETAILS' && pg.open) fresh.open = true;
        pg.replaceWith(fresh);
        setUpRoot(fresh);
      });
      strip.innerHTML = newStrip.innerHTML;
      oldEnd.replaceWith(document.importNode(newEnd, true));
      refreshSave();
      form.dispatchEvent(new Event('helper-refresh'));
      return true;
    }).catch(function () { return false; });
  };

  //the item being worked on is lit up on its page
  form.addEventListener('focusin', function (e) {
    var item = e.target.closest('.scan-item');
    form.querySelectorAll('.crop.is-current').forEach(function (c) { c.classList.remove('is-current'); });
    if (!item) return;
    var crop = form.querySelector('.crop[data-for="p' + item.dataset.page + 'i' + item.dataset.item + '-box"]');
    if (crop) crop.classList.add('is-current');
  });

  /* ---------- check one item ---------- */
  form.addEventListener('click', function (e) {
    var btn = e.target.closest('.scan-try');
    if (!btn) return;
    var item = btn.closest('.scan-item'), out = item.querySelector('.scan-check');
    var data = new FormData(form);
    data.set('page', item.dataset.page);
    data.set('item', item.dataset.item);
    btn.disabled = true;
    out.textContent = 'Checking…';
    fetch(form.dataset.check, { method: 'POST', body: data, credentials: 'same-origin', headers: { 'X-CSRFToken': csrf() } })
      .then(function (r) { return r.json(); })
      .then(function (res) { if (res.ok) out.innerHTML = res.html; else out.textContent = res.error; refreshSave(); })
      .catch(function () { out.textContent = 'Couldn’t check it just now. Please try again.'; })
      .then(function () { btn.disabled = false; });
  });

  /* Enter in a one-line box doesn't send the form: it would press the first button in it, a page's
     "Find the boxes again" (the code critic, 2026-10-22) */
  form.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT' && !/^(checkbox|radio|button|submit)$/.test(e.target.type)) e.preventDefault();
  });

  //(a failed page's Read this page / Discard page (Keep as it is removed: the owner, 2026-10-25, CX3): asked first, then the whole form sent to that address, so the changes on
  //the other pages are kept; a plain button, never the form's own send button)
  form.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('button[data-page-go]');
    if (!b) return;
    e.preventDefault(); e.stopImmediatePropagation();
    //(one with nothing to ask goes at once: Use what was read costs nothing, CX6)
    (b.dataset.ask ? window.qgenAsk(b.dataset.ask, b.dataset.ok, false) : Promise.resolve(true)).then(function (yes) {
      if (!yes) return;
      var go = document.createElement('button');
      go.type = 'submit'; go.hidden = true; go.formNoValidate = true;
      go.setAttribute('formaction', b.dataset.pageGo);
      form.appendChild(go);
      form.requestSubmit(go);
    });
  }, true);

  /* ---------- Read this page again: asks first (the owner, 2026-10-20) ---------- */
  //(sent with the whole form, so the changes on the other pages are kept)
  form.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('button[data-ask]');
    if (!btn) return;
    e.preventDefault();
    //(the OK button says that button's own action: the code critic, 2026-10-22)
    window.qgenAsk(btn.dataset.ask, btn.dataset.ok || btn.textContent.trim(), false).then(function (yes) {
      if (yes) form.requestSubmit(btn);
    });
  });
})();
