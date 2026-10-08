/* Filter bars, the same on every page (the filter_bar macro in _macros.html): a "Filter by
 * name…" box, how many match ("12 problems"), and Clear.
 *  - data-filter: the list it narrows; data-items: what in it counts as one thing (rows,
 *    quiz boxes, pictures...), each counted once even when it's in two folders (data-box)
 *  - data-boxes: the folder boxes in the list: while filtering, those with a match open and
 *    the others hide; Clear puts them back as they were
 *  - a page with its own way of narrowing (the Assign page's Quiz menu, the results pages'
 *    "Show" choice) sets bar.qgenFilter = function (words) { ...; return how many show }
 *  - a select in the bar (the results pages' "Show") filters again when it changes
 *  - Enter in the box never sends a form
 * A thing can be hidden by more than one filter (the typed words, the quiz builder's Folder
 * menu): each sets its own flag with qgenHideRow(row, 'name', true/false), and it shows only
 * when nothing hides it. */
window.qgenHideRow = function (row, key, hide) {
  var flags = (row.dataset.hiddenBy || '').split(' ').filter(function (f) { return f && f !== key; });
  if (hide) flags.push(key);
  row.dataset.hiddenBy = flags.join(' ');
  row.hidden = flags.length > 0;
};

(function () {
  function setUp(bar) {
    var input = bar.querySelector('input[type=search]');
    if (!input || bar.dataset.ready) return;
    bar.dataset.ready = '1';
    var count = bar.querySelector('[data-filter-count]'), clear = bar.querySelector('[data-filter-clear]');
    var root = bar.dataset.filter ? document.querySelector(bar.dataset.filter) : null;
    var one = bar.dataset.one || 'match', many = bar.dataset.many || 'matches';
    var before = null;  // which folder boxes were open before filtering
    var touched = false;  // nothing is shown or hidden until someone filters

    function things() { return root ? Array.prototype.slice.call(root.querySelectorAll(bar.dataset.items || 'tbody tr')) : []; }
    function words(el) { return (el.dataset.name || el.textContent).toLowerCase(); }
    function shows(el) { return !el.hidden && !el.closest('[hidden]'); }
    function boxes() { return root && bar.dataset.boxes ? Array.prototype.slice.call(root.querySelectorAll(bar.dataset.boxes)) : []; }

    //folder boxes: open where something matches, hide the rest; put back when cleared
    function fold(active) {
      var all = boxes();
      if (!all.length) return;
      if (active) {
        if (!before) before = all.map(function (d) { return d.open; });
        all.forEach(function (d) { d.hidden = false; });
        all.slice().reverse().forEach(function (d) {
          var hit = things().some(function (el) { return d.contains(el) && shows(el); });
          d.hidden = !hit;
          if (hit) d.open = true;
        });
      } else if (before) {
        all.forEach(function (d, i) { d.hidden = false; d.open = before[i]; });  // just as they were
        before = null;
      }
    }

    function run() {
      var q = input.value.trim().toLowerCase(), shown;
      if (typeof bar.qgenFilter === 'function') {
        shown = bar.qgenFilter(q);
      } else if (q || touched) {
        touched = true;
        things().forEach(function (el) { window.qgenHideRow(el, 'text', !!q && words(el).indexOf(q) === -1); });
      }
      var active = !!q || Array.prototype.some.call(bar.querySelectorAll('select'), function (s) { return s.selectedIndex > 0; });
      fold(active);
      if (typeof shown !== 'number') {
        var seen = {};
        shown = 0;
        things().forEach(function (el) {
          if (el.hidden) return;
          var key = el.dataset.box || el.dataset.item;
          if (!key) { shown++; return; }
          if (!seen[key]) { seen[key] = 1; shown++; }
        });
      }
      if (count) count.textContent = shown + ' ' + (shown === 1 ? one : many);
      input.dispatchEvent(new CustomEvent('qgen-filtered', { bubbles: true, detail: { active: active } }));
    }

    input.addEventListener('input', run);
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter') e.preventDefault(); });
    bar.querySelectorAll('select').forEach(function (s) { s.addEventListener('change', run); });
    if (clear) clear.addEventListener('click', function () {
      input.value = '';
      bar.querySelectorAll('select').forEach(function (s) { s.selectedIndex = 0; });
      run();
      input.focus();
    });
    bar.qgenRun = run;  // for a page that changes the list itself (the quiz builder's Folder menu)
    bar.hidden = false;
    run();
  }
  document.querySelectorAll('[data-filter-bar]').forEach(setUp);
})();
