/* People: every Assign a quiz opens a dialog to pick the quizzes, instead of going to the
 * Assign page (the owner, 2026-10-15): the checked bar's button (the checked people), a
 * person's paper plane (that person), a folder's (everyone in it), All's (every student).
 * The quizzes are given at once (/quiz/assignmany), and the page comes back as it was. */
(function () {
  var dialog = document.getElementById('assign-people-dialog');
  if (!dialog) return;
  var folders = {};
  try { folders = JSON.parse(document.getElementById('person-folders').textContent); } catch (e) {}
  //(the quizzes: the standard picker, folder list and filter, static/js/folderfilter.js and
  //filter.js; Check all shown / Uncheck all here: the owner, 2026-10-19)
  var items = Array.prototype.slice.call(dialog.querySelectorAll('#assign-people-pick tr[data-box]'));
  var boxes = items.map(function (li) { return li.querySelector('input'); });
  var count = dialog.querySelector('[data-pick-count]');
  var error = dialog.querySelector('[data-pick-error]'), full = dialog.querySelector('[data-full-assign]');
  function shownNow(li) { return !li.hidden && !li.closest('[hidden]'); }
  var all = dialog.querySelector('[data-quizzes="all"]'), none = dialog.querySelector('[data-quizzes="none"]');
  if (all) all.addEventListener('click', function () { items.forEach(function (li, i) { if (shownNow(li)) boxes[i].checked = true; }); sync(); });
  if (none) none.addEventListener('click', function () { boxes.forEach(function (b) { b.checked = false; }); sync(); });

  function nameOf(id) {
    var el = document.querySelector('input.pick-person[value="' + id + '"]');
    var card = el && el.closest('.person-card, tr[data-box]');
    return card ? card.querySelector('.box-title').textContent.trim() : '';
  }
  function sync() {
    var n = boxes.filter(function (b) { return b.checked; }).length;
    count.textContent = n + ' checked';
    if (n) error.hidden = true;
  }
  dialog.addEventListener('change', sync);
  dialog.querySelector('[data-cancel]').addEventListener('click', function () { dialog.close(); });
  //"open it": the Assign page with these people, and the quiz checked here when it's one
  //(Assign gives one quiz at a time) (the owner, 2026-10-15)
  if (full) full.addEventListener('click', function (e) {
    e.preventDefault();
    var q = new URLSearchParams();
    Array.prototype.forEach.call(dialog.querySelectorAll('[data-users] input[name=users]'), function (i) { q.append('users', i.value); });
    var quizzes = boxes.filter(function (b) { return b.checked; });
    if (quizzes.length === 1) q.set('vq', quizzes[0].value);
    var n = dialog.querySelector('input[name="next"]');
    if (n && n.value) q.set('next', n.value);
    location.href = full.getAttribute('href').split('?')[0] + '?' + q.toString();
  });
  dialog.querySelector('form').addEventListener('submit', function (e) {
    if (!boxes.some(function (b) { return b.checked; })) { e.preventDefault(); error.hidden = false; }
    if (!e.defaultPrevented && fromBar && window.qgenCheckedClear) window.qgenCheckedClear();  // (the checked ones done: nothing stays checked)
  });
  var fromBar = false;  // (opened by the checked bar's button, not one row's)
  function open(ids, who, fullUrl) {
    if (!ids.length) return;
    dialog.querySelector('[data-who]').textContent = who;
    var holder = dialog.querySelector('[data-users]');
    holder.innerHTML = '';
    ids.forEach(function (id) {
      var i = document.createElement('input');
      i.type = 'hidden'; i.name = 'users'; i.value = id;
      holder.appendChild(i);
    });
    dialog.querySelector('input[name="next"]').value = location.pathname + location.search;
    if (full && fullUrl) full.href = fullUrl;
    sync();
    dialog.showModal();
  }
  function whoOf(ids) {
    if (ids.length === 1) return nameOf(ids[0]) || '1 person';
    return ids.length + ' people';
  }
  //the checked bar's button
  var bar = document.querySelector('[data-assign-checked]');
  if (bar) bar.addEventListener('click', function () {
    var ids = {};
    //(everyone checked, in other folders too: static/js/checked.js)
    if (window.qgenCheckedIds) window.qgenCheckedIds().forEach(function (id) { ids[id] = 1; });
    else document.querySelectorAll('input.pick-person:checked').forEach(function (b) { ids[b.value] = 1; });
    var list = Object.keys(ids);
    fromBar = true;
    open(list, 'the ' + (list.length === 1 ? 'checked person, ' + nameOf(list[0]) : list.length + ' checked people'),
         '/quiz/assign?' + list.map(function (id) { return 'users=' + id; }).join('&'));
  });
  //every other Assign a quiz on the page (a person's, a folder's, All's): a link to the Assign
  //page naming the people (users=) or a folder (folder=)
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href*="/quiz/assign?"]');
    if (!a || a.closest('dialog') || e.ctrlKey || e.metaKey || e.shiftKey) return;
    var u = new URL(a.href, location.href), ids = u.searchParams.getAll('users'), f = u.searchParams.get('folder'), who;
    if (f) {
      ids = Object.keys(folders).filter(function (id) { return (' ' + folders[id] + ' ').indexOf(' ' + f + ' ') !== -1; });
      //(its name: from its tab, else the folder list down the side)
      var tab = document.querySelector('.folder-filter-rows .folder-tab[data-folder="' + f + '"] .box-title')
        || document.querySelector('.folder-side .side-row[data-drop="' + f + '"] .side-link');
      who = 'everyone in “' + (tab ? tab.textContent.trim() : 'this folder') + '” (' + ids.length + ')';
    } else who = a.dataset.what || whoOf(ids);
    if (!ids.length || u.searchParams.get('vq')) return;
    e.preventDefault();
    fromBar = false;
    open(ids, who, a.href);
  });
})();
