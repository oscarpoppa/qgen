/* "Are you sure?" questions shown inside the page, not with the browser's own
 * confirm() pop-up: browsers let people switch those off ("prevent this page from
 * creating additional dialogs"), after which every confirm() silently answers no
 * and buttons seem to do nothing.
 *
 * Any form with data-confirm="question" asks first (data-confirm-ok names the
 * button, e.g. "Delete"). Scripts can call qgenAsk(question, okLabel, danger, cancelLabel),
 * which resolves to true or false. */
(function () {
  var box = null;

  function build() {
    box = document.createElement('dialog');
    box.className = 'ask';
    box.setAttribute('aria-labelledby', 'ask-text');
    box.innerHTML = '<p id="ask-text"></p><div class="btn-row">'
      + '<button type="button" class="btn ask-ok"></button>'
      + '<button type="button" class="btn btn-secondary ask-cancel" title="Don\'t do it; nothing changes">Cancel</button></div>';
    document.body.appendChild(box);
  }

  window.qgenAsk = function (question, okLabel, danger, cancelLabel) {
    if (!window.HTMLDialogElement) return Promise.resolve(window.confirm(question));
    if (!box) build();
    box.querySelector('#ask-text').textContent = question;
    box.querySelector('.ask-cancel').textContent = cancelLabel || 'Cancel';
    var ok = box.querySelector('.ask-ok');
    ok.textContent = okLabel || 'OK';
    ok.title = danger ? 'Yes, go ahead; this can\'t be undone' : 'Yes, go ahead';
    ok.classList.toggle('btn-danger', !!danger);
    return new Promise(function (resolve) {
      function done(answer) {
        ok.removeEventListener('click', yes);
        box.querySelector('.ask-cancel').removeEventListener('click', no);
        box.removeEventListener('cancel', no);
        if (box.open) box.close();
        resolve(answer);
      }
      function yes() { done(true); }
      function no(e) { if (e) e.preventDefault(); done(false); }
      ok.addEventListener('click', yes);
      box.querySelector('.ask-cancel').addEventListener('click', no);
      box.addEventListener('cancel', no);  // Esc
      box.showModal();
      //the safe choice has the focus, so Enter doesn't delete by accident
      box.querySelector('.ask-cancel').focus();
    });
  };

  //"Start over" / "Undo changes" on the problem and quiz editors: after asking, the page
  //opens again as it was (data-start-over: its address)
  document.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('[data-start-over]');
    if (!btn) return;
    window.qgenAsk(btn.dataset.ask, btn.dataset.ok, true).then(function (yes) {
      if (yes) location.replace(btn.dataset.startOver);
    });
  });

  //runs before other submit handlers (e.g. the side panels' own sending)
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form.dataset || !form.dataset.confirm) return;
    if (form.dataset.confirmed === '1') { delete form.dataset.confirmed; return; }
    e.preventDefault();
    e.stopImmediatePropagation();
    var label = form.dataset.confirmOk || 'Yes';
    var submitter = e.submitter;
    window.qgenAsk(form.dataset.confirm, label, /delete|remove|clear/i.test(label)).then(function (yes) {
      if (!yes) return;
      form.dataset.confirmed = '1';
      if (form.requestSubmit) form.requestSubmit(submitter && form.contains(submitter) ? submitter : undefined);
      else form.submit();
    });
  }, true);
})();
