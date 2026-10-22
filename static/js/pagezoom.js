/* A scanned page's small picture (templates/_page_thumbs.html): a click shows the page large in a
 * pop-over over the page; Esc, its ✕ or a click outside it closes it (the owner, 2026-10-19). */
(function () {
  if (window.qgenPageZoom) return;
  window.qgenPageZoom = true;
  var dlg = null;
  function box() {
    if (dlg) return dlg;
    dlg = document.createElement('dialog');
    dlg.className = 'page-zoom';
    var x = document.createElement('button');
    x.type = 'button';
    x.className = 'page-zoom-x btn btn-secondary btn-sm btn-icon';
    x.title = 'Close';
    x.setAttribute('aria-label', 'Close');
    x.textContent = '✕';
    x.addEventListener('click', function () { dlg.close(); });
    dlg.appendChild(x);
    dlg.appendChild(document.createElement('div')).className = 'page-zoom-body';
    //(a click outside the page closes it)
    dlg.addEventListener('click', function (e) { if (e.target === dlg) dlg.close(); });
    document.body.appendChild(dlg);
    return dlg;
  }
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[data-page-zoom]');
    if (!a || e.ctrlKey || e.metaKey || e.shiftKey) return;
    e.preventDefault();
    var d = box(), body = d.querySelector('.page-zoom-body');
    body.textContent = '';
    //the same page, its left-out questions covered, only bigger; else (a scan's page thumbnail:
    //the owner, 2026-10-22) the picture it links to
    var paper = a.querySelector('.page-thumb-paper');
    if (paper) body.appendChild(paper.cloneNode(true));
    else {
      var img = document.createElement('img');
      img.src = a.href; img.alt = a.title || '';
      img.className = 'page-zoom-img';
      body.appendChild(img);
    }
    d.setAttribute('aria-label', a.title);
    d.showModal();
  });
})();
