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
  function removeOne(form) {  // (form: the trash can button, its fields in data-*)
    var label = form.dataset.label, person = form.dataset.kind === 'people';
    var archive = form.dataset.archiveUrl;
    var q = archive ? 'What do you want to do with ' + label + '?' : 'Delete ' + label + ' for good?';
    if (form.dataset.deleteNote) q += ' ' + form.dataset.deleteNote;
    var choices = [];
    if (archive) choices.push({ value: 'archive', label: 'Move to Trash',
      title: person ? 'He/she can’t log in until you restore him/her from the Trash' : 'Off this page; you can restore it from the Trash' });
    choices.push({ value: 'delete', label: form.dataset.deleteLabel || 'Delete for good', danger: true, title: 'It can’t be undone' });
    function send(url, extra) {
      var f = document.createElement('form');
      f.method = 'post'; f.action = url; f.hidden = true;
      var token = document.createElement('input');
      token.type = 'hidden'; token.name = 'csrf_token';
      token.value = document.querySelector('meta[name=csrf-token]').content;
      f.appendChild(token);
      Object.keys(extra || {}).forEach(function (k) { var i = document.createElement('input'); i.type = 'hidden'; i.name = k; i.value = extra[k]; f.appendChild(i); });
      document.body.appendChild(f);
      f.submit();
    }
    //(a quiz: its problems no other quiz uses can go with it, checked to start: the owner, 2026-10-26)
    var own = +(form.dataset.ownProblems || 0);
    var check = own ? { label: 'Also its ' + (own === 1 ? 'problem' : own + ' problems') + ' no other quiz uses', checked: true } : null;
    window.qgenChoose(q, choices, check).then(function (got) {
      var answer = check ? got.value : got, extra = check && got.checked ? { problems: '1' } : {};
      if (answer === 'delete') { send(form.dataset.deleteUrl, extra); return; }
      if (answer !== 'archive') return;
      if (!person) { send(archive, extra); return; }
      window.qgenChoose('Move ' + label + ' to the Trash? He/she won’t be able to log in until you restore him/her. What about his/her quiz results and attempts?', [
        { value: 'yes', label: 'Keep their results', title: 'His/her attempts and scores stay, and come back with him/her' },
        { value: 'no', label: 'Delete their results', danger: true, title: 'His/her attempts and scores are deleted for good, also any in the Trash' }
      ]).then(function (keep) { if (keep) send(archive, { keep: keep }); });
    });
  }

  //(the trash can is a button with its fields on it, not a form: one per row)
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('button[data-remove-one]');
    if (b && !b.disabled) { e.preventDefault(); removeOne(b); }
  });

  //a folder badge's ✕ (span[data-chip-out]): its take-out form is made only when pressed, then
  //sent the usual way below (the owner, 2026-10-21: no form in every badge of a long list)
  document.addEventListener('click', function (e) {
    var x = e.target.closest && e.target.closest('[data-chip-out] .chip-x');
    if (!x) return;
    e.preventDefault();
    var chip = x.closest('[data-chip-out]'), form = document.createElement('form');
    chip.querySelectorAll('form').forEach(function (f) { f.remove(); });  // (one left by Cancel before)
    form.method = 'post';
    form.setAttribute('action', chip.dataset.chipOut);
    form.dataset.takeout = '';
    form.hidden = true;
    var csrf = document.querySelector('meta[name="csrf-token"]');
    [['csrf_token', csrf ? csrf.content : ''], ['view', chip.dataset.view], [chip.dataset.what, chip.dataset.ident], ['folder', chip.dataset.folder]].forEach(function (kv) {
      var i = document.createElement('input'); i.type = 'hidden'; i.name = kv[0]; i.value = kv[1]; form.appendChild(i);
    });
    //(inside the badge, so "which folder is this shown in" still finds its place on the page)
    chip.appendChild(form);
    form.requestSubmit();
  });

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form.matches || !form.matches('form[data-takeout]')) return;
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

  function chipOut(form, chip) {
    fetchJson(form.getAttribute('action'), new FormData(form)).then(function (res) {
      if (!res.ok) { window.qgenSay(res.error || 'That didn\'t work. Please reload the page and try again.', 'error'); return; }
      var fid = chip.dataset.folder, row = chip.closest('tr[data-box]') || chip.closest('[data-box]');
      var list = chip.closest('.row-folders');
      chip.remove();
      //(the "+N more" card's chips count too: static/js/chipcap.js)
      if (list && !list.querySelector('.folder-chip')) list.remove();
      if (row) {
        var fs = row.querySelector('[data-folders]');
        if (fs) { try { fs.dataset.folders = JSON.stringify(JSON.parse(fs.dataset.folders).filter(function (x) { return String(x) !== String(fid); })); } catch (err) {} }
        //(out of the folder shown: its row leaves the list, as it would after a reload)
        if (chip.dataset.view === fid) row.remove();
      }
      if (window.qgenMovedSay) window.qgenMovedSay(res.message); else window.qgenSay(res.message);
      window.qgenRefreshCounts();
    });
  }

  function send(form, sub) {
    var data = new FormData(form);
    if (sub && sub.name) data.set(sub.name, sub.value);
    data.set('check', '1');
    //(the address itself: the bar's buttons are named "action", which hides form.action)
    fetchJson(form.getAttribute('action'), data).then(function (res) {
      if (!res.ok) { window.qgenSay(res.error || 'That didn\'t work. Please reload the page and try again.', 'error'); return; }
      var go = function (choice) {
        if (choice) hidden(form, 'confirm', choice);
        //a folder chip's ✕: done here, the page left exactly as it was but for the chip (and the row, when it has left
        //the folder shown); a reload made the page jump (the owner, 2026-10-27)
        var chip = form.closest('.folder-chip');
        if (chip && window.qgenRefreshCounts) { chipOut(form, chip); return; }
        if (sub && sub.name) hidden(form, sub.name, sub.value);
        //(the checked bar's: done with the checked ones, unchecked when the page comes back; not before the
        //question is answered, so a Cancel keeps them: static/js/checked.js)
        if (form.id === 'file-form' && window.qgenCheckedForget) window.qgenCheckedForget();
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
