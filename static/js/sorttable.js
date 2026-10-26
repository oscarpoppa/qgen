/* Sorting a folder's list by a column (the owner, 2026-10-17): on list pages (Problems,
 * Quizzes, People, the Archive), and in cards with a table (Grading, one quiz's results...), each
 * table heading with words is a button. Press it to sort by
 * that column, A to Z (or low to high); press again for Z to A. Every table in the open folder
 * sorts the same way, and this browser remembers the choice for the page.
 * A cell can say what to sort by with data-sort (a date, a score); otherwise its name (the
 * first link or bold words) or its words are used. Empty cells go last either way. */
(function () {
  var KEY = 'qgen-sort:' + location.pathname;
  var collator = window.Intl && Intl.Collator ? new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' }) : null;
  function cmp(a, b) { return collator ? collator.compare(a, b) : a < b ? -1 : a > b ? 1 : 0; }

  function keyOf(cell) {
    if (!cell) return '';
    if (cell.dataset.sort !== undefined) return cell.dataset.sort;
    //(a row's own name first: a box's title, then a name link; never a button's words inside it)
    var named = cell.querySelector('.box-title') || cell.querySelector('.name-link') || cell.querySelector('a strong, strong') || cell.querySelector('a:not(.btn):not(.icon-link)');
    return ((named || cell).textContent || '').replace(/\s+/g, ' ').trim();
  }
  function label(th) { return (th.textContent || '').replace(/\s+/g, ' ').trim(); }

  function sortTable(table, name, down) {
    var heads = Array.prototype.slice.call(table.querySelectorAll(':scope > thead > tr > th'));
    var col = heads.map(label).indexOf(name);
    heads.forEach(function (th) {
      var b = th.querySelector('.th-sort');
      if (!b) return;
      var on = label(th) === name;
      th.setAttribute('aria-sort', on ? (down ? 'descending' : 'ascending') : 'none');
      b.dataset.dir = on ? (down ? 'down' : 'up') : '';
    });
    if (col < 0) return;
    var body = table.tBodies[0];
    if (!body) return;
    var rows = Array.prototype.slice.call(body.rows);
    rows.map(function (r, i) { return { r: r, i: i, k: keyOf(r.cells[col]) }; })
      .sort(function (x, y) {
        if (!x.k !== !y.k) return x.k ? -1 : 1;  // (empty last)
        var c = cmp(x.k, y.k);
        return (down ? -c : c) || x.i - y.i;
      })
      .forEach(function (o) { body.appendChild(o.r); });
  }

  //a heading's words made into its sort button (every sortable table, paged or not)
  function headButton(th, name) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'th-sort';
    b.title = 'Sort by ' + name.toLowerCase() + ' (press again to reverse)';
    b.innerHTML = '<span></span><span class="th-sort-arrow" aria-hidden="true"></span>';
    b.firstChild.textContent = name;
    th.textContent = '';
    th.appendChild(b);
    return b;
  }
  //a paged list's headings: each asks the server for the list sorted that way, from page 1, and only the list
  //and its page numbers are swapped in, so the page doesn't blink (the owner, 2026-10-25, CR1); the
  //address follows (replaceState), so a reload or coming back finds it sorted the same
  function pagedHeads(table) {
    var on = table.dataset.sorted || '', dir = table.dataset.sortedDir === 'desc' ? 'desc' : 'asc';
    table.querySelectorAll(':scope > thead > tr > th[data-sort-key]').forEach(function (th) {
      var name = label(th), k = th.dataset.sortKey;
      var b = headButton(th, name);
      th.setAttribute('aria-sort', k === on ? (dir === 'desc' ? 'descending' : 'ascending') : 'none');
      b.dataset.dir = k === on ? (dir === 'desc' ? 'down' : 'up') : '';
      b.addEventListener('click', function () {
        var u = new URL(location.href);
        u.searchParams.set('sort', k);
        u.searchParams.set('dir', k === on && dir === 'asc' ? 'desc' : 'asc');
        ['page', 'show', 'moved'].forEach(function (x) { u.searchParams.delete(x); });
        swapIn(table, u.pathname + u.search + u.hash);
      });
    });
  }
  //the columns stay where they were while sorting, instead of shifting a little with each page's rows
  //(the owner, 2026-10-25, CR3): the new table gets the old one's column widths, as shares of the table
  //(not on a phone, where the rows are cards and there are no columns)
  function keepColumns(old, added) {
    var heads = old.querySelectorAll(':scope > thead > tr > th');
    if (!heads.length || !old.tHead || getComputedStyle(old.tHead).display === 'none') return;
    var whole = old.getBoundingClientRect().width;
    var fresh = added.querySelectorAll(':scope > thead > tr > th');
    if (!whole || fresh.length !== heads.length) return;
    heads.forEach(function (th, i) {
      fresh[i].style.width = (old.dataset.fixedCols ? th.style.width : (100 * th.getBoundingClientRect().width / whole).toFixed(3) + '%');
    });
    added.style.tableLayout = 'fixed';
    added.dataset.fixedCols = '1';
  }
  //(a list made of several tables, like the Trash's month boxes, is swapped in whole: its [data-sort-swap])
  function swapIn(table, url) {
    var go = function () { location.assign(url); };  // (anything odd: just open it, as before)
    if (!window.fetch || !window.DOMParser || !(window.history && history.replaceState)) return go();
    var group = table.closest('[data-sort-swap]');
    var old = group || table;
    var mine = Array.prototype.indexOf.call(document.querySelectorAll('table[data-paged]'), table);
    //(switched at once, like opening or folding a row: dimmed only if the server is slow to answer)
    var slow = setTimeout(function () { table.classList.add('is-sorting'); }, 300);
    fetch(url, { credentials: 'same-origin' }).then(function (r) {
      if (!r.ok || r.redirected) throw new Error('not the list');
      return r.text();
    }).then(function (html) {
      clearTimeout(slow);
      var doc = new DOMParser().parseFromString(html, 'text/html');
      var fresh = group ? doc.querySelector('[data-sort-swap="' + group.dataset.sortSwap + '"]') : doc.querySelectorAll('table[data-paged]')[mine];
      var oldPagers = document.querySelectorAll('nav.pager'), newPagers = doc.querySelectorAll('nav.pager');
      if (!fresh || oldPagers.length !== newPagers.length) throw new Error('not the same page');
      var added = document.importNode(fresh, true);
      var tablesOf = function (el) { return el.matches('table') ? [el] : Array.prototype.slice.call(el.querySelectorAll('table[data-paged]')); };
      var before = tablesOf(old), after = tablesOf(added);
      after.forEach(function (t, i) { if (before[i] || before[0]) keepColumns(before[i] || before[0], t); });
      old.replaceWith(added);
      Array.prototype.forEach.call(oldPagers, function (p, i) { p.replaceWith(document.importNode(newPagers[i], true)); });
      after.forEach(pagedHeads);
      //(what's checked in this folder is checked again in the new rows: checked.js)
      if (window.qgenCheckedIds) {
        var kept = {};
        window.qgenCheckedIds().forEach(function (id) { kept[id] = 1; });
        var first = null;
        added.querySelectorAll('input[name="items"], input.pick-person').forEach(function (t) {
          if (kept[t.value] && !t.checked) { t.checked = true; first = first || t; }
        });
        if (first) first.dispatchEvent(new Event('change', { bubbles: true }));
      }
      history.replaceState(history.state, '', url);
      document.dispatchEvent(new CustomEvent('qgen-address'));  // (the Back trail keeps it: trail.js)
      //(scripts that set up a list's parts once, like its heading check box, do the new one: filebar.js)
      document.dispatchEvent(new CustomEvent('qgen-swapped', { detail: { list: added } }));
    }).catch(go);
  }

  function setUp(list, key) {
    //(not a table that's part of a form being filled in, like the problem editor's Random values;
    //nor a heading with its own controls, like a ? help button)
    var tables = Array.prototype.slice.call(list.querySelectorAll('table')).filter(function (t) { return !t.closest('form') || t.classList.contains('pick-table'); });
    //a list shown a page at a time (app/paging.py; the owner, 2026-10-23) sorts the whole folder: its
    //headings (data-sort-key) ask the server for the sorted pages, from page 1 (pagedHeads)
    tables.filter(function (t) { return t.hasAttribute('data-paged'); }).forEach(pagedHeads);
    tables = tables.filter(function (t) { return !t.hasAttribute('data-paged'); });
    if (!tables.length) return;
    tables.forEach(function (table) {
      table.querySelectorAll(':scope > thead > tr > th').forEach(function (th) {
        var name = label(th);
        if (!name || th.classList.contains('tick-col') || th.querySelector('.sr-only:only-child') || th.querySelector('.th-sort')) return;
        if (th.querySelector('button, a, input, select, .tip-wrap, [role=tooltip]')) return;
        var b = headButton(th, name);
        th.setAttribute('aria-sort', 'none');
        b.addEventListener('click', function () {
          var down = b.dataset.dir === 'up';
          tables.forEach(function (t) { sortTable(t, name, down); });
          try { localStorage.setItem(key, JSON.stringify({ name: name, down: down })); } catch (e) {}
        });
      });
    });
    var saved = null;
    try { saved = JSON.parse(localStorage.getItem(key) || 'null'); } catch (e) {}
    if (saved && saved.name) tables.forEach(function (t) { sortTable(t, saved.name, !!saved.down); });
  }

  function all() {
    //(the open folder on a list page; not a picker card or a dialog)
    //(and a student's page, whose quizzes are rows like My quizzes': the owner, 2026-10-21)
    document.querySelectorAll('.folder-main .folder-filter-list, .folder-main #folder-items, .student-folders .folder-filter-list').forEach(function (list) {
      if (list.closest('dialog') || list.qgenSorts) return;
      list.qgenSorts = true;
      setUp(list, KEY);
    });
    //a picker's list (a dialog's, the Assign page's cards): its own name column sorts, remembered for
    //each picker (the owner, 2026-10-21)
    document.querySelectorAll('table.pick-table').forEach(function (t) {
      var wrap = t.parentElement;
      if (wrap.qgenSorts) return;
      wrap.qgenSorts = true;
      var ff = t.closest('[data-remember]');
      setUp(wrap, 'qgen-sort:pick:' + (ff ? ff.dataset.remember : location.pathname));
    });
    //cards with a table elsewhere (one quiz's results, Grading, a student's page...): each card
    //sorts its own table (the owner, 2026-10-17)
    document.querySelectorAll('main details.box, main .card').forEach(function (card, i) {
      if (card.closest('dialog') || card.closest('.folder-main') || card.qgenSorts || !card.querySelector('table:not(.pick-table)')) return;
      if (card.parentElement && card.parentElement.closest('details.box, .card')) return;  // (the outer card does it)
      card.qgenSorts = true;
      //(remembered for each card: by its name on the page, else its place)
      setUp(card, KEY + ':' + (card.id || card.dataset.box || i));
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', all); else all();
  //(a list swapped in place, after a drop, an upload or a live change: its headings sort too; the ones set up already
  //are marked and skipped; the code critic, 2026-10-25)
  document.addEventListener('qgen-swapped', all);
})();
