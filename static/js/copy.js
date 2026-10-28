/* A row's Copy icon on Problems and Quizzes (the owner, 2026-10-16): a small dialog asks the new
 * one's name ("Fractions (copy)" to begin with); Make copy makes it, in the same folders, and
 * opens it in its editor. */
(function () {
  var box = document.createElement('dialog');
  box.className = 'ask folder-dialog copy-dialog';
  box.innerHTML = '<form method="post"><input type="hidden" name="csrf_token">'
    + '<p><strong data-head></strong><br><span class="muted small" data-sub></span></p>'
    + '<label class="small" for="copy-name">Name of the copy</label>'
    + '<input type="text" id="copy-name" name="title" maxlength="64" required>'
    + '<div class="btn-row"><button class="btn" title="Make the copy and open it, to change what you like">Make Copy</button>'
    + '<button type="button" class="btn btn-secondary" data-cancel>Cancel</button></div></form>';
  document.body.appendChild(box);
  var form = box.querySelector('form'), name = box.querySelector('#copy-name');
  box.querySelector('[data-cancel]').addEventListener('click', function () { box.close(); });
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-copy-url]');
    if (!b) return;
    e.preventDefault();
    var csrf = document.querySelector('input[name=csrf_token]');
    form.action = b.dataset.copyUrl;
    form.elements.csrf_token.value = csrf ? csrf.value : '';
    var src = b.dataset.copyName || '';
    box.querySelector('[data-head]').textContent = 'Copy “' + src + '”';
    box.querySelector('[data-sub]').textContent = b.dataset.copyKind === 'quiz'
      ? 'A new quiz with the same problems and settings, in the same folders. It opens for you to change.'
      : 'A new problem with the same question, values and answer, in the same folders. It opens for you to change.';
    name.value = src.slice(0, 57) + ' (copy)';
    box.showModal();
    name.focus(); name.select();
  });
})();
