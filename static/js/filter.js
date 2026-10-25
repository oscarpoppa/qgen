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
    //a list shown a page at a time (app/paging.py; the owner, 2026-10-23): the words typed go to the server,
    //which sends the page of matches; the count is the server's (data-matches), no row is hidden here
    var paged = 'paged' in bar.dataset;
    //(the Checked folder open: how many are still checked, not the server's count from when the page was sent; the owner, 2026-10-24)
    if (paged) bar.qgenFilter = function () {
      var open = document.querySelector('.folder-main .folder-filter[data-chosen="checked"]');
      return open && window.qgenCheckedIds ? window.qgenCheckedIds().length : +bar.dataset.matches || 0;
    };
    var count = bar.querySelector('[data-filter-count]'), clear = bar.querySelector('[data-filter-clear]');
    //a folder page's list: the count goes under the page's heading instead (_folders.html)
    var under = bar.dataset.filter === '#folder-items' && document.getElementById('folder-count');
    //(beside the folder heading, "Problems  9 problems", not on a line of its own over the filter:
    //the owner, 2026-10-15)
    var title = document.getElementById('folder-title');
    if (under) {
      if (count) count.remove(); count = under; under.hidden = false;
      if (title) { under.classList.add('title-count'); title.insertAdjacentElement('afterend', under); } else bar.insertBefore(under, bar.firstChild);
    }
    var root = bar.dataset.filter ? document.querySelector(bar.dataset.filter) : null;
    var one = bar.dataset.one || 'match', many = bar.dataset.many || 'matches';
    var before = null;  // which folder boxes were open before filtering
    var none = null;  // the "Nothing matches" note
    var touched = false;  // nothing is shown or hidden until someone filters
    var first = true;  // the run on the page's opening

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
          var key = el.dataset.box || el.dataset.item, w = el.dataset.weight ? +el.dataset.weight : 1;
          if (!key) { shown += w; return; }
          if (!seen[key]) { seen[key] = 1; shown += w; }
        });
      }
      //(the count can count something else than the things: Grading's attempts, data-count-many)
      var cOne = bar.dataset.countOne || one, cMany = bar.dataset.countMany || many;
      if (count) count.textContent = shown + ' ' + (shown === 1 ? cOne : cMany);
      //nothing matches: say so, with a way back (a page with its own note keeps it: the results pages)
      //(a page with its own way of narrowing too, unless it has its own note: People had nothing at
      //all to say for 0 matches, the owner 2026-10-22)
      if (root && !(typeof bar.qgenFilter === 'function' && document.querySelector('.filter-none'))) {
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
          //(a "Show" choice in the bar is named too: it may be what leaves nothing, the owner 2026-10-22)
          var picked = Array.prototype.filter.call(bar.querySelectorAll('select'), function (s) { return s.selectedIndex > 0; })
            .map(function (s) { return '\u201c' + s.options[s.selectedIndex].text + '\u201d'; });
          var said = q ? '\u201c' + input.value.trim() + '\u201d' + (picked.length ? ' with ' + picked.join(' and ') : '') : picked.join(' and ');
          none.textContent = said ? 'Nothing matches ' + said + '. ' : 'Nothing matches. ';
          var again = document.createElement('button');
          again.type = 'button';
          again.className = 'btn btn-link btn-sm';
          again.textContent = 'Clear the filter';
          again.title = 'Show all the ' + many + ' again';
          again.addEventListener('click', function () { if (clear) clear.click(); else { input.value = ''; run(); } });
          none.appendChild(again);
        }
      }
      //(not on the page's first run with nothing typed or chosen: nothing changed, and the folder
      //tabs, grids and lists that listen would only lay themselves out again, 0.25 s on Problems in
      //Firefox; the owner, 2026-10-21)
      if (!first || active) input.dispatchEvent(new CustomEvent('qgen-filtered', { bubbles: true, detail: { active: active } }));
      first = false;
    }

    input.addEventListener('input', run);
    if (paged) {
      var pagedChoice = bar.querySelector('select');
      var go = function () {
        clearTimeout(go.t);
        var u = new URL(location.href), v = input.value.trim();
        if (v) u.searchParams.set('q', v); else u.searchParams.delete('q');
        //(the results pages' Show choice goes to the server too: ?state=)
        if (pagedChoice && pagedChoice.selectedIndex > 0) u.searchParams.set('state', pagedChoice.value); else u.searchParams.delete('state');
        ['page', 'show', 'moved'].forEach(function (k) { u.searchParams.delete(k); });
        if (u.search === location.search) return;
        try { sessionStorage.setItem('qgen-refocus-filter', '1'); } catch (e) {}
        location.assign(u.pathname + u.search + u.hash);
      };
      //(after a short pause in typing, or Enter)
      input.addEventListener('input', function () { clearTimeout(go.t); go.t = setTimeout(go, 500); });
      input.addEventListener('keydown', function (e) { if (e.key === 'Enter') go(); });
      if (clear) clear.addEventListener('click', function () { input.value = ''; if (pagedChoice) pagedChoice.selectedIndex = 0; go(); });
      if (pagedChoice) pagedChoice.addEventListener('change', go);
      var asked = new URLSearchParams(location.search).get('q');
      if (asked) input.value = asked;
      var askedState = new URLSearchParams(location.search).get('state');
      if (pagedChoice && askedState && Array.prototype.some.call(pagedChoice.options, function (o) { return o.value === askedState; })) pagedChoice.value = askedState;
      //(the page just reloaded for what was typed: the cursor is back in the box, after the words)
      try {
        if (sessionStorage.getItem('qgen-refocus-filter')) {
          sessionStorage.removeItem('qgen-refocus-filter');
          input.focus(); input.setSelectionRange(input.value.length, input.value.length);
        }
      } catch (e) {}
    }
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
    //(the page's own bar is marked data-url-filter: filter_bar(..., url=true); a bar in a form
    //or inside one box, like a long class's on Results by quiz, never goes in the address)
    var inAddress = 'urlFilter' in bar.dataset && !!(window.history && history.replaceState);
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
  //the cursor starts in the page's filter box, ready to type (the owner, 2026-10-25, CQ1); not on a phone,
  //where it would pop the keyboard up over the list (CQ2), nor when something else already has it.
  //(once the page has loaded and is showing: a page is kept out of sight until its scripts have set it up)
  function cursorToFilter(tries) {
    try {
      if (document.activeElement && document.activeElement !== document.body) return;
      var first = Array.prototype.find.call(document.querySelectorAll('[data-filter-bar]'), function (b) {
        return !b.closest('dialog, [hidden]') && b.getClientRects().length;
      });
      var box = first && first.querySelector('input[type=search]');
      if (box && getComputedStyle(box).visibility === 'hidden') {
        if ((tries || 0) < 40) setTimeout(function () { cursorToFilter((tries || 0) + 1); }, 50);
        return;
      }
      if (box && window.matchMedia('(min-width: 768px) and (pointer: fine)').matches &&
          (!document.activeElement || document.activeElement === document.body) && !document.querySelector('[autofocus]')) {
        box.focus({ preventScroll: true });
        box.setSelectionRange(box.value.length, box.value.length);
      }
    } catch (e) {}
  }
  if (document.readyState === 'complete') cursorToFilter(0); else window.addEventListener('load', function () { cursorToFilter(0); });
  //(for bars a script adds later: the folder dialogs' filter, dialogfilter.js)
  window.qgenFilterBar = setUp;
})();
