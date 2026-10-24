/* A button pressed with something needed left empty (the owner, 2026-10-24: the standard is New problem's): the field gets the red
 * outline and its message right under it in red, the first one gets the cursor, and the message goes as soon as it's filled in.
 * window.qgenFieldError(el, words) / qgenFieldOk(el) for a page's own checks; a field the browser checks (required...) shows its
 * data-error words, or the browser's own, the same way instead of the browser's bubble. */
(function () {
  //(a box with no .field around it, e.g. a dialog's name box right in its form: one is put around it, so the
  //message sits right under the box and the red outline shows)
  function holder(el) {
    var f = el.closest('.field, .pq-answer');  // (a box on a scanned page: its own spot on the page)
    if (f) return f;
    if (el.type === 'radio' || el.type === 'checkbox') return el.parentElement;
    f = document.createElement('div');
    f.className = 'field field-bare';  // (no gap of its own under the box: app.css)
    el.parentNode.insertBefore(f, el);
    f.appendChild(el);
    return f;
  }
  window.qgenFieldError = function (el, words) {
    var f = holder(el);
    f.classList.add('has-error');
    var e = f.querySelector(':scope > .error[data-said]');
    if (!e) {
      e = document.createElement('div');
      e.className = 'error';
      e.setAttribute('data-said', '');
      e.setAttribute('role', 'alert');
      f.appendChild(e);
    }
    e.textContent = words;
  };
  window.qgenFieldOk = function (el) {
    var f = holder(el);
    var e = f.querySelector(':scope > .error[data-said]');
    if (e) { e.remove(); f.classList.remove('has-error'); }
  };
  var first = null;
  document.addEventListener('invalid', function (e) {
    var el = e.target;
    e.preventDefault();  // (no bubble: the message under the field instead)
    window.qgenFieldError(el, el.dataset.error || el.validationMessage);
    if (!first) { first = el; setTimeout(function () { if (first) first.focus(); first = null; }, 0); }
  }, true);
  //(gone once there's something in it)
  function clear(e) {
    var el = e.target;
    if (!el.closest || !el.closest('.has-error')) return;
    if (el.type === 'file' ? el.files.length : String(el.value || '').trim()) window.qgenFieldOk(el);
  }
  document.addEventListener('input', clear, true);
  document.addEventListener('change', clear, true);
})();
