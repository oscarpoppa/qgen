/* Subject containers on the Problems and Quizzes pages and in the quiz builder:
 * - each container opens, folds and is remembered like every box (static/js/boxes.js)
 * - an item in several subjects is in several containers: checking one copy checks them all
 * - each container's heading says how many in it are checked
 * - after saving, the saved item's containers open and it is scrolled to (data-show)
 * Also: a select[data-autosubmit] sends its form when changed (the Archive page). */
(function () {
  document.querySelectorAll('select[data-autosubmit]').forEach(function (sel) {
    //(requestSubmit: like pressing a button, so the page keeps its place, static/js/place.js)
    sel.addEventListener('change', function () { if (sel.form.requestSubmit) sel.form.requestSubmit(); else sel.form.submit(); });
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
  //each box opens, folds and is remembered like every box (static/js/boxes.js)
  //the quiz editor's folder boxes (folders inside folders), or a results page's boxes
  var boxes = Array.prototype.slice.call(wrap.querySelectorAll('details.sub-box, details.subject-box'));

  //checkboxes: list pages use name="items", the builder uses class="pick"
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
  //the builder checks boxes itself (e.g. removing a problem from the order)
  wrap.addEventListener('qgen-ticks-changed', update);

  var form = document.getElementById('file-form');
  if (form) form.addEventListener('submit', function (e) {
    if (!ticks.some(function (t) { return t.checked; })) {
      e.preventDefault();
      if (count) { count.textContent = 'Check at least one first'; count.classList.add('error'); }
    }
  });

  //just saved: open where it is and show it
  var shown = wrap.querySelectorAll('tr[data-show]');
  if (shown.length) {
    shown.forEach(function (r) { r.closest('details').open = true; r.classList.add('just-saved'); });
    shown[0].scrollIntoView({ block: 'center' });
  }
  update();
})();
