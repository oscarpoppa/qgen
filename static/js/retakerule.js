/* Results tables: a student's "Score counted" pencil opens "How should ava’s score on “Quiz 1”
   count?" with the choices as round buttons, Cancel / Save; Save sends the row's own small form
   (its hidden list holds the choices). Nothing changes until Save (the owner, 2026-10-19). */
(function () {
  if (!document.querySelector('[data-rule-edit]')) return;
  var box = document.createElement('dialog');
  //(a plain question box with round choices: not a folder dialog, so no filter and no folder
  //list's top buttons; the user critic, 2026-10-20)
  box.className = 'ask rule-dialog';
  box.innerHTML = '<p><strong data-head></strong></p>'
    + '<ul class="rule-list" data-list></ul>'
    + '<div class="btn-row"><button type="button" class="btn" data-ok>Save</button><button type="button" class="btn btn-secondary" data-no>Cancel</button></div>';
  document.body.appendChild(box);
  var list = box.querySelector('[data-list]');
  box.querySelector('[data-no]').addEventListener('click', function () { box.close(); });
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-rule-edit]');
    if (!b) return;
    e.preventDefault();
    var form = b.closest('form'), sel = form.querySelector('select[name=rule]'), was = sel.value;
    box.querySelector('[data-head]').textContent = b.dataset.head;
    list.innerHTML = '';
    Array.prototype.forEach.call(sel.options, function (o) {
      var li = document.createElement('li'), lab = document.createElement('label'), r = document.createElement('input');
      r.type = 'radio'; r.name = 'rule-pick'; r.value = o.value; r.checked = o.selected;
      lab.title = o.title;
      lab.appendChild(r);
      lab.appendChild(document.createTextNode(' ' + o.textContent));
      li.appendChild(lab);
      list.appendChild(li);
    });
    box.querySelector('[data-ok]').onclick = function () {
      var r = list.querySelector('input:checked');
      box.close();
      if (!r || r.value === was) return;  // (nothing changed: nothing to save)
      sel.value = r.value;
      form.dataset.inPlace = ''; (window.qgenSubmit || function (x) { x.submit(); })(form);  // (in place: static/js/inplace.js)
    };
    box.showModal();
    var on = list.querySelector('input:checked');
    if (on) on.focus();
  });
})();
