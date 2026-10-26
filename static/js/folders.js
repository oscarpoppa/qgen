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
  var FOLD = layout.dataset.foldKey, folded = load(FOLD), shows = [];
  path.forEach(function (id) { delete folded[id]; });
  document.querySelectorAll('.side-item').forEach(function (li) {
    var btn = li.querySelector(':scope > .side-row > .side-fold');
    if (!btn) return;
    function show(open) {
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      li.classList.toggle('side-folded', !open);
      if (open) delete folded[li.dataset.folder]; else folded[li.dataset.folder] = true;
    }
    shows.push({ id: li.dataset.folder, show: show });
    show(!folded[li.dataset.folder]);
    //a folder above the one being looked at can't be folded: the folder you're in always shows
    if (path.slice(0, -1).map(String).indexOf(String(li.dataset.folder)) !== -1) {
      btn.disabled = true;
      btn.title = 'You\u2019re in a folder inside this one, so it stays open';
      return;
    }
    btn.addEventListener('click', function () { show(btn.getAttribute('aria-expanded') !== 'true'); save(FOLD, folded); });
  });
  save(FOLD, folded);
  //a folder opened from its tab on the right is shown in this list too: the folders above it
  //unfold (the owner, 2026-10-15; static/js/folderfilter.js asks)
  window.qgenSideReveal = function (id) {
    var li = document.querySelector('.side-item[data-folder="' + id + '"]');
    for (var up = li && li.parentElement.closest('.side-item'); up; up = up.parentElement.closest('.side-item')) {
      shows.forEach(function (x) { if (String(x.id) === String(up.dataset.folder)) x.show(true); });
    }
    save(FOLD, folded);
  };
  //Expand all / Collapse all above the list (the folders above the one you're in stay open)
  //(always there: grayed out, with why, when no folder in the list has folders inside it)
  var levels = document.querySelector('.side-levels');
  //(beside the folder list's heading "Folders", as on every picker: the owner, 2026-10-23; it was
  //beside the page's title. It still opens and folds the list's folders)
  var sideHead = levels && document.querySelector('.folder-side > .side-list-head');
  if (sideHead) {
    levels.qgenScope = levels.parentElement;
    levels.classList.add('title-levels');
    sideHead.appendChild(levels);
  }
  if (levels) levels.hidden = false;
  if (levels && !shows.length) levels.querySelectorAll('[data-side-level]').forEach(function (b) {
    b.disabled = true;
    b.title = 'No folder here has folders inside it';
  });
  if (levels && shows.length) {
    levels.addEventListener('click', function (e) {
      var b = e.target.closest('[data-side-level]');
      if (!b) return;
      var open = b.dataset.sideLevel === 'open';
      //(the folder you're in folds too, like its own arrow: only the folders above it stay open)
      shows.forEach(function (s) { s.show(open || path.slice(0, -1).map(String).indexOf(String(s.id)) !== -1); });
      save(FOLD, folded);
    });
  }

  //on a phone the folder list starts folded (its heading says which folder is shown)
  var side = document.querySelector('details.folder-side');
  if (side && window.matchMedia('(max-width: 760px)').matches) side.open = false;

  //folder boxes (and every other box) open, fold and are remembered, and Expand all /
  //Collapse all work, in static/js/boxes.js
  function restore(d) { if (window.qgenBoxes) window.qgenBoxes.restore(d); }

  //+ New folder, and Folder options' Rename / Move to / + New folder inside: each opens its own
  //small dialog (the owner, 2026-10-16). The dialog moves to the page's end the first time, so a
  //closed Folder options (or a folder tab's copy of it) doesn't hide it; Folder options closes.
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-fopt]');
    if (!b) return;
    //(a folder's "+ New folder inside" has no dialog of its own: it opens the page's one New folder dialog)
    var box = b._dialog || b.parentElement.querySelector(':scope > dialog[data-fopt-dialog]')
      || (b.dataset.fopt === 'new' ? document.querySelector('dialog[data-fopt-dialog="new"]') : null);
    if (!box) return;
    e.preventDefault();
    b._dialog = box;
    if (!box._wired) {
      box._wired = true;
      document.body.appendChild(box);
      box.querySelector('[data-cancel]').addEventListener('click', function () { box.close(); });
      box.addEventListener('close', function () { box.querySelector('form').reset(); });
    }
    //(New folder starts on that folder, or the one being looked at; its picker is drawn again from there)
    var holder = b.dataset.fopt === 'new' && box.querySelector('[data-folder-pick]');
    if (holder) {
      var at = b.dataset.newAt || holder.dataset.home;
      if (holder.dataset.checked !== at) {
        holder.dataset.checked = at;
        var old = holder.querySelector('table');
        if (old) old.remove();
      }
    }
    var menu = b.closest('details.folder-tools');
    if (menu) menu.open = false;
    box.showModal();
    var name = box.querySelector('input[name=name]');
    if (name) { name.focus(); name.select(); }
  });

  //after a drag: "Moved "train" to "abc"." at the top, and what moved lit up
  function movedSay(done) {
    if (!done || !done.text) return;
    var list = document.createElement('ul'), item = document.createElement('li');
    list.className = 'alerts';
    list.setAttribute('role', 'status');
    item.className = 'alert alert-success';
    item.textContent = done.text;
    list.appendChild(item);
    var main = document.querySelector('main');
    main.insertBefore(list, main.firstChild);
    //over the page, not in it: the page stays where it was (place.js, which runs after this)
    function float() { if (window.qgenFloat) window.qgenFloat(list); }
    if (window.qgenFloat) float(); else document.addEventListener('DOMContentLoaded', float);
    var box = document.querySelector('[data-box="' + done.box + '"]');
    if (box) {
      box.classList.add('just-moved');
      setTimeout(function () { box.classList.remove('just-moved'); }, 2500);
    }
  }
  //(after a reload: kept for the fallback below)
  (function () {
    var done = null;
    try { done = JSON.parse(sessionStorage.getItem('qgen-moved') || 'null'); sessionStorage.removeItem('qgen-moved'); } catch (e) {}
    movedSay(done);
  })();

  //after a move, the page as it is now, swapped in without reloading (the owner, 2026-10-25: "the whole page blanks
  //out and comes back"): the list (each folder box is set up again by folderfilter.js), its page controls, and the
  //folder list's counts, changed in place so its folds and drop places stay. Anything that doesn't line up: a reload.
  function sideKey(row) {
    var a = row.querySelector('a[href]');
    if (!a || a.dataset.sideTab) return null;
    var u = new URL(a.getAttribute('href'), location.href);
    return u.pathname + u.search;
  }
  //(also for a page whose contents changed meanwhile, a hand-in or a grade: static/js/messages.js, the owner 2026-10-25)
  window.qgenRefreshList = function () { refreshInPlace(null); };
  function refreshInPlace(done) {
    var reload = function () {
      try { sessionStorage.setItem('qgen-moved', JSON.stringify(done)); } catch (e) {}
      if (window.qgenNotePlace) window.qgenNotePlace();  // back to the same place after the reload
      location.reload();
    };
    if (!window.fetch || !window.DOMParser || !window.qgenFolderFilterSetUp) return reload();
    fetch(location.href, { credentials: 'same-origin' }).then(function (r) {
      if (!r.ok || r.redirected) throw new Error('not the page');
      return r.text();
    }).then(function (html) {
      var doc = new DOMParser().parseFromString(html, 'text/html');
      var oldBoxes = document.querySelectorAll('.folder-main [data-folder-filter]'), newBoxes = doc.querySelectorAll('.folder-main [data-folder-filter]');
      var oldPagers = document.querySelectorAll('nav.pager'), newPagers = doc.querySelectorAll('nav.pager');
      if (!oldBoxes.length || oldBoxes.length !== newBoxes.length || oldPagers.length !== newPagers.length) throw new Error('not the same page');
      var fresh = {};
      doc.querySelectorAll('.folder-side .side-row').forEach(function (row) { var k = sideKey(row); if (k) fresh[k] = row; });
      document.querySelectorAll('.folder-side .side-row').forEach(function (row) {
        var k = sideKey(row), n = k && fresh[k];
        if (!n) return;
        ['.side-count', '.side-flags', '.side-inner-dots'].forEach(function (sel) {
          var a = row.querySelector(sel), b = n.querySelector(sel);
          if (a && b) a.innerHTML = b.innerHTML;
          else if (a) a.remove();
          else if (b) {
            //(in their usual order: its own dots, then the small ones for the folders inside, then the count)
            var at = (sel === '.side-flags' && row.querySelector('.side-inner-dots')) || row.querySelector('.side-count');
            if (at) row.insertBefore(document.importNode(b, true), at); else row.appendChild(document.importNode(b, true));
          }
        });
        row.classList.toggle('is-empty', n.classList.contains('is-empty'));
      });
      Array.prototype.forEach.call(oldPagers, function (p, i) { p.replaceWith(document.importNode(newPagers[i], true)); });
      Array.prototype.forEach.call(oldBoxes, function (b, i) {
        var nb = document.importNode(newBoxes[i], true);
        if (b.qgenTearDown) b.qgenTearDown();
        b.replaceWith(nb);
        window.qgenFolderFilterSetUp(nb);
        //(what's checked stays checked in the new rows, as after a sort: checked.js)
        if (window.qgenCheckedIds) {
          var kept = {}, first = null;
          window.qgenCheckedIds().forEach(function (id) { kept[id] = 1; });
          nb.querySelectorAll('input[name="items"], input.pick-person').forEach(function (t) {
            if (kept[t.value] && !t.checked) { t.checked = true; first = first || t; }
          });
          if (first) first.dispatchEvent(new Event('change', { bubbles: true }));
        }
      });
      document.dispatchEvent(new CustomEvent('qgen-swapped', { detail: { list: document.querySelector('.folder-main') } }));
      //(a name typed in the filter still narrows the new list)
      document.querySelectorAll('[data-filter-bar]').forEach(function (bar) { if (bar.qgenRun) bar.qgenRun(); });
      movedSay(done);
    }).catch(reload);
  }

  //after a "Move to" list, "+ Add to folder…" or a bar's button (the page came back with
  //?moved=quiz:12): the same glow as after a drag; the address is tidied
  (function () {
    var params = new URLSearchParams(location.search), moved = params.get('moved');
    if (!moved) return;
    params.delete('moved');
    try { history.replaceState(null, '', location.pathname + (params.toString() ? '?' + params : '') + location.hash); } catch (e) {}
    var box = document.querySelector('[data-box="' + moved.replace(/"/g, '') + '"]');
    if (!box) return;
    //lit up where it is; the page keeps its place (static/js/place.js), and its folder box
    //opens only if that grows below what's in view, never pushing the page down
    box.classList.add('just-moved');
    setTimeout(function () { box.classList.remove('just-moved'); }, 2500);
    var shut = box.closest('details.sub-box:not([open])');
    if (shut) window.addEventListener('load', function () {
      setTimeout(function () { if (shut.getBoundingClientRect().top >= 0) shut.open = true; }, 50);
    });
  })();

  //checked rows (the bar above the list puts them in a folder): something listed twice
  //(in a folder and a folder inside it) is checked in both; the bar says how many
  //(People's check boxes are the people picked for Assign: the same bar uses them)
  var ticks = Array.prototype.slice.call(document.querySelectorAll('.folder-main input[name="items"], .folder-main input.pick-person'));
  var fileForm = document.getElementById('file-form'), fileCount = document.querySelector('.file-count');
  function counted() {
    //(everything checked, here or in another folder: static/js/checked.js)
    if (window.qgenCheckedIds) return window.qgenCheckedIds().length;
    var ids = {};
    ticks.forEach(function (t) { if (t.checked) ids[t.value] = 1; });
    return Object.keys(ids).length;
  }
  //nothing checked: the bar says what to do, and its list and button are grayed out, with the
  //reason in their tooltips
  function syncBar() {
    if (!fileForm) return;
    var n = counted(), sel = fileForm.querySelector('select');
    fileForm.classList.toggle('file-bar-idle', !n);
    if (fileCount) {
      fileCount.textContent = n ? n + ' checked:' : (fileCount.dataset.hint || '0 checked');
      fileCount.classList.remove('error');
    }
    if (sel) { sel.disabled = !n; if (!n) sel.title = 'Check something below first'; else sel.removeAttribute('title'); }
    //(the bar's actions wherever they sit: in the "With checked" dialog now, still the bar's by
    //form="file-form"; the dialog's own button keeps its own words, static/js/filebar.js)
    document.querySelectorAll('#file-form button, button[form="file-form"]').forEach(function (b) {
      if (b.classList.contains('with-checked')) return;
      //(no folders yet: grayed, with why, never hidden: the owner, 2026-10-19)
      if (b.dataset.noFolder !== undefined) { b.disabled = true; b.title = b.dataset.noFolder; return; }
      b.disabled = !n || (sel && sel.value === '');
      if (!b.dataset.titleWas) b.dataset.titleWas = b.title || '';
      b.title = !n ? 'Check something below first' : b.disabled ? 'Choose a folder first' : b.dataset.titleWas;
    });
  }
  ticks.forEach(function (t) {
    t.addEventListener('change', function () {
      ticks.forEach(function (o) { if (o.value === t.value) o.checked = t.checked; });
      syncBar();
    });
  });
  if (fileForm) { fileForm.addEventListener('change', syncBar); syncBar(); }
  document.addEventListener('qgen-checked', syncBar);
  if (fileForm) fileForm.addEventListener('submit', function (e) {
    if (!counted()) {
      e.preventDefault();
      if (fileCount) { fileCount.textContent = 'Check at least one first'; fileCount.classList.add('error'); }
    }
  });

  //the results pages: a box per student (or quiz). The filter bar (static/js/filter.js) matches
  //a box's name or a row in it; "Show" keeps only the rows waiting for grading, or not handed
  //in yet (tr[data-state]), inside each row; the rows themselves stay closed.
  var resultsBar = document.getElementById('results-filter');
  //(a row like My quizzes' (tr.result-item, the owner 2026-10-21): its groups of attempts
  //(.result-group[data-state]) count as its rows, and its fold opens instead)
  var itemBoxes = Array.prototype.slice.call(document.querySelectorAll('.folder-main details.item-box, .folder-main tr.result-item'));
  function foldOf(d) { return d.tagName === 'TR' ? d.querySelector('details.row-fold') : d; }
  if (resultsBar) resultsBar.qgenFilter = function (q) {
    var stateFilter = resultsBar.querySelector('select.state-filter'), st = stateFilter ? stateFilter.value : 'all';
    var active = !!q || st !== 'all';
    itemBoxes.forEach(function (d) {
      var named = !q || (d.dataset.name || '').indexOf(q) !== -1, rows = d.querySelectorAll('tr[data-state], .result-group[data-state]'), shown = 0;
      rows.forEach(function (r) {
        //(the name only, as the box says: a quiz's name inside no longer counts; "is" found "teacher"
        //through "Christmas Trivia": the owner, 2026-10-22)
        var ok = (st === 'all' || r.dataset.state === st) && named;
        r.hidden = !ok;
        if (ok) shown++;
      });
      //(its own flag: a folder button's choice stays, static/js/folderfilter.js)
      var hide = !named || (rows.length ? !shown : st !== 'all');
      if (window.qgenHideRow) window.qgenHideRow(d, 'text', hide); else d.hidden = hide;
      //(rows stay closed: a filter or "Show" never opens them, everything starts closed; the owner,
      //2026-10-21: "Not handed in yet only" used to open every row)
      var fold = foldOf(d);
      if (fold && !active) restore(fold);
    });
    var none = document.querySelector('.filter-none');
    //(only for the name and Show filters: an empty folder says so itself, folderfilter.js)
    if (none) none.hidden = !active || itemBoxes.some(function (d) { return !d.hidden; });
    //(a list shown a page at a time: the count is the server's, all the pages' worth; app/paging.py)
    if ('paged' in resultsBar.dataset) return +resultsBar.dataset.matches || 0;
    return itemBoxes.filter(function (d) { return !d.hidden; }).length;
  };

  //just saved (?show=): the folder box it's in opens, and it's shown
  var saved = document.querySelector('.folder-main tr[data-show]');
  if (saved) {
    var up = saved.closest('details.sub-box');
    while (up) { up.open = true; up = up.parentElement.closest('details.sub-box'); }
    var row = saved.querySelector('details.row-fold');  // (a row that folds: shown open)
    if (row) row.open = true;
    saved.classList.add('just-saved');
    saved.scrollIntoView({ block: 'center' });
  }

  var token = document.querySelector('meta[name="csrf-token"]');
  function move(d, to, confirm) {
    var data = new FormData();
    data.append('csrf_token', token ? token.content : '');
    data.append(d.kind, d.id);
    data.append('to', to);
    data.append('view', view);
    data.append('from', d.home);  // the folder it was dragged out of ("top": the main list; "": a copy)
    if (confirm) data.append('confirm', confirm);
    fetch(layout.dataset.moveUrl, { method: 'POST', body: data, credentials: 'same-origin',
                                    headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) { return r.json().catch(function () { return { ok: false }; }); })
      .then(function (res) {
        //out of its only folder: delete it or put it in Uncategorized? (app/takeout.py)
        if (res.confirm && window.qgenAsk) {
          //(where it will go, OK or Cancel: never deleted by dragging it out, the owner 2026-10-15)
          window.qgenAsk((res.preview || []).join(' ') || res.confirm, 'Take out').then(function (yes) { if (yes) move(d, to, 'uncategorized'); });
          return;
        }
        if (res.ok) {
          refreshInPlace({ text: res.message, box: d.kind + ':' + d.id });
          return;
        }
        window.qgenSay(res.error || 'That didn\'t work. Please reload the page and try again.', 'error');
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
      //dragged out of the folder shown (a folder tab, or the folder box it's in): a move
      var shown = kind === 'folder' ? null : (window.qgenShownFolder && window.qgenShownFolder(h));
      //(from All: something in exactly one folder moves out of that one; in several, it's a copy)
      if (!shown && kind !== 'folder') {
        //(a card holds its Remove; a table row has it in another cell)
        var rm = (h.closest('[data-box]') || h).querySelector('form[data-remove-one]'), fs = [];
        if (!rm && h.closest('tr')) rm = h.closest('tr').querySelector('form[data-remove-one]');
        try { fs = JSON.parse(rm ? rm.dataset.folders : '[]'); } catch (err) {}
        if (fs.length === 1) shown = String(fs[0]);
      }
      pending = { kind: kind, id: h.dataset.id, home: shown || h.dataset.home, label: h.dataset.name,
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
      ghost.textContent = dragging.label;
      if (dragging.kind === 'folder' && window.qgenIcon) ghost.insertAdjacentHTML('afterbegin', window.qgenIcon('folder') + ' ');
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
    //Ctrl (or ⌘) held: a copy, it stays where it was too
    if (t && d.kind !== 'folder' && (e.ctrlKey || e.metaKey) && t.dataset.drop !== 'top') d.home = '';
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

  //Folder options floats over the page: a click outside it, or Esc, closes it
  document.addEventListener('click', function (e) {
    document.querySelectorAll('details.folder-tools[open]').forEach(function (d) {
      if (!d.contains(e.target) && !e.target.closest('dialog')) d.open = false;
    });
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    document.querySelectorAll('details.folder-tools[open]').forEach(function (d) {
      d.open = false;
      var s = d.querySelector('summary');
      if (s) s.focus();
    });
  });
})();

/* Folder pages (Problems, Quizzes, People, the results pages): the title and its buttons sit over
   the folder list only (the buttons small, wrapping there), and the list's side slides up beside
   them into the room that leaves (the owner, 2026-10-15). Only where the folders come right
   under the title; on a phone it all stays stacked. */
(function () {
  var layout = document.querySelector('.folders-layout');
  var head = layout && layout.previousElementSibling;
  if (!head || !head.classList.contains('page-head')) return;
  var main = layout.querySelector(':scope > .folder-main'), side = layout.querySelector(':scope > .folder-side');
  if (!main || !side) return;
  function lift() {
    main.style.marginTop = '';
    head.style.maxWidth = '';
    head.classList.remove('lifted');
    if (window.innerWidth <= 760) return;
    head.classList.add('lifted');
    head.style.maxWidth = (side.getBoundingClientRect().right - head.getBoundingClientRect().left) + 'px';
    main.style.marginTop = -(main.getBoundingClientRect().top - head.getBoundingClientRect().top) + 'px';
  }
  lift();
  window.addEventListener('resize', lift);
  window.addEventListener('load', lift);
  //(the folder list made wider or narrower by hand)
  if (window.ResizeObserver) new ResizeObserver(function () { lift(); }).observe(side);
})();

/* the folder list down the side: no taller than the window has room for below its top, then it
   scrolls inside itself (the owner, 2026-10-17); on phones it's stacked and folds away instead */
(function () {
  //(the list inside it scrolls: a <details> doesn't clip what's in it)
  var side = document.querySelector('.folders-layout > .folder-side'), nav = side && side.querySelector(':scope > nav');
  if (!nav) return;
  function fit() {
    nav.style.maxHeight = '';
    nav.classList.remove('side-scroll');
    if (window.innerWidth <= 760) return;
    var top = nav.getBoundingClientRect().top + window.scrollY;
    //(the folder list's own bottom padding and border, then the page's bottom margin, so the
    //page itself doesn't scroll)
    var main = side.closest('main'), gap = main ? parseFloat(getComputedStyle(main).paddingBottom) || 16 : 16;
    //(what sits under the card: the hint, a page's own button like Just finished)
    var below = 0;
    for (var el = nav.nextElementSibling; el; el = el.nextElementSibling) {
      if (el.offsetParent) below += el.offsetHeight + (parseFloat(getComputedStyle(el).marginTop) || 0);
    }
    nav.style.maxHeight = Math.max(200, window.innerHeight - top - gap - 3 - below) + 'px';
    nav.classList.add('side-scroll');
  }
  fit();
  setTimeout(fit, 0);
  window.addEventListener('load', fit);
  window.addEventListener('resize', fit);
})();

/* My quizzes: a quiz's Move (a bare folder icon) opens a dialog to choose the folder, like the
   other folder dialogs; the folder it's in now is shown grayed; Move sends the quiz's own small
   form (the owner, 2026-10-15). The Archive's attempts too.
   Laid out like the Assign dialogs (the owner, 2026-10-22): 820px wide, the title and a short line,
   what moving does in the amber "What happens:" box, then the standard picker (side folder list,
   Uncategorized right after All, beside a tab over the folders' table): static/js/dialogfilter.js.
   The folders are the page's one list (_folders.html move_folders). */
(function () {
  var data = document.getElementById('move-folders');
  if (!data) return;
  var page = JSON.parse(data.textContent), box = null, list, err;
  var folders = page.folders.map(function (f) { return { id: String(f[0]), name: f[1], depth: f[2], icon: f[3] }; });
  //(made the first time it's wanted: this file runs before the deferred dialogfilter.js)
  function make() {
    box = document.createElement('dialog');
    box.className = 'ask ask-many assign-many pick-dialog put-dialog move-dialog';
    box.innerHTML = '<p data-pick-head><strong data-head></strong><br><span class="muted small" data-sub></span></p>'
      + '<div class="assign-defaults small"><strong>' + (window.qgenIcon ? window.qgenIcon('lc-alert') : '') + 'What happens:</strong><ul data-happens></ul></div>'
      + window.qgenFolderPick.html()
      + '<p class="error small" data-err hidden>Choose a folder first.</p>'
      + '<div class="btn-row"><button type="button" class="btn" data-ok>Move</button><button type="button" class="btn btn-secondary" data-no>Cancel</button></div>';
    document.body.appendChild(box);
    list = box.querySelector('[data-folder-pick]'); err = box.querySelector('[data-err]');
    box.querySelector('[data-no]').addEventListener('click', function () { box.close(); });
    box.addEventListener('change', function () { err.hidden = true; });
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-move-one]');
    if (!b) return;
    e.preventDefault();  // (it's on the box's heading: not folding it)
    e.stopPropagation();
    openMove(b.closest('form'), b.dataset.label);
  }, true);
  //(also the Archive's Remove, "Move from …": the row's own Move form, static/js/takeout.js)
  window.qgenMoveOne = openMove;
  function openMove(form, label) {
    if (!box) make();
    var here = form.querySelector('input[name=from]').value;
    box.querySelector('[data-head]').textContent = 'Move ' + (label || 'it') + ' to a folder';
    box.querySelector('[data-sub]').textContent = 'Choose the folder to move it to.';
    //(an Archive attempt or a My quizzes quiz: each is in one folder at a time; said in the amber
    //box, not as a gray line under the title: the owner, 2026-10-22)
    window.qgenFolderPick.happens(box.querySelector('[data-happens]'), ['It leaves the folder it\u2019s in now',
      (form.querySelector('input[name=attempt]') ? 'An attempt' : 'A quiz') + ' is in one folder at a time']);
    //(the folder it's in now: grayed, "(here now)")
    window.qgenFolderPick.fill(list, folders, { type: 'radio', name: 'move-to', top: page.main,
      each: function (f, r, lab) {
        if (String(f.id) !== here) return;
        r.disabled = true;
        lab.lastChild.textContent += ' (here now)';
      } });
    err.hidden = true;
    window.qgenPickOk(list);
    box.querySelector('[data-ok]').onclick = function () {
      var r = list.querySelector('input[name=move-to]:checked');
      if (!r) { window.qgenPickError(list, 'Choose a folder first.'); return; }
      form.querySelector('input[name=to]').value = r.value;
      box.close();
      form.submit();
    };
    box.showModal();
  }
})();
