/* The Folder question on the problem and quiz forms: its folders fold like every folder list
 * (an arrow on a folder with folders inside; Expand all / Collapse all above), remembered in
 * this browser. A folder with a checked folder inside it always stays open, so nothing
 * checked is ever out of sight. */
(function () {
  var list = document.querySelector('#subject-question .subject-check-list');
  if (!list) return;
  var rows = Array.prototype.slice.call(list.querySelectorAll('.subject-row'));
  var KEY = list.dataset.foldKey, folded = {};
  try { (JSON.parse(localStorage.getItem(KEY) || '[]') || []).forEach(function (id) { folded[id] = true; }); } catch (e) {}
  function save() { try { localStorage.setItem(KEY, JSON.stringify(Object.keys(folded))); } catch (e) {} }
  //the rows inside a row: those after it, deeper, until one at its depth or above
  function inside(i) {
    var d = +rows[i].dataset.depth, out = [];
    for (var j = i + 1; j < rows.length && +rows[j].dataset.depth > d; j++) out.push(rows[j]);
    return out;
  }
  function checkedInside(i) { return inside(i).some(function (r) { return r.querySelector('input:checked'); }); }
  function draw() {
    rows.forEach(function (r) { r.hidden = false; });
    rows.forEach(function (r, i) {
      var btn = r.querySelector('.side-fold');
      if (!btn) return;
      var open = !folded[r.dataset.folder] || checkedInside(i);
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (!open) inside(i).forEach(function (c) { c.hidden = true; });
    });
  }
  var folds = [];
  rows.forEach(function (r, i) {
    var btn = r.querySelector('.side-fold');
    if (!btn) return;
    folds.push(r);
    btn.addEventListener('click', function () {
      if (btn.getAttribute('aria-expanded') === 'true') {
        if (checkedInside(i)) return;  // (a checked folder inside: it stays open)
        folded[r.dataset.folder] = true;
      } else delete folded[r.dataset.folder];
      save();
      draw();
    });
  });
  list.addEventListener('change', draw);
  var levels = document.querySelector('#subject-question .subject-levels');
  //(beside the field's label, "Folder", not on top of the list: the owner, 2026-10-19)
  var lab = levels && levels.closest('fieldset') && levels.closest('fieldset').querySelector(':scope > legend');
  if (lab) {
    levels.qgenScope = levels.parentElement;
    levels.classList.add('title-levels');
    lab.appendChild(levels);
  }
  if (levels) {
    levels.hidden = false;
    if (!folds.length) levels.querySelectorAll('[data-side-level]').forEach(function (b) {
      b.disabled = true;
      b.title = 'No folder here has folders inside it';
    });
    else levels.addEventListener('click', function (e) {
      var b = e.target.closest('[data-side-level]');
      if (!b) return;
      folds.forEach(function (r) { if (b.dataset.sideLevel === 'open') delete folded[r.dataset.folder]; else folded[r.dataset.folder] = true; });
      save();
      draw();
    });
  }
  draw();
})();
