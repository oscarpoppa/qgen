/* The stash's folders on Scan workbook pages (the owner, 2026-10-23): a button with data-stash-dialog="<id>"
 * opens that dialog; its data-url becomes the form's address, data-name the folder's or scan's name in its
 * words (and the rename box), data-here the folder a scan is in now (its round button starts checked). Cancel closes. */
(function () {
  document.addEventListener('click', function (e) {
    var cancel = e.target.closest && e.target.closest('dialog.folder-dialog [data-cancel]');
    if (cancel) { cancel.closest('dialog').close(); return; }
    var b = e.target.closest && e.target.closest('[data-stash-dialog]');
    if (!b) return;
    var d = document.getElementById(b.dataset.stashDialog);
    if (!d) return;
    var form = d.querySelector('form');
    if (b.dataset.url) form.action = b.dataset.url;
    d.querySelectorAll('[data-stash-name]').forEach(function (el) { el.textContent = b.dataset.name || ''; });
    var text = d.querySelector('input[name="name"]');
    if (text && b.dataset.name !== undefined) text.value = b.dataset.name;
    var here = d.querySelector('input[name="to"][value="' + (b.dataset.here || '') + '"]');
    if (b.dataset.here !== undefined && here) here.checked = true;
    d.showModal();
    if (text) { text.focus(); text.select(); }
  });
})();
