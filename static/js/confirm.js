/* "Are you sure?" questions shown inside the page, not with the browser's own
 * confirm() pop-up: browsers let people switch those off ("prevent this page from
 * creating additional dialogs"), after which every confirm() silently answers no
 * and buttons seem to do nothing.
 *
 * Any form with data-confirm="question" asks first (data-confirm-ok names the
 * button, e.g. "Delete"). Scripts can call qgenAsk(question, okLabel, danger, cancelLabel),
 * which resolves to true or false.
 *
 * Messages that need no answer ("That didn't work...") use qgenSay(text, kind): the same
 * floating message as the page's own (kind: 'success', 'warning' or 'error'), which fades
 * after a few seconds or goes when clicked; never the browser's alert() pop-up. */
(function () {
  var box = null;

  function build() {
    box = document.createElement('dialog');
    box.className = 'ask';
    box.setAttribute('aria-labelledby', 'ask-text');
    //(the answer first, Cancel last, as in every dialog: the owner, 2026-10-23; the focus stays on Cancel, the safe one)
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
    //(every caller names the action; "Yes" only if one ever doesn't: buttons never say "OK",
    //the code critic 2026-10-20)
    ok.textContent = okLabel || 'Yes';
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

  /* qgenChoose(question, choices): the same question box with several answers, each
   * {value, label, title, danger, disabled: why it can't be chosen}, and Cancel first (with the focus). Resolves to the value
   * chosen, or null for Cancel or Esc. */
  var many = null;
  window.qgenChoose = function (question, choices) {
    //(no dialog in this browser: OK means the first choice that isn't a danger, never a delete)
    if (!window.HTMLDialogElement) {
      var safe = choices.filter(function (c) { return !c.danger && !c.disabled; })[0];
      return Promise.resolve(safe && window.confirm(question + '\n\nOK: ' + safe.label) ? safe.value : null);
    }
    if (!many) {
      many = document.createElement('dialog');
      many.className = 'ask ask-many';
      many.setAttribute('aria-labelledby', 'choose-text');
      many.innerHTML = '<p id="choose-text"></p><div class="btn-row"></div>';
      document.body.appendChild(many);
    }
    many.querySelector('#choose-text').textContent = question;
    var row = many.querySelector('.btn-row');
    row.textContent = '';
    return new Promise(function (resolve) {
      function done(v) { many.removeEventListener('cancel', esc); if (many.open) many.close(); resolve(v); }
      function esc(e) { e.preventDefault(); done(null); }
      //(the answers first, Cancel last: the owner, 2026-10-23)
      choices.concat([{ value: null, label: 'Cancel', title: 'Don\'t do it; nothing changes' }]).forEach(function (c) {
        var b = document.createElement('button');
        b.type = 'button';
        //(only a dangerous answer is filled in: the others are plain, like Cancel)
        b.className = 'btn' + (c.danger ? ' btn-danger' : ' btn-secondary');
        b.textContent = c.label;
        if (c.title) b.title = c.title;
        if (c.disabled) { b.disabled = true; b.title = c.disabled; }  // (grayed, with why)
        b.addEventListener('click', function () { done(c.value); });
        row.appendChild(b);
      });
      many.addEventListener('cancel', esc);
      many.showModal();
      row.lastChild.focus();  // (Cancel)
    });
  };

  //"Start over" / "Undo changes" on the problem and quiz editors: after asking, the page
  //opens again as it was (data-start-over: its address)
  document.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('[data-start-over]');
    if (!btn) return;
    window.qgenAsk(btn.dataset.ask, btn.dataset.ok, true).then(function (yes) {
      if (!yes) return;
      document.dispatchEvent(new CustomEvent('qgen-start-over'));  // (static/js/quiz_pick.js keeps nothing)
      location.replace(btn.dataset.startOver);
    });
  });

  //runs before other submit handlers (e.g. the side panels' own sending)
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form.dataset || !form.dataset.confirm) return;
    if (form.dataset.confirmed === '1') { delete form.dataset.confirmed; return; }
    e.preventDefault();
    e.stopImmediatePropagation();
    //(asked from a pop-over, Folder options' "Delete folder": the pop-over closes first, so it isn't
    //left open behind the question; the owner, 2026-10-22)
    var pop = form.closest('details.folder-tools[open]');
    if (pop) pop.open = false;
    var submitter = e.submitter;
    //(no data-confirm-ok: the button that was pressed names the action, its words or its
    //tooltip's first part, e.g. "Archive" from "Archive: move it to the Archive")
    var own = submitter ? (submitter.getAttribute('aria-label') || (submitter.title || '').split(':')[0] || submitter.textContent || '').trim() : '';
    var label = form.dataset.confirmOk || own || 'Yes';
    window.qgenAsk(form.dataset.confirm, label, /delete|remove|clear/i.test(label)).then(function (yes) {
      if (!yes) return;
      form.dataset.confirmed = '1';
      if (form.requestSubmit) form.requestSubmit(submitter && form.contains(submitter) ? submitter : undefined);
      else form.submit();
    });
  }, true);
})();

window.qgenSay = function (text, kind) {
  var list = document.createElement('ul'), item = document.createElement('li');
  list.className = 'alerts';
  list.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  item.className = 'alert alert-' + (kind || 'error');
  item.textContent = text;
  list.appendChild(item);
  var main = document.querySelector('main') || document.body;
  main.insertBefore(list, main.firstChild);
  if (window.qgenFloat) window.qgenFloat(list);
};
