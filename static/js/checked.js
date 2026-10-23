/* What's checked on a page with a checked bar (Problems, Quizzes, People, the Archive) is kept,
 * whatever folder is open: moving between folders (tabs, the folder list, a folder's own page,
 * Back) never loses it (the owner, 2026-10-15); the Checked folder (folderfilter.js) lists what's
 * checked (its chips are gone: the owner, 2026-10-21). Kept in this browser tab
 * (sessionStorage), per page; cleared once the bar's action is done.
 * For the bar's scripts: window.qgenCheckedIds() (every checked one, here or not, in the order
 * checked) and window.qgenCheckedClear(). */
(function () {
  var form = document.getElementById('file-form');
  var bar = form && form.closest('.folder-tools-bar');
  if (!bar) return;
  var TICKS = '.folder-main input[name="items"], .folder-main input.pick-person';
  var KEY = 'qgen-checked:' + location.pathname;
  var kept = [];  // [[id, name]]
  try { kept = JSON.parse(sessionStorage.getItem(KEY) || '[]') || []; } catch (e) { kept = []; }
  function save() { try { sessionStorage.setItem(KEY, JSON.stringify(kept)); } catch (e) {} }
  function has(id) { return kept.some(function (k) { return k[0] === id; }); }
  function ticks() { return Array.prototype.slice.call(document.querySelectorAll(TICKS)); }
  function nameOf(t) {
    var l = t.getAttribute('aria-label') || '';
    return l.replace(/^Check\s+/, '') || t.value;
  }

  //(no chips any more: the Checked folder lists what's checked, the owner 2026-10-21; a check all
  //of 254 problems filled the page with them)
  function set(id, name, on) {
    var i = -1;
    kept.forEach(function (k, j) { if (k[0] === id) i = j; });
    if (on && i === -1) kept.push([id, name]);
    if (!on && i !== -1) kept.splice(i, 1);
    save();
    //(the bar recounts and grays its buttons from this list, after it's changed)
    setTimeout(function () { document.dispatchEvent(new CustomEvent('qgen-checked')); }, 0);
  }
  //(the boxes on this page follow; the bar recounts)
  function sync(id, on) {
    var changed = null;
    ticks().forEach(function (t) { if (t.value === id && t.checked !== on) { t.checked = on; changed = t; } });
    if (changed) changed.dispatchEvent(new Event('change', { bubbles: true }));
    else document.dispatchEvent(new CustomEvent('qgen-checked'));
  }
  document.addEventListener('change', function (e) {
    var t = e.target;
    if (!t.matches || !t.matches(TICKS)) return;
    set(t.value, nameOf(t), t.checked);
  });

  window.qgenCheckedIds = function () { return kept.map(function (k) { return k[0]; }); };
  //every one of a list at once, on every page (a list shown 20 at a time: "Check all 57"; the owner,
  //2026-10-23): pairs of [id, name]
  window.qgenCheckMany = function (pairs, on) {
    pairs.forEach(function (p) {
      var id = String(p[0]), i = -1;
      kept.forEach(function (k, j) { if (k[0] === id) i = j; });
      if (on && i === -1) kept.push([id, p[1]]);
      if (!on && i !== -1) kept.splice(i, 1);
    });
    save();
    ticks().forEach(function (t) { t.checked = has(t.value); });
    document.dispatchEvent(new CustomEvent('qgen-checked'));
    //(the checked bar and the Checked folder count again)
    if (ticks()[0]) ticks()[0].dispatchEvent(new Event('change', { bubbles: true }));
  };
  window.qgenAllChecked = function (pairs) { return pairs.length > 0 && pairs.every(function (p) { return has(String(p[0])); }); };
  window.qgenCheckedClear = function () {
    kept = []; save();
    ticks().forEach(function (t) { t.checked = false; });
  };

  //coming back to the page (another folder, a reload): what was checked is checked again
  var first = null;
  ticks().forEach(function (t) { if (has(t.value) && !t.checked) { t.checked = true; first = first || t; } });
  if (first) first.dispatchEvent(new Event('change', { bubbles: true }));
  document.dispatchEvent(new CustomEvent('qgen-checked'));
})();
