/* People: Assign quizzes (the owner, 2026-10-24: the dialog became the Assign page). The checked
 * bar's button opens the Assign page with the checked people already checked; a person's, a
 * folder's or All's paper plane is a plain link to it (?users=, ?folder=). Assign comes back
 * here when it's done. */
(function () {
  var bar = document.querySelector('[data-assign-checked]');
  if (!bar) return;
  bar.addEventListener('click', function () {
    var ids = {};
    //(everyone checked, in other folders too: static/js/checked.js)
    if (window.qgenCheckedIds) window.qgenCheckedIds().forEach(function (id) { ids[id] = 1; });
    else document.querySelectorAll('input.pick-person:checked').forEach(function (b) { ids[b.value] = 1; });
    var list = Object.keys(ids);
    if (!list.length) return;
    if (window.qgenCheckedLeaving) window.qgenCheckedLeaving();
    location.href = '/quiz/assign?' + list.map(function (id) { return 'users=' + encodeURIComponent(id); }).join('&');
  });
})();
