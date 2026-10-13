/* Every box that opens and folds (<details class="box">, step 1's standard heading) opens,
 * folds and is remembered the same way, on every page:
 *
 * Starting state: a page's own sections (the HTML says open: Home, the Dashboard, settings)
 * start open; boxes in a list (data-list: quizzes, students, folders, months...) start
 * closed, except the only one in its list, which starts open; data-closed ones (Done, help)
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
  function save() { try { localStorage.setItem(KEY, JSON.stringify(memory)); } catch (e) {} }

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
    if (d.hasAttribute('data-list')) return listed(d).length === 1;
    return d.dataset.drawnOpen === '1';
  }
  function restore(d) {
    if (d.closest('[data-keep-open]')) { d.open = true; return; }
    var id = idOf(d);
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
    if (d._byHand && Date.now() - d._byHand < 1000) { memory[idOf(d)] = d.open ? 1 : 0; save(); }
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
      if (keep && !d.hasAttribute('data-fixed')) memory[idOf(d)] = want ? 1 : 0;
    });
    if (keep) save();
  });
  //every folder box holding boxes of its own (sub-folders, quizzes, attempts) gets its own
  //Expand all / Collapse all pair, on its heading line at the right (taking no room of its own);
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
      open.textContent = 'Expand all'; open.setAttribute('aria-label', 'Expand all in ' + name); open.title = 'Open every box in ' + name;
      close.textContent = 'Collapse all'; close.setAttribute('aria-label', 'Collapse all in ' + name); close.title = 'Fold every box in ' + name + ' down to its heading';
      head.appendChild(bar);
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
          b.title = set.length ? b.dataset.title0 : 'Nothing here opens or folds';
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
    }, 0);
  }
  document.addEventListener('qgen-filtered', showLevelButtons);
  window.addEventListener('resize', showLevelButtons);

  window.qgenBoxes = { restore: restore, idOf: idOf, levels: showLevelButtons };
  setUp(document);
  //boxes drawn later (the Dashboard's refresh, pages that redraw parts of themselves)
  if (window.MutationObserver) new MutationObserver(function (changes) {
    if (changes.some(function (c) { return c.addedNodes.length; })) setUp(document);
  }).observe(document.querySelector('main') || document.body, { childList: true, subtree: true });
  document.dispatchEvent(new CustomEvent('qgen-boxes-ready'));
})();
