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
 *  - the page's one filter bar keeps its words (?q=) and Show choice (?state=) in the address
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
    var none = null;  // the "Nothing matches" note
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
      //nothing matches: say so, with a way back (a page with its own note keeps it: the results pages)
      if (typeof bar.qgenFilter !== 'function' && root) {
        if (!none) {
          none = document.createElement('p');
          none.className = 'card empty small filter-none-auto';
          none.hidden = true;
          //inside the list (it goes with it), unless the list itself hides when empty (folder tabs)
          if (root.matches('.folder-filter-list')) root.parentElement.insertBefore(none, root.nextSibling);
          else root.appendChild(none);
        }
        //(not when a folder tab already says it's empty)
        var box = root.closest('.folder-filter') || root.querySelector('.folder-filter');
        var said = box && box.querySelector('.folder-filter-empty:not([hidden])');
        none.hidden = !(active && shown === 0) || !!said;
        if (!none.hidden) {
          none.textContent = (q ? 'Nothing matches \u201c' + input.value.trim() + '\u201d. ' : 'Nothing matches. ');
          var again = document.createElement('button');
          again.type = 'button';
          again.className = 'btn btn-link btn-sm';
          again.textContent = 'Clear the filter';
          again.title = 'Show all the ' + many + ' again';
          again.addEventListener('click', function () { if (clear) clear.click(); else { input.value = ''; run(); } });
          none.appendChild(again);
        }
      }
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
    //the page's own filter bar (one on the page, not in a form) keeps what's typed (?q=) and
    //its Show choice (?state=) in the address, like the folder tabs (folderfilter.js): coming
    //back from an editor or an action finds the list narrowed just as it was left
    //(the page's own bar: the one over its folder list, else the only one that isn't in a form
    //or inside one box, like a long class's box on Results by quiz)
    var own = Array.prototype.filter.call(document.querySelectorAll('[data-filter-bar]'), function (b) { return !b.closest('form, details, .box'); });
    var main = document.querySelector('[data-filter-bar][data-filter="#folder-items"]') || (own.length === 1 ? own[0] : null);
    var inAddress = bar === main && !!(window.history && history.replaceState);
    var choice = bar.querySelector('select');
    if (inAddress) {
      var asked = new URLSearchParams(location.search);
      if (asked.get('q')) input.value = asked.get('q');
      if (choice && asked.get('state') && Array.prototype.some.call(choice.options, function (o) { return o.value === asked.get('state'); })) choice.value = asked.get('state');
      var remember = function () {
        var q = new URLSearchParams(location.search);
        if (input.value.trim()) q.set('q', input.value.trim()); else q.delete('q');
        if (choice && choice.selectedIndex > 0) q.set('state', choice.value); else q.delete('state');
        var s = q.toString();
        history.replaceState(history.state, '', location.pathname + (s ? '?' + s : '') + location.hash);
        document.dispatchEvent(new CustomEvent('qgen-address'));  // the Back trail keeps it (trail.js)
      };
      input.addEventListener('input', remember);
      if (choice) choice.addEventListener('change', remember);
      if (clear) clear.addEventListener('click', remember);
    }
    run();
  }
  document.querySelectorAll('[data-filter-bar]').forEach(setUp);
})();
