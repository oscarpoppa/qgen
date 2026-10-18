/* "Leave this page?": the problem editor, the quiz editor and Grading ask the browser to warn
 * before leaving with changes not saved yet (the October 7 review's bug; the owner, 2026-10-16).
 * A form marked data-unsaved counts as changed once anything in it (or anything tied to it
 * with form="...") is typed in or changed; sending it clears that. A link or button marked
 * data-keeps-form (Pick on the Problems page, which keeps what's filled in) leaves without asking. */
(function () {
  var forms = Array.prototype.slice.call(document.querySelectorAll('form[data-unsaved]'));
  if (!forms.length) return;
  var changed = false, leaving = false;
  function mine(el) {
    if (!el || !el.closest) return false;
    var f = el.form || el.closest('form');
    return forms.indexOf(f) !== -1;
  }
  document.addEventListener('input', function (e) { if (e.isTrusted && mine(e.target)) changed = true; }, true);
  document.addEventListener('change', function (e) { if (e.isTrusted && mine(e.target)) changed = true; }, true);
  document.addEventListener('submit', function (e) { if (forms.indexOf(e.target) !== -1) leaving = true; }, true);
  document.addEventListener('click', function (e) { if (e.target.closest && e.target.closest('[data-keeps-form]')) leaving = true; }, true);
  window.addEventListener('beforeunload', function (e) {
    if (!changed || leaving) return;
    e.preventDefault();
    e.returnValue = '';
  });
  window.qgenSaved = function () { changed = false; };
})();
