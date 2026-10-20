/* Taking things out of a folder, the same on every folder page (app/takeout.py): every form
 * marked data-takeout (a folder chip's ✕, "Take out of folder" on the checked bar, a card's
 * the checked bar's "Take out of folder") first asks the site what would happen (check=1); a
 * row's or card's "Remove" (data-remove-one) asks one question of its own (removeOne). Something that would be left
 * in no folder goes to Uncategorized; before anything is done, a dialog says where each will
 * go ("ava will go to “Alpha”.") with OK and Cancel (the owner, 2026-10-15). Deleting is
 * only Remove's (removeOne), never taking out.
 */
(function () {
  //the folder something is shown in: a folder tab's choice ("self:7" is folder 7's own), else
  //the folder box it sits in
  window.qgenShownFolder = function (el) {
    //(a form outside the list, e.g. the checked bar: the page's own folder tabs)
    var ff = el.closest('[data-folder-filter]') || (el.closest('[data-here]') ? null : document.querySelector('[data-folder-filter][data-url-tab]'));
    if (ff && ff.dataset.shown) {
      var c = ff.dataset.shown.replace(/^self:/, '');
      return /^\d+$/.test(c) ? c : null;
    }
    var here = el.closest('[data-here]');
    return here && /^\d+$/.test(here.dataset.here) ? here.dataset.here : null;
  };

  //canDelete false: nothing left can be deleted (the question says why), so that choice is grayed
  window.qgenTakeOutChoices = function (canDelete) {
    return [{ value: 'delete', label: 'Delete for good', danger: true, title: 'Delete it (asked because it’s in no other folder)',
              disabled: canDelete === false ? 'It can’t be deleted (the question above says why)' : null },
            { value: 'uncategorized', label: 'Put in Uncategorized', title: 'Keep it, in no folder' }];
  };

  function fetchJson(url, data) {
    return fetch(url, { method: 'POST', body: data, credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) { return r.json().catch(function () { return { ok: false }; }); })
      .catch(function () { return { ok: false }; });  // (no connection: still says so)
  }

  //(a field the form already has, e.g. Remove's folder, is set; else one is added for this sending)
  function hidden(form, name, value) {
    var i = form.querySelector('input[type=hidden][name="' + name + '"]:not([data-added])') ||
            form.querySelector('input[type=hidden][name="' + name + '"][data-added]');
    if (!i) { i = document.createElement('input'); i.type = 'hidden'; i.name = name; i.dataset.added = ''; form.appendChild(i); }
    i.value = value;
  }

  //a card's or row's trash can: Move to Archive (kept there, and restorable) or Delete for good,
  //asked first (the owner, 2026-10-16; moving to a folder is the row's own Move icon). A person
  //moved to the Archive: a second question, keep their quiz results or delete them.
  function removeOne(form) {
    var label = form.dataset.label, person = form.dataset.kind === 'people';
    var archive = form.dataset.archiveUrl;
    var q = archive ? 'What do you want to do with ' + label + '?' : 'Delete ' + label + ' for good?';
    if (form.dataset.deleteNote) q += ' ' + form.dataset.deleteNote;
    var choices = [];
    if (archive) choices.push({ value: 'archive', label: 'Move to Archive',
      title: person ? 'He/she can’t log in until you restore him/her from the Archive' : 'Off this page; you can restore it from the Archive' });
    choices.push({ value: 'delete', label: form.dataset.deleteLabel || 'Delete for good', danger: true, title: 'It can’t be undone' });
    function send(url, extra) {
      var f = document.createElement('form');
      f.method = 'post'; f.action = url; f.hidden = true;
      f.appendChild(form.querySelector('input[name=csrf_token]').cloneNode());
      Object.keys(extra || {}).forEach(function (k) { var i = document.createElement('input'); i.type = 'hidden'; i.name = k; i.value = extra[k]; f.appendChild(i); });
      document.body.appendChild(f);
      f.submit();
    }
    window.qgenChoose(q, choices).then(function (answer) {
      if (answer === 'delete') { send(form.dataset.deleteUrl); return; }
      if (answer !== 'archive') return;
      if (!person) { send(archive); return; }
      window.qgenChoose('Move ' + label + ' to the Archive? He/she won’t be able to log in until you restore him/her. What about his/her quiz results and attempts?', [
        { value: 'yes', label: 'Keep their results', title: 'His/her attempts and scores stay, and come back with him/her' },
        { value: 'no', label: 'Delete their results', danger: true, title: 'His/her attempts and scores are deleted for good, also any in the Archive' }
      ]).then(function (keep) { if (keep) send(archive, { keep: keep }); });
    });
  }

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form.matches || !form.matches('form[data-takeout]')) return;
    if ('removeOne' in form.dataset) { e.preventDefault(); e.stopImmediatePropagation(); removeOne(form); return; }
    var sub = e.submitter;
    //(both of the bar's buttons) the checked bar: everyone checked (data-takeout-items: which check boxes)
    if (form.dataset.takeoutItems) {
      form.querySelectorAll('input[data-added][name=items]').forEach(function (i) { i.remove(); });
      var seen = {};
      document.querySelectorAll(form.dataset.takeoutItems).forEach(function (b) {
        if (seen[b.value]) return;
        seen[b.value] = 1;
        var i = document.createElement('input'); i.type = 'hidden'; i.name = 'items'; i.value = b.value; i.dataset.added = '';
        form.appendChild(i);
      });
    }
    //the checked bar's other button (Put in folder) goes straight through
    if (form.dataset.takeout === 'remove' && !(sub && sub.name === 'action' && sub.value === 'remove')) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    clean(form);
    send(form, sub);
  }, true);

  //added fields never outlive one sending (a page brought back with the browser's Back button
  //must ask again)
  function clean(form) { form.querySelectorAll('input[data-added]').forEach(function (i) { if (i.name !== 'items') i.remove(); }); }
  window.addEventListener('pageshow', function () {
    document.querySelectorAll('form[data-takeout]').forEach(function (form) { form.querySelectorAll('input[data-added]').forEach(function (i) { i.remove(); }); });
  });

  function send(form, sub) {
    var data = new FormData(form);
    if (sub && sub.name) data.set(sub.name, sub.value);
    data.set('check', '1');
    //(the address itself: the bar's buttons are named "action", which hides form.action)
    fetchJson(form.getAttribute('action'), data).then(function (res) {
      if (!res.ok) { window.qgenSay(res.error || 'That didn\'t work. Please reload the page and try again.', 'error'); return; }
      var go = function (choice) {
        if (choice) hidden(form, 'confirm', choice);
        if (sub && sub.name) hidden(form, sub.name, sub.value);
        form.submit();  // (no submit event: not asked again; the added fields go with it)
      };
      //(the owner, 2026-10-15: every take-out says where each will go, up to the folder this one
      //is in, else Uncategorized, and OK does it; nothing is deleted by taking it out)
      var said = (res.preview || []).join(' ');
      if (!said) { go(null); return; }
      window.qgenAsk(said, 'Take out').then(function (yes) { if (yes) go('uncategorized'); });
    });
  }

})();
