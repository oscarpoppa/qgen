/* A problem's question and answer in a dialog (the owner, 2026-10-21): the row icon marked data-qa
 * (Problems) shows one example student's version of it (data-qa: its address, routes.vprob_example),
 * numbers filled in as View shows them, in one shared dialog. */
(function () {
  var box = null;
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function build() {
    box = document.createElement('dialog');
    box.className = 'ask qa-dialog';
    box.setAttribute('aria-labelledby', 'qa-title');
    box.innerHTML = '<h2 id="qa-title" class="qa-title"></h2><div class="qa-body" aria-live="polite"></div>'
      + '<div class="btn-row"><button type="button" class="btn btn-secondary qa-close" title="Close this">Close</button></div>';
    box.querySelector('.qa-close').addEventListener('click', function () { box.close(); });
    box.addEventListener('click', function (e) { if (e.target === box) box.close(); });  // (a click outside it)
    document.body.appendChild(box);
  }
  function show(body, d) {
    body.textContent = '';
    if (!d.ok) { body.appendChild(el('p', 'error', d.error || 'This problem couldn’t be shown.')); return; }
    body.appendChild(el('h3', 'qa-head', 'Question'));
    body.appendChild(el('p', 'qa-text', d.text || '—'));
    if (d.look) return;
    body.appendChild(el('h3', 'qa-head', 'Answer'));
    if (d.choices.length) {
      var ul = el('ul', 'qa-choices');
      d.choices.forEach(function (c, i) {
        var right = d.right.indexOf(i) !== -1, li = el('li', right ? 'qa-right' : '');
        li.appendChild(el('span', 'qa-mark', right ? '✓' : '○'));
        li.appendChild(document.createTextNode(' ' + c));
        if (right) li.appendChild(el('span', 'sr-only', ' (correct)'));
        ul.appendChild(li);
      });
      body.appendChild(ul);
    } else if (d.graded_by_teacher) {
      body.appendChild(el('p', 'qa-text', 'Teacher-graded' + (d.correct ? '. Model answer: ' + d.correct : '')));
    } else body.appendChild(el('p', 'qa-text', d.correct || '—'));
    //(math in it, \( \): drawn as math)
    if (/\\\(|\\\[|\$\$/.test(body.textContent)) {
      if (window.qgenNeedMath) window.qgenNeedMath();
      var tries = 0, t = setInterval(function () {
        if (window.MathJax && MathJax.typesetPromise) { clearInterval(t); MathJax.typesetPromise([body]).catch(function () {}); }
        else if (++tries > 50) clearInterval(t);
      }, 100);
    }
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-qa]');
    if (!b) return;
    e.preventDefault();
    if (!box) build();
    box.querySelector('.qa-title').textContent = b.dataset.qaTitle || '';
    var body = box.querySelector('.qa-body');
    body.textContent = '';
    body.appendChild(el('p', 'muted small', 'Drawing an example…'));
    box.showModal();
    fetch(b.dataset.qa, { credentials: 'same-origin' }).then(function (r) { return r.json(); })
      .then(function (d) { show(body, d); })
      .catch(function () { show(body, { ok: false }); });
  });
})();
