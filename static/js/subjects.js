/* Subjects on the Problems and Quizzes lists: the Subject menu switches the list as
 * soon as it's changed; "Select all shown" ticks the rows the filter box leaves
 * showing; the count says how many are ticked. */
(function () {
  document.querySelectorAll('select[data-autosubmit]').forEach(function (sel) {
    sel.addEventListener('change', function () { sel.form.submit(); });
  });

  var form = document.getElementById('file-form');
  if (!form) return;
  var boxes = Array.prototype.slice.call(document.querySelectorAll('input[name="items"][form="file-form"]'));
  var count = form.querySelector('.file-count');

  function update() {
    var n = boxes.filter(function (b) { return b.checked; }).length;
    if (count) count.textContent = n + ' ticked';
  }
  boxes.forEach(function (b) { b.addEventListener('change', update); });

  var all = form.querySelector('[data-select-shown]');
  if (all) all.addEventListener('click', function () {
    var shown = boxes.filter(function (b) { return !b.closest('tr').hidden; });
    var tick = shown.some(function (b) { return !b.checked; });
    shown.forEach(function (b) { b.checked = tick; });
    all.textContent = tick ? 'Clear ticks' : 'Select all shown';
    update();
  });

  form.addEventListener('submit', function (e) {
    if (!boxes.some(function (b) { return b.checked; })) {
      e.preventDefault();
      if (count) { count.textContent = 'Tick at least one first'; count.classList.add('error'); }
    }
  });
  update();
})();
