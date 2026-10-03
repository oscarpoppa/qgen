/* Subject containers on the Problems and Quizzes pages and in the quiz builder:
 * - each container opens and closes; which are open is remembered in this browser
 *   (the wrapper's data-store names the key); "Open all" / "Close all"
 * - an item in several subjects is in several containers: ticking one copy ticks them all
 * - each container's heading says how many in it are ticked
 * - searching opens the containers with matches and hides the rest; clearing the
 *   search puts them back as they were
 * - after saving, the saved item's containers open and it is scrolled to (data-show)
 * Also: a select[data-autosubmit] sends its form when changed (the Archive page). */
(function () {
  document.querySelectorAll('select[data-autosubmit]').forEach(function (sel) {
    sel.addEventListener('change', function () { sel.form.submit(); });
  });

  var wrap = document.querySelector('.subject-boxes');
  if (!wrap) return;

  //Rename / Delete sit in a container's heading: clicking them mustn't also open or
  //close it. Rename opens the container and shows its name box.
  wrap.addEventListener('click', function (e) {
    var actions = e.target.closest('.box-actions');
    if (!actions) return;
    var rename = e.target.closest('[data-rename]');
    if (rename) {
      e.preventDefault();
      var box = rename.closest('details'), form = document.getElementById(rename.dataset.rename);
      box.open = true;
      form.hidden = false;
      var input = form.querySelector('input[name="name"]');
      input.focus();
      input.select();
      return;
    }
    //a Delete button: let its form submit (after the in-page question), but don't toggle
    if (e.target.closest('button')) {
      e.preventDefault();
      var f = e.target.closest('form');
      if (f.requestSubmit) f.requestSubmit(); else f.submit();
    }
  });
  wrap.addEventListener('click', function (e) {
    var cancel = e.target.closest('[data-rename-cancel]');
    if (cancel) cancel.closest('form').hidden = true;
  });
  var boxes = Array.prototype.slice.call(wrap.querySelectorAll('details.subject-box'));
  var key = wrap.dataset.store;
  var searching = false;

  function load() {
    try { return JSON.parse(localStorage.getItem(key) || 'null'); } catch (e) { return null; }
  }
  function store() {
    if (searching) return;
    var open = boxes.filter(function (b) { return b.open; }).map(function (b) { return b.dataset.box; });
    try { localStorage.setItem(key, JSON.stringify(open)); } catch (e) { /* private window: not remembered */ }
  }

  //first visit: everything open, so nothing seems missing (except empty folders, marked data-empty)
  var saved = load();
  function firstOpen(b) { return !('empty' in b.dataset); }
  boxes.forEach(function (b) { b.open = saved ? saved.indexOf(b.dataset.box) !== -1 : firstOpen(b); });
  boxes.forEach(function (b) { b.addEventListener('toggle', store); });

  document.querySelectorAll('[data-boxes]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var open = btn.dataset.boxes === 'open';
      boxes.forEach(function (b) { if (!b.hidden) b.open = open; });
      store();
    });
  });

  //tick boxes: list pages use name="items", the builder uses class="pick"
  var ticks = Array.prototype.slice.call(wrap.querySelectorAll('input[name="items"], input.pick'));
  var count = document.querySelector('.file-count');
  function update() {
    boxes.forEach(function (b) {
      var n = b.querySelectorAll('input[name="items"]:checked, input.pick:checked').length;
      var badge = b.querySelector('.box-ticked');
      if (badge) { badge.hidden = !n; badge.textContent = n + ' checked'; }
    });
    if (count) {
      var ids = {};
      ticks.forEach(function (t) { if (t.checked) ids[t.value] = 1; });
      count.textContent = Object.keys(ids).length + ' checked';
      count.classList.remove('error');
    }
  }
  ticks.forEach(function (t) {
    t.addEventListener('change', function () {
      ticks.forEach(function (o) {
        if (o !== t && o.value === t.value && o.checked !== t.checked) {
          o.checked = t.checked;
        }
      });
      update();
    });
  });
  //the builder sets ticks itself (e.g. removing a problem from the order)
  wrap.addEventListener('qgen-ticks-changed', update);

  var form = document.getElementById('file-form');
  if (form) form.addEventListener('submit', function (e) {
    if (!ticks.some(function (t) { return t.checked; })) {
      e.preventDefault();
      if (count) { count.textContent = 'Check at least one first'; count.classList.add('error'); }
    }
  });

  //search (filter.js hides rows, then tells us)
  document.addEventListener('qgen-filtered', function (e) {
    var q = (e.target.value || '').trim();
    if (q) {
      if (!searching) { store(); searching = true; }
      boxes.forEach(function (b) {
        var hit = Array.prototype.some.call(b.querySelectorAll('tbody tr'), function (r) { return !r.hidden; });
        b.hidden = !hit;
        b.open = hit;
      });
    } else if (searching) {
      searching = false;
      var back = load();
      boxes.forEach(function (b) { b.hidden = false; b.open = back ? back.indexOf(b.dataset.box) !== -1 : firstOpen(b); });
    }
  });

  //just saved: open where it is and show it
  var shown = wrap.querySelectorAll('tr[data-show]');
  if (shown.length) {
    shown.forEach(function (r) { r.closest('details').open = true; r.classList.add('just-saved'); });
    store();
    shown[0].scrollIntoView({ block: 'center' });
  }
  update();
})();
