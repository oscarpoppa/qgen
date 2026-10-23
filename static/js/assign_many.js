/* Assign quizzes (the owner, 2026-10-15): the Quizzes page's checked bar, and any one quiz's
 * paper plane (a quiz row, Edit quiz, Results by quiz: a link to the Assign page with ?vq=) open
 * a dialog to pick the people (People's folders as the folder list, and a filter); the quizzes are then
 * given to them (/quiz/assignmany), and the page comes back as it was. The dialog links to the
 * Assign page for opening and closing times. */
(function () {
  var dialog = document.getElementById('assign-many-dialog');
  var btn = document.querySelector('[data-assign-many]');
  if (!dialog) return;
  var people = Array.prototype.slice.call(dialog.querySelectorAll('.folder-filter-list tr[data-box]'));
  var boxes = people.map(function (li) { return li.querySelector('input'); });
  //(the folder list and the filter, static/js/folderfilter.js, hide the people not shown)
  function shownNow(li) { return !li.hidden && !li.closest('[hidden]'); }
  var error = dialog.querySelector('[data-people-error]');
  function checkedQuizzes() {
    if (window.qgenCheckedIds) return window.qgenCheckedIds();
    var ids = {};
    document.querySelectorAll('.folder-main input[name="items"]:checked').forEach(function (t) { ids[t.value] = 1; });
    return Object.keys(ids);
  }
  function sync() {
    if (boxes.some(function (b) { return b.checked; })) error.hidden = true;
  }
  dialog.addEventListener('change', sync);
  dialog.querySelector('[data-cancel]').addEventListener('click', function () { dialog.close(); });
  //"open it": the Assign page with what's checked here now, the people (and the quiz, when it's
  //one: Assign gives one quiz at a time) (the owner, 2026-10-15)
  var fullLink = dialog.querySelector('[data-full-assign]');
  if (fullLink) fullLink.addEventListener('click', function (e) {
    e.preventDefault();
    var q = new URLSearchParams();
    var quizzes = Array.prototype.map.call(dialog.querySelectorAll('[data-quiz-items] input[name=items]'), function (i) { return i.value; });
    if (quizzes.length === 1) q.set('vq', quizzes[0]);
    boxes.forEach(function (b) { if (b.checked) q.append('users', b.value); });
    var n = dialog.querySelector('input[name="next"]');
    if (n && n.value) q.set('next', n.value);
    location.href = fullLink.getAttribute('href').split('?')[0] + (q.toString() ? '?' + q.toString() : '');
  });
  dialog.querySelector('form').addEventListener('submit', function (e) {
    if (!boxes.some(function (b) { return b.checked; })) { e.preventDefault(); error.hidden = false; }
    if (!e.defaultPrevented && fromBar && window.qgenCheckedClear) window.qgenCheckedClear();  // (the checked ones done: nothing stays checked)
  });
  var fromBar = false;  // (opened by the checked bar's button, not one row's)
  function open(ids, what, fullUrl) {
    if (!ids.length) return;
    dialog.querySelector('[data-what]').textContent = what;
    var next = dialog.querySelector('input[name="next"]');
    if (next) next.value = location.pathname + location.search;
    var full = dialog.querySelector('[data-full-assign]');
    if (full && fullUrl) full.href = fullUrl;
    var holder = dialog.querySelector('[data-quiz-items]');
    holder.innerHTML = '';
    ids.forEach(function (id) {
      var i = document.createElement('input');
      i.type = 'hidden'; i.name = 'items'; i.value = id;
      holder.appendChild(i);
    });
    sync();
    dialog.showModal();
  }
  if (btn) btn.addEventListener('click', function () {
    var ids = checkedQuizzes();
    fromBar = true;
    open(ids, ids.length === 1 ? 'the checked quiz' : 'the ' + ids.length + ' checked quizzes',
         ids.length === 1 ? '/quiz/assign?vq=' + ids[0] : null);
  });
  //one quiz's paper plane (a link to Assign with ?vq=): just that quiz
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href*="/quiz/assign?"]');
    if (!a || a.closest('dialog') || e.ctrlKey || e.metaKey || e.shiftKey) return;
    var vq = new URL(a.href, location.href).searchParams.get('vq');
    if (!vq) return;
    e.preventDefault();
    fromBar = false;
    open([vq], a.dataset.what || 'this quiz', a.href);
  });
})();
