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

  /* A message for the notice, kept with it in the Trash (the owner, 2026-10-29: informational, never asking why), in either
   * dialog the same way: opts {max, before} turns it on, before being the message it was moved to the Trash with. */
  var nextId = 0;
  function messageBox(dialog) {
    var m = dialog.querySelector('.ask-message');
    if (m) return m;
    var id = 'ask-message-' + (++nextId);
    m = document.createElement('div');
    m.className = 'ask-message';
    m.hidden = true;
    m.innerHTML = '<p class="ask-message-before small"></p><label class="ask-message-label" for="' + id + '">Message (Optional)</label>'
      + '<textarea id="' + id + '" rows="3"></textarea><p class="small muted ask-message-hint">Sent in the notice and kept in the Trash</p>';
    dialog.insertBefore(m, dialog.querySelector('.btn-row'));
    return m;
  }
  function setMessage(dialog, opts) {
    var m = messageBox(dialog), text = m.querySelector('textarea'), before = m.querySelector('.ask-message-before');
    m.hidden = !opts;
    text.value = '';
    if (!opts) return null;
    text.maxLength = +opts.max || 2000;
    before.hidden = !opts.before;
    before.textContent = opts.before ? 'Message from when it was moved to the Trash: ' + opts.before : '';
    return text;
  }

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

  //(message: {max, before}, the message box under the question; then it resolves to {ok, message} instead of true / false)
  window.qgenAsk = function (question, okLabel, danger, cancelLabel, message) {
    if (!window.HTMLDialogElement) {
      var yes = window.confirm(question);
      return Promise.resolve(message ? { ok: yes, message: '' } : yes);
    }
    if (!box) build();
    var typed = setMessage(box, message);
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
        resolve(message ? { ok: answer, message: answer && typed ? typed.value.trim() : '' } : answer);
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
  //(check: {label, checked}, a check box under the question (a quiz's own problems going with it: the owner, 2026-10-26);
  //then it resolves to {value, checked} instead of the value)
  //(message: {max, before}, the message box, as qgenAsk's; then it resolves to {value, checked, message})
  window.qgenChoose = function (question, choices, check, message) {
    //(no dialog in this browser: OK means the first choice that isn't a danger, never a delete)
    if (!window.HTMLDialogElement) {
      var safe = choices.filter(function (c) { return !c.danger && !c.disabled; })[0];
      var v = safe && window.confirm(question + '\n\nOK: ' + safe.label) ? safe.value : null;
      return Promise.resolve(check || message ? { value: v, checked: false, message: '' } : v);
    }
    if (!many) {
      many = document.createElement('dialog');
      many.className = 'ask ask-many';
      many.setAttribute('aria-labelledby', 'choose-text');
      many.innerHTML = '<p id="choose-text"></p><label class="check choose-check" hidden><input type="checkbox"> <span></span></label><div class="btn-row"></div>';
      document.body.appendChild(many);
    }
    many.querySelector('#choose-text').textContent = question;
    var typed = setMessage(many, message);
    var box = many.querySelector('.choose-check'), tick = box.querySelector('input');
    box.hidden = !check;
    if (check) { box.querySelector('span').textContent = check.label; tick.checked = !!check.checked; }
    var row = many.querySelector('.btn-row');
    row.textContent = '';
    return new Promise(function (resolve) {
      function done(v) {
        many.removeEventListener('cancel', esc);
        if (many.open) many.close();
        resolve(check || message ? { value: v, checked: tick.checked, message: v !== null && typed ? typed.value.trim() : '' } : v);
      }
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
    //(data-trash-message: the message box too, its words sent as trash_message; the owner, 2026-10-29)
    var msg = 'trashMessage' in form.dataset ? { max: form.dataset.trashMessage, before: form.dataset.trashMessageBefore || '' } : null;
    window.qgenAsk(form.dataset.confirm, label, /delete|remove|clear/i.test(label), undefined, msg).then(function (answer) {
      if (!(msg ? answer.ok : answer)) return;
      if (msg) {
        var field = form.querySelector('input[name="trash_message"]');
        if (!field) { field = document.createElement('input'); field.type = 'hidden'; field.name = 'trash_message'; form.appendChild(field); }
        field.value = answer.message;
      }
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

/* A student's paper pages to print (the printer on his/her row, templates/qgen/_results.html): one thing at a
 * time, and a long one asks first, "Print 14 pages?" (the owner, 2026-10-21, To do 7) */
(function () {
  var MANY = 10;
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[data-print-pages]');
    if (!a || e.ctrlKey || e.metaKey || e.shiftKey) return;
    var n = parseInt(a.dataset.printPages, 10) || 0;
    if (n <= MANY || !window.qgenAsk) return;
    e.preventDefault();
    window.qgenAsk('Print ' + n + ' pages?', 'Print').then(function (yes) { if (yes) location.href = a.href; });
  });
})();
