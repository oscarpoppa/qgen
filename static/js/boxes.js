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
    //a folder (shown as a folder button, static/js/foldertabs.js) waits to be picked
    if (d.matches('details.sub-box[data-sub], details.sub-box[data-folder-box]')) return false;
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
    var sel = btn.dataset.levelOf;
    return sel ? document.querySelector(sel) : btn.closest('.level');
  }
  function folds(level) {
    if (!level) return [];
    return Array.prototype.filter.call(level.querySelectorAll(FOLDS), function (d) {
      //hidden by a filter: left alone; a row of folder buttons (foldertabs.js) opens one at a time
      return !d.hasAttribute('data-fixed') && !d.closest('[hidden]')
        && !(d.classList.contains('tab-box') && d.qgenRow && !d.qgenRow.classList.contains('tabs-off'));
    });
  }
  document.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('[data-level]');
    if (!btn) return;
    var want = btn.dataset.level === 'open', keep = !btn.closest('[data-keep-open]');
    folds(levelOf(btn)).forEach(function (d) {
      d.open = want;
      if (keep) memory[idOf(d)] = want ? 1 : 0;
    });
    if (keep) save();
  });
  function showLevelButtons() {
    clearTimeout(showLevelButtons._t);
    showLevelButtons._t = setTimeout(function () {
      document.querySelectorAll('.level-buttons').forEach(function (pair) {
        var btn = pair.querySelector('[data-level]');
        pair.hidden = !btn || folds(levelOf(btn)).length < 2;
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
