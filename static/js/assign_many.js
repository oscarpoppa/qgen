/* Assign quizzes (the owner, 2026-10-24: the Assign dialog became the Assign page): the Quizzes
 * page's checked bar opens the Assign page with the checked quizzes already checked; any one
 * quiz's paper plane is a plain link to it (?vq=). Assign comes back here when it's done. */
(function () {
  var btn = document.querySelector('[data-assign-many]');
  if (!btn) return;
  btn.addEventListener('click', function () {
    var ids = window.qgenCheckedIds ? window.qgenCheckedIds()
      : Array.prototype.map.call(document.querySelectorAll('.folder-main input[name="items"]:checked'), function (t) { return t.value; });
    if (!ids.length) return;
    var q = new URLSearchParams();
    ids.forEach(function (id) { if (q.getAll('vq').indexOf(id) === -1) q.append('vq', id); });
    if (window.qgenCheckedLeaving) window.qgenCheckedLeaving();
    location.href = '/quiz/assign?' + q.toString();
  });
})();
