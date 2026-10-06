/* Folders beside a list (My quizzes, Users): the folder list down the side, the folder boxes
 * inside the folder being looked at, and moving things into folders.
 *
 * The page's <div class="folders-layout"> says:
 *   data-move-url   where a drop is sent (POST: <kind>=<id>, to=<folder id or "top">, from=<its folder>, view=<shown>)
 *   data-view       what's shown: "main", "all" or a folder's id
 *   data-path       the shown folder and its parents' ids (JSON), always unfolded in the list
 *   data-fold-key / data-open-key   where this browser remembers folded list folders / open boxes
 *
 * Draggable things have data-drag="<kind>" data-id data-name, and data-home (the folder
 * they're in, "top" for the main list); the box that moves has data-box="<kind>:<id>".
 * Places to drop have data-drop="<folder id>" or "top". */
(function () {
  var layout = document.querySelector('.folders-layout');
  if (!layout) return;
  var view = layout.dataset.view, path = [];
  try { path = JSON.parse(layout.dataset.path || '[]'); } catch (e) {}
  function load(key) {
    var out = {};
    try { (JSON.parse(localStorage.getItem(key) || '[]') || []).forEach(function (id) { out[id] = true; }); } catch (e) {}
    return out;
  }
  function save(key, set) {
    try { localStorage.setItem(key, JSON.stringify(Object.keys(set))); } catch (e) {}
  }

  //folders in the list whose inner folders are hidden (the one being looked at always shows)
  var FOLD = layout.dataset.foldKey, folded = load(FOLD);
  path.forEach(function (id) { delete folded[id]; });
  document.querySelectorAll('.side-item').forEach(function (li) {
    var btn = li.querySelector(':scope > .side-row > .side-fold');
    if (!btn) return;
    function show(open) {
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      li.classList.toggle('side-folded', !open);
      if (open) delete folded[li.dataset.folder]; else folded[li.dataset.folder] = true;
    }
    show(!folded[li.dataset.folder]);
    btn.addEventListener('click', function () { show(btn.getAttribute('aria-expanded') !== 'true'); save(FOLD, folded); });
  });
  save(FOLD, folded);

  //on a phone the folder list starts folded (its heading says which folder is shown)
  var side = document.querySelector('details.folder-side');
  if (side && window.matchMedia('(max-width: 760px)').matches) side.open = false;

  //folder boxes start folded; the ones left open are remembered
  var OPEN = layout.dataset.openKey, opened = load(OPEN), subs = document.querySelectorAll('details.sub-box');
  subs.forEach(function (d) { if (opened[d.dataset.sub]) d.open = true; });
  subs.forEach(function (d) {
    d.addEventListener('toggle', function () {
      if (searching) return;  // opened by a search: not remembered
      if (d.open) opened[d.dataset.sub] = true; else delete opened[d.dataset.sub];
      save(OPEN, opened);
    });
  });
  //Expand all / Collapse all: only the boxes directly in that level (folders and quizzes alike)
  document.querySelectorAll('[data-level]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var level = btn.closest('.level'), want = btn.dataset.level === 'open';
      level.querySelectorAll('details.sub-box, details.quiz-card, details.month-box, details.item-box').forEach(function (d) {
        if (d.parentElement.closest('.level') === level) d.open = want;
      });
    });
  });

  //"Move to" / "Add to" lists act as soon as a folder is picked
  document.querySelectorAll('.move-select').forEach(function (sel) {
    sel.addEventListener('change', function () {
      if (!sel.value) return;
      sel.form.requestSubmit ? sel.form.requestSubmit() : sel.form.submit();
    });
  });
  //a new folder's name box gets the cursor when its form opens
  document.querySelectorAll('details.new-folder').forEach(function (d) {
    d.addEventListener('toggle', function () { if (d.open) d.querySelector('input[name=name]').focus(); });
  });

  //after a drag: "Moved "train" to "abc"." at the top, and what moved lit up
  (function () {
    var done = null;
    try { done = JSON.parse(sessionStorage.getItem('qgen-moved') || 'null'); sessionStorage.removeItem('qgen-moved'); } catch (e) {}
    if (!done || !done.text) return;
    var list = document.createElement('ul'), item = document.createElement('li');
    list.className = 'alerts';
    list.setAttribute('role', 'status');
    item.className = 'alert alert-success';
    item.textContent = done.text;
    list.appendChild(item);
    var main = document.querySelector('main');
    main.insertBefore(list, main.firstChild);
    var box = document.querySelector('[data-box="' + done.box + '"]');
    if (box) {
      box.classList.add('just-moved');
      setTimeout(function () { box.classList.remove('just-moved'); }, 2500);
    }
  })();

  //after a "Move to" list, "+ Add to folder…" or a bar's button (the page came back with
  //?moved=quiz:12): the same glow as after a drag; the address is tidied
  (function () {
    var params = new URLSearchParams(location.search), moved = params.get('moved');
    if (!moved) return;
    params.delete('moved');
    try { history.replaceState(null, '', location.pathname + (params.toString() ? '?' + params : '') + location.hash); } catch (e) {}
    var box = document.querySelector('[data-box="' + moved.replace(/"/g, '') + '"]');
    if (!box) return;
    var shut = box.closest('details.sub-box');
    if (shut) shut.open = true;
    box.classList.add('just-moved');
    box.scrollIntoView({ block: 'center' });
    setTimeout(function () { box.classList.remove('just-moved'); }, 2500);
  })();

  //checked rows (the bar above the list puts them in a folder): something listed twice
  //(in a folder and a folder inside it) is checked in both; the bar says how many
  var ticks = Array.prototype.slice.call(document.querySelectorAll('.folder-main input[name="items"]'));
  var fileForm = document.getElementById('file-form'), fileCount = document.querySelector('.file-count');
  function counted() {
    var ids = {};
    ticks.forEach(function (t) { if (t.checked) ids[t.value] = 1; });
    return Object.keys(ids).length;
  }
  ticks.forEach(function (t) {
    t.addEventListener('change', function () {
      ticks.forEach(function (o) { if (o.value === t.value) o.checked = t.checked; });
      if (fileCount) { fileCount.textContent = counted() + ' checked'; fileCount.classList.remove('error'); }
    });
  });
  if (fileForm) fileForm.addEventListener('submit', function (e) {
    if (!counted()) {
      e.preventDefault();
      if (fileCount) { fileCount.textContent = 'Check at least one first'; fileCount.classList.add('error'); }
    }
  });

  //sections that fold (My quizzes' "Done"): open or not is remembered in this browser
  var REMEMBER = 'qgen-open-sections', remembered = load(REMEMBER);
  document.querySelectorAll('details[data-remember]').forEach(function (d) {
    if (remembered[d.dataset.remember]) d.open = true;
    d.addEventListener('toggle', function () {
      if (searching) return;
      if (d.open) remembered[d.dataset.remember] = true; else delete remembered[d.dataset.remember];
      save(REMEMBER, remembered);
    });
  });

  //"Find a quiz" on My quizzes: hides the quiz boxes whose title doesn't match (then the
  //same as a search below)
  var findCards = document.querySelector('input.filter-cards');
  if (findCards) findCards.addEventListener('input', function () {
    var q = findCards.value.trim().toLowerCase();
    document.querySelectorAll('.folder-main details.quiz-card').forEach(function (c) {
      var title = (c.querySelector('h2') || c).textContent.toLowerCase();
      c.hidden = !!q && title.indexOf(q) === -1;
    });
    findCards.dispatchEvent(new CustomEvent('qgen-filtered', { bubbles: true }));
  });

  //the results pages: a box per student (or quiz), closed to begin with; the open ones are
  //remembered (data-item-key). "Find…" matches a box's name or a row; "Show" keeps only the
  //rows waiting for grading, or not handed in yet (tr[data-state])
  var searching = null;
  var ITEMS = layout.dataset.itemKey, itemOpen = ITEMS ? load(ITEMS) : {};
  var itemBoxes = Array.prototype.slice.call(document.querySelectorAll('.folder-main details.item-box'));
  if (ITEMS) itemBoxes.forEach(function (d) {
    d.open = !!itemOpen[d.dataset.box];
    d.addEventListener('toggle', function () {
      if (searching) return;
      if (d.open) itemOpen[d.dataset.box] = true; else delete itemOpen[d.dataset.box];
      save(ITEMS, itemOpen);
    });
  });
  var findItems = document.querySelector('input.filter-items'), stateFilter = document.querySelector('select.state-filter');
  function filterItems() {
    var q = findItems ? findItems.value.trim().toLowerCase() : '', st = stateFilter ? stateFilter.value : 'all';
    itemBoxes.forEach(function (d) {
      var named = !q || (d.dataset.name || '').indexOf(q) !== -1, rows = d.querySelectorAll('tr[data-state]'), shown = 0;
      rows.forEach(function (r) {
        var ok = (st === 'all' || r.dataset.state === st) && (named || r.textContent.toLowerCase().indexOf(q) !== -1);
        r.hidden = !ok;
        if (ok) shown++;
      });
      d.hidden = rows.length ? !shown : !(named && st === 'all');
      if ((q || st !== 'all') && !d.hidden) d.open = true;
    });
    document.dispatchEvent(new CustomEvent('qgen-filtered', { detail: { active: !!q || st !== 'all' } }));
    var none = document.querySelector('.filter-none');
    if (none) none.hidden = itemBoxes.some(function (d) { return !d.hidden; });
  }
  if (findItems) findItems.addEventListener('input', filterItems);
  if (stateFilter) stateFilter.addEventListener('change', filterItems);

  //searching (filter.js hides the rows that don't match): folder boxes with a match open,
  //the others hide; clearing the search puts them back as they were
  if (typeof searching === 'undefined') searching = null;
  //what a search opens and hides: folder boxes, months, Done
  function boxes() { return Array.prototype.slice.call(document.querySelectorAll('.folder-main details.sub-box, .folder-main details.month-box')); }
  document.addEventListener('qgen-filtered', function (e) {
    var q = e.detail && 'active' in e.detail ? e.detail.active : (e.target.value || '').trim();
    if (q) {
      if (!searching) searching = boxes().map(function (d) { return d.open; });
      boxes().forEach(function (d) { d.hidden = false; });
      boxes().reverse().forEach(function (d) {
        var hit = Array.prototype.some.call(d.querySelectorAll('tbody tr, details.quiz-card, details.item-box'), function (r) {
          return !r.hidden && !r.closest('[hidden]');
        });
        d.hidden = !hit;
        if (hit) d.open = true;
      });
    } else if (searching) {
      boxes().forEach(function (d, i) { d.hidden = false; d.open = searching[i]; });
      itemBoxes.forEach(function (d) { d.open = !!itemOpen[d.dataset.box]; });
      searching = null;
    }
  });

  //just saved (?show=): the folder box it's in opens, and it's shown
  var saved = document.querySelector('.folder-main tr[data-show]');
  if (saved) {
    var up = saved.closest('details.sub-box');
    while (up) { up.open = true; up = up.parentElement.closest('details.sub-box'); }
    saved.classList.add('just-saved');
    saved.scrollIntoView({ block: 'center' });
  }

  var token = document.querySelector('meta[name="csrf-token"]');
  function move(d, to) {
    var data = new FormData();
    data.append('csrf_token', token ? token.content : '');
    data.append(d.kind, d.id);
    data.append('to', to);
    data.append('view', view);
    data.append('from', d.home);  // the folder it was dragged out of ("top": the main list)
    fetch(layout.dataset.moveUrl, { method: 'POST', body: data, credentials: 'same-origin',
                                    headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) { return r.json().catch(function () { return { ok: false }; }); })
      .then(function (res) {
        if (res.ok) {
          try { sessionStorage.setItem('qgen-moved', JSON.stringify({ text: res.message, box: d.kind + ':' + d.id })); } catch (e) {}
          location.reload();
          return;
        }
        alert(res.error || 'That didn\'t work. Please reload the page and try again.');
      });
  }

  /* dragging, done here with the mouse (the browser's own drag and drop is unreliable on a
   * box's title row and on links): press, move a little, and a label follows the pointer;
   * let go over a folder. A plain click still does what it did. Esc cancels. On a touch
   * screen this is left alone (scrolling comes first; the Move to / Add to lists do the job). */
  var pending = null, dragging = null, ghost = null, over = null, swallowClick = false;
  function targetAt(x, y) {
    var el = document.elementFromPoint(x, y), t = el && el.closest ? el.closest('[data-drop]') : null;
    if (!t || t.dataset.drop === dragging.home) return null;
    if (dragging.kind === 'folder' && dragging.el.contains(t)) return null;  // not into itself
    return t;
  }
  function highlight(t) {
    if (over === t) return;
    if (over) over.classList.remove('drop-over');
    over = t;
    if (over) over.classList.add('drop-over');
  }
  function stop() {
    highlight(null);
    if (ghost) ghost.remove();
    if (dragging) dragging.el.classList.remove('dragging');
    document.body.classList.remove('folder-dragging');
    pending = dragging = ghost = null;
  }
  document.querySelectorAll('[data-drag]').forEach(function (h) {
    h.addEventListener('pointerdown', function (e) {
      if (e.button !== 0 || e.pointerType === 'touch') return;
      if (e.target.closest('button, input, select, textarea')) return;  // its own controls still work
      var kind = h.dataset.drag;
      pending = { kind: kind, id: h.dataset.id, home: h.dataset.home, label: h.dataset.name,
                  el: h.closest('[data-box]') || h, x: e.clientX, y: e.clientY };
      e.preventDefault();  // no text selection while dragging; a click still goes through
    });
  });
  document.addEventListener('pointermove', function (e) {
    if (pending && !dragging) {
      if (Math.abs(e.clientX - pending.x) + Math.abs(e.clientY - pending.y) < 6) return;
      dragging = pending;
      ghost = document.createElement('div');
      ghost.className = 'drag-ghost';
      ghost.textContent = (dragging.kind === 'folder' ? '📁 ' : '') + dragging.label;
      document.body.appendChild(ghost);
      dragging.el.classList.add('dragging');
      document.body.classList.add('folder-dragging');
    }
    if (!dragging) return;
    ghost.style.left = (e.clientX + 14) + 'px';
    ghost.style.top = (e.clientY + 10) + 'px';
    highlight(targetAt(e.clientX, e.clientY));
  });
  document.addEventListener('pointerup', function (e) {
    if (!dragging) { pending = null; return; }
    var d = dragging, t = targetAt(e.clientX, e.clientY);
    //the click that follows a drag shouldn't open the box or follow the link
    swallowClick = true;
    setTimeout(function () { swallowClick = false; }, 0);
    stop();
    if (t) move(d, t.dataset.drop);
  });
  document.addEventListener('click', function (e) {
    if (!swallowClick) return;
    swallowClick = false;
    e.preventDefault();
    e.stopPropagation();
  }, true);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && (pending || dragging)) stop(); });
  window.addEventListener('blur', stop);
})();
