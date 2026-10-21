/* Every box that opens and folds (<details class="box">, step 1's standard heading) opens,
 * folds and is remembered the same way, on every page:
 *
 * Starting state: a page's own sections (the HTML says open: Home, the Dashboard, settings)
 * start open; boxes in a list (data-list: quizzes, students, folders, months...) and list rows
 * start closed, even the only one (the owner, 2026-10-19); data-closed ones (Done, help)
 * start closed; data-fixed ones (Assign's people) are left as the page drew them.
 *
 * Memory: what this person opens or folds themselves (a click on its heading, or Expand all
 * / Collapse all) is remembered in this browser, for this page, for them. A box a search or
 * a "just saved" opens isn't. Boxes drawn later (the Dashboard's refresh) get theirs too.
 * Inside [data-keep-open] (My quizzes from a Home counter) everything shows open.
 *
 * Expand all / Collapse all: buttons [data-level="open"|"close"] open or fold every box that
 * holds several things (folders, a quiz's or a student's tries, the Dashboard's and Home's
 * boxes...), everywhere inside their level (the nearest .level, or data-level-of=
 * "<selector>"), folders inside folders too. Small boxes (.box-mini: a quiz's problem list)
 * and long questions are left as they are. Their .level-buttons pair shows only where there
 * are two or more boxes.
 *
 * Page scripts can use window.qgenBoxes.restore(box) (back to remembered/starting state,
 * e.g. after a search) and listen for "qgen-boxes-ready". Loaded right after <main>, so it
 * runs before the page's own scripts. */
