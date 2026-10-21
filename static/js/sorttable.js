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

  function setUp(list, key) {
    //(not a table that's part of a form being filled in, like the problem editor's Random values;
    //nor a heading with its own controls, like a ? help button)
    var tables = Array.prototype.slice.call(list.querySelectorAll('table')).filter(function (t) { return !t.closest('form') || t.classList.contains('pick-table'); });
    if (!tables.length) return;
    tables.forEach(function (table) {
      table.querySelectorAll(':scope > thead > tr > th').forEach(function (th) {
        var name = label(th);
        if (!name || th.classList.contains('tick-col') || th.querySelector('.sr-only:only-child') || th.querySelector('.th-sort')) return;
        if (th.querySelector('button, a, input, select, .tip-wrap, [role=tooltip]')) return;
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'th-sort';
        b.title = 'Sort by ' + name.toLowerCase() + ' (press again to reverse)';
        b.innerHTML = '<span></span><span class="th-sort-arrow" aria-hidden="true"></span>';
        b.firstChild.textContent = name;
        th.textContent = '';
        th.appendChild(b);
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
})();