(function () {
  var me = document.currentScript;
  var KEY = 'qgen-boxes:' + ((me && me.dataset.user) || '') + ':' + location.pathname;
  var BOX = 'details.box:not(.box-mini)';
  var FOLDER = 'details.sub-box[data-sub], details.sub-box[data-folder-box]';
  var memory = {};
  try { memory = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) {}
  //the first time on a page, everything starts as the page draws it (folded); after that, what was
  //opened or folded by hand comes back however the page is reached (the owner, 2026-10-21; it
  //came back only when returning, 2026-10-19)
  var nav = performance.getEntriesByType && performance.getEntriesByType('navigation')[0];
  var going = null;
  try { going = sessionStorage.getItem('qgen-going-back'); } catch (e) {}
  var touched = {};  // (opened or folded by hand on this visit: kept as left)
  var returning = !!(nav && (nav.type === 'back_forward' || nav.type === 'reload')) || going !== null;
  //coming back from something done on this page (a Move, Take out, Delete, Restore, New folder:
  //the page sends a form and comes back) or from an editor's Save or Cancel: returning too, so
  //what was open stays open (the owner, 2026-10-19, from the code critic)
  var RET = 'qgen-returning';
  try {
    var ret = sessionStorage.getItem(RET);
    //('*': an editor's Save going back to wherever it came from, its list by default)
    if (ret === location.pathname || ret === '*') returning = true;
    sessionStorage.removeItem(RET);
  } catch (e) {}
  function willReturn(path) { try { sessionStorage.setItem(RET, path); } catch (e) {} }
  document.addEventListener('submit', function (e) {
    var f = e.target;
    if (!f || (f.method || '').toLowerCase() !== 'post') return;
    var next = f.querySelector('input[data-back-next], input[name="next"]');
    var to = next ? (next.value ? new URL(next.value, location.href).pathname : '*') : location.pathname;
    willReturn(to);
  }, true);
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[data-back-href]');
    if (a && a.href) willReturn(new URL(a.href, location.href).pathname);
  }, true);
  function save() { try { localStorage.setItem(KEY, JSON.stringify(memory)); } catch (e) {} }
  //a page can forget, once, what was remembered for some of its boxes, when how they start
  //changes: data-boxes-reset="<when>:<box>,<box>" (the Dashboard's list cards, 2026-10-15)
  var reset = document.querySelector('[data-boxes-reset]');
  if (reset) {
    var parts = reset.dataset.boxesReset.split(':'), mark = '_reset:' + parts[0];
    if (!memory[mark]) {
      (parts[1] || '').split(',').forEach(function (b) { delete memory[b]; });
      memory[mark] = 1;
      save();
    }
  }

  //a name for a box on this page that stays the same from visit to visit
  function idOf(d) {
    var s = d.dataset, own = s.box || (s.sub && 'sub:' + s.sub) || (s.quizBox && 'quiz:' + s.quizBox)
      || (s.folderBox && 'folder:' + s.folderBox) || (s.remember && 'section:' + s.remember) || (d.id && '#' + d.id);
    if (own) return own;
    var t = d.querySelector(':scope > summary .box-title'), up = d.parentElement && d.parentElement.closest(BOX);
    return (up ? idOf(up) + '/' : '') + 'title:' + (t ? t.textContent.trim() : '');
  }
  function listed(d) {
    return Array.prototype.filter.call(d.parentElement.children, function (b) {
      return b.matches && b.matches(BOX + '[data-list]') && !b.hidden;
    });
  }
  //how it starts before the person changes it (the HTML's own open is read once, first)
  function starting(d) {
    if (d.hasAttribute('data-closed')) return false;
    //a folder (shown as a folder button, static/js/foldertabs.js) waits to be picked, except
    //that the first one in a row at the top of the page starts open, so a page (the All views)
    //never starts with nothing showing but folder buttons; once any folder in that row is
    //opened or closed by hand, that's remembered instead
    if (d.matches(FOLDER)) {
      if (d.parentElement.closest(FOLDER)) return false;
      var row = Array.prototype.filter.call(d.parentElement.children, function (b) {
        return b.matches && b.matches(FOLDER) && !b.hidden;
      });
      return row[0] === d && !row.some(function (b) { return idOf(b) in memory; });
    }
    //(a box in a list starts folded, even the only one: the owner, 2026-10-19; it was open when
    //it was the only one)
    if (d.hasAttribute('data-list')) return false;
    return d.dataset.drawnOpen === '1';
  }
  function restore(d) {
    if (d.closest('[data-keep-open]')) { d.open = true; return; }
    var id = idOf(d);
    //(every page keeps its boxes as they were left, however it's reached: starting folded is only
    //for a box never opened or folded by hand; the owner, 2026-10-21. It used to be kept only
    //when coming back with Back)
    d.open = id in memory ? !!memory[id] : starting(d);
  }

  var seen = window.WeakSet ? new WeakSet() : { has: function () { return false; }, add: function () {} };
  function setUp(root) {
    var fresh = [];
    (root || document).querySelectorAll(BOX).forEach(function (d) {
      if (seen.has(d) || d.hasAttribute('data-fixed')) return;
      seen.add(d);
      d.dataset.drawnOpen = d.open ? '1' : '0';
      fresh.push(d);
    });
    fresh.forEach(restore);  // after all are read, so "the only one in its list" is known
    if (fresh.length) showLevelButtons();
  }

  //remembered: only what the person does themselves
  document.addEventListener('click', function (e) {
    var sum = e.target.closest && e.target.closest('summary');
    var d = sum && sum.parentElement;
    if (!d || !d.matches(BOX)) return;
    //a list in a heading (My quizzes' "Move… ▾") is used, not the box opened or folded
    if (e.target.closest('select')) { e.preventDefault(); return; }
    //a button or link on a heading line (History, Archive all, Open this folder...) does its job;
    //the box stays as it was
    var ctl = e.target.closest('a, button');
    if (ctl && ctl !== sum && !ctl.hasAttribute('data-level')) {
      var was = d.open;
      setTimeout(function () { if (d.open !== was) d.open = was; }, 0);
    }
    if (d.hasAttribute('data-fixed') || d.closest('[data-keep-open]')) return;
    if (e.target.closest('a, button, input, label') && e.target.closest('a, button, input, label') !== sum) return;
    d._byHand = Date.now();  // its toggle event comes a moment later
  }, true);
  document.addEventListener('toggle', function (e) {
    var d = e.target;
    if (!d.matches || !d.matches(BOX)) return;
    if (d._byHand && Date.now() - d._byHand < 1000) { memory[idOf(d)] = d.open ? 1 : 0; touched[idOf(d)] = 1; save(); }
    d._byHand = 0;
    showLevelButtons();
  }, true);

  //Expand all / Collapse all
  var FOLDS = BOX;
  function levelOf(btn) {
    //a folder's own things (the boxes after its "…: Uncategorized" line, foldertabs.js), not its folders
    if ('levelItems' in btn.dataset) {
      var list = [], head = btn.closest('.folder-items-head');
      for (var el = head && head.nextElementSibling; el; el = el.nextElementSibling) {
        if (el.matches(FOLDS)) list.push(el);
        Array.prototype.push.apply(list, el.querySelectorAll(FOLDS));
      }
      return { querySelectorAll: function () { return list; } };
    }
    var sel = btn.dataset.levelOf;
    return sel ? document.querySelector(sel) : btn.closest('.level');
  }
  //btn: a pair with data-level-fixed also opens and folds the boxes the page keeps as drawn
  //(data-fixed: Assign's folders of people), without remembering them
  function folds(level, btn) {
    if (!level) return [];
    var fixedToo = btn && 'levelFixed' in btn.dataset;
    return Array.prototype.filter.call(level.querySelectorAll(FOLDS), function (d) {
      //hidden by a filter: left alone (folders shown as a row of buttons count too: Expand all
      //shows them all open, static/js/foldertabs.js)
      return (fixedToo || !d.hasAttribute('data-fixed')) && !d.closest('[hidden]');
    });
  }
  document.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('[data-level]');
    if (!btn) return;
    var want = btn.dataset.level === 'open', keep = !btn.closest('[data-keep-open]');
    //a pair on a box's heading line: the click doesn't fold the box, and Expand all opens it too
    var head = btn.closest('summary');
    if (head) {
      e.preventDefault();
      if (want && head.parentElement.tagName === 'DETAILS') {
        head.parentElement.open = true;
        if (keep && head.parentElement.matches(BOX)) memory[idOf(head.parentElement)] = 1;
      }
    }
    folds(levelOf(btn), btn).forEach(function (d) {
      d.open = want;
      if (keep && !d.hasAttribute('data-fixed')) { memory[idOf(d)] = want ? 1 : 0; touched[idOf(d)] = 1; }
    });
    if (keep) save();
  });
  //every folder box holding boxes of its own (sub-folders, quizzes, attempts) gets its own
  //Expand all / Collapse all pair, on its heading line right after its name (taking no room of its own);
  //grayed out where there's nothing inside to open or fold (below)
  var pairs = 0;
  function addFolderPairs() {
    document.querySelectorAll('details.sub-box').forEach(function (d) {
      var body = d.querySelector(':scope > summary + *');
      if (!body || body.qgenPair) return;
      var own = Array.prototype.some.call(d.querySelectorAll('.level-buttons'), function (p) {
        return p.closest('details.sub-box') === d;
      });
      body.qgenPair = true;
      if (own) return;
      var t = d.querySelector(':scope > summary .box-title');
      var name = t ? '“' + t.textContent.trim() + '”' : 'this folder';
      var head = d.querySelector(':scope > summary');
      if (!body.id) body.id = 'folder-body-' + (++pairs);
      var bar = document.createElement('span');
      bar.className = 'head-pair';
      bar.innerHTML = '<span class="level-buttons">'
        + '<button type="button" class="btn btn-secondary btn-xs" data-level="open"></button>'
        + '<button type="button" class="btn btn-secondary btn-xs" data-level="close"></button></span>';
      var open = bar.querySelector('[data-level=open]'), close = bar.querySelector('[data-level=close]');
      open.dataset.levelOf = close.dataset.levelOf = '#' + body.id;
      window.qgenIconButton(open, 'lc-expand', 'Expand all', 'Open every box in ' + name); open.setAttribute('aria-label', 'Expand all in ' + name);
      window.qgenIconButton(close, 'lc-collapse', 'Collapse all', 'Fold every box in ' + name + ' down to its heading'); close.setAttribute('aria-label', 'Collapse all in ' + name);
      //(right after its name and badges, before any buttons on the line: the owner, 2026-10-19)
      var first = Array.prototype.filter.call(head.children, function (c) {
        return c.matches('.box-actions, .head-tools, .btn, .btn-row, form, a.btn');
      })[0];
      head.insertBefore(bar, first || null);
    });
  }
  function showLevelButtons() {
    addFolderPairs();
    clearTimeout(showLevelButtons._t);
    showLevelButtons._t = setTimeout(function () {
      //never two pairs for the same boxes: a pair that would open or fold exactly what one
      //shown before it (further out) does is left out
      var shown = [], emptyShown = [];
      //a folder's own pair (data-level-prefer: the folder chosen in a row of folder buttons) comes
      //first, so it's the one kept when the page's pair would do the same
      var pairs = Array.prototype.slice.call(document.querySelectorAll('.level-buttons'));
      pairs.sort(function (a, b) {
        return (b.querySelector('[data-level-prefer]') ? 1 : 0) - (a.querySelector('[data-level-prefer]') ? 1 : 0);
      });
      pairs.forEach(function (pair) {
        var btn = pair.querySelector('[data-level]');
        var set = btn ? folds(levelOf(btn), btn) : [];
        //always there; grayed out (with why) when there's nothing in it to open or fold
        pair.hidden = !btn;
        pair.querySelectorAll('[data-level]').forEach(function (b) {
          if (!('title0' in b.dataset)) b.dataset.title0 = b.title || '';
          b.disabled = !set.length;
          b.title = set.length ? b.dataset.title0 : (b.classList.contains('btn-icon') ? (b.textContent.trim() || (b.querySelector('svg[aria-label]') || { getAttribute: function () { return ''; } }).getAttribute('aria-label')) + ': ' : '') + 'Nothing here opens or folds';
        });
        if (pair.hidden || (pair.parentElement && pair.parentElement.closest('[hidden]'))) return;
        //a grayed pair (nothing to fold) is a copy only of one for the same list (a list's heading
        //and its tab row, one inside the other); separate lists each keep theirs, like Assign's
        //Quiz and Students cards side by side
        if (!set.length) {
          var lv = btn && levelOf(btn);
          var dup = lv && lv.nodeType === 1 && emptyShown.some(function (o) { return o === lv || o.contains(lv) || lv.contains(o); });
          if (dup) pair.hidden = true; else if (lv && lv.nodeType === 1) emptyShown.push(lv);
          return;
        }
        var same = shown.some(function (other) {
          return other.length === set.length && other.every(function (d, i) { return d === set[i]; });
        });
        if (same) pair.hidden = true;
        else shown.push(set);
      });
      syncToggles();
    }, 0);
  }

  /* Every Expand all / Collapse all pair is one toggle (the owner, 2026-10-16): only one of the
   * two shows, with its own icon: Expand all while anything it covers is folded, Collapse all
   * once everything is open. Both pairs kinds: boxes ([data-level]) and folder lists
   * ([data-side-level], whose folds are the .side-fold arrows beside it). */
  function syncToggles() {
    document.querySelectorAll('[data-level="open"]').forEach(function (open) {
      var close = open.parentElement && open.parentElement.querySelector(':scope > [data-level="close"]');
      if (!close) return;
      var set = folds(levelOf(open), open);
      var anyShut = !set.length || set.some(function (d) { return !d.open; });
      open.classList.toggle('lvl-off', !anyShut);
      close.classList.toggle('lvl-off', anyShut);
    });
    document.querySelectorAll('[data-side-level="open"]').forEach(function (open) {
      var row = open.parentElement, close = row && row.querySelector(':scope > [data-side-level="close"]');
      if (!close) return;
      //(a pair moved beside a title keeps its list: qgenScope, the owner 2026-10-19)
      var scope = row.qgenScope || row.parentElement || document;
      var all = Array.prototype.filter.call(scope.querySelectorAll('.side-fold'), function (f) { return !f.closest('[hidden]'); });
      var anyShut = !all.length || all.some(function (f) { return f.getAttribute('aria-expanded') === 'false'; });
      open.classList.toggle('lvl-off', !anyShut);
      close.classList.toggle('lvl-off', anyShut);
    });
  }
  var syncSoon = function () { clearTimeout(syncSoon.t); syncSoon.t = setTimeout(syncToggles, 30); };
  document.addEventListener('toggle', syncSoon, true);
  document.addEventListener('click', syncSoon);
  document.addEventListener('DOMContentLoaded', syncSoon);
  window.addEventListener('load', syncSoon);
  document.addEventListener('qgen-filtered', showLevelButtons);
  window.addEventListener('resize', showLevelButtons);

  window.qgenBoxes = { restore: restore, idOf: idOf, levels: showLevelButtons, toggles: syncSoon };
  setUp(document);
  //boxes drawn later (the Dashboard's refresh, pages that redraw parts of themselves)
  if (window.MutationObserver) new MutationObserver(function (changes) {
    if (changes.some(function (c) { return c.addedNodes.length; })) setUp(document);
  }).observe(document.querySelector('main') || document.body, { childList: true, subtree: true });
  document.dispatchEvent(new CustomEvent('qgen-boxes-ready'));
})();
