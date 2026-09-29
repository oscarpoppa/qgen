/* Problem editor: show the fields for the chosen question type and value
 * kind, add/remove rows, "Show me 3 examples", and the AI helper. */
(function () {
  var form = document.getElementById('problem-form');
  if (!form) return;
  var qtype = form.querySelector('[name=qtype]');

  function csrf() { return document.querySelector('meta[name=csrf-token]').content; }

  /* ---------- show only what applies ---------- */

  function showType() {
    var t = qtype.value;
    form.querySelectorAll('[class*="t-"]').forEach(function (el) {
      var types = Array.prototype.filter.call(el.classList, function (c) { return c.indexOf('t-') === 0; });
      if (types.length) el.hidden = types.indexOf('t-' + t) === -1;
    });
  }

  function showKind(row) {
    var kind = row.querySelector('select.kind').value;
    row.querySelectorAll('[class*="k-"]').forEach(function (el) {
      var kinds = Array.prototype.filter.call(el.classList, function (c) { return c.indexOf('k-') === 0; });
      if (kinds.length) el.hidden = kinds.indexOf('k-' + kind) === -1;
    });
  }

  qtype.addEventListener('change', showType);
  form.addEventListener('change', function (e) {
    if (e.target.matches('select.kind')) {
      showKind(e.target.closest('.value-row'));
      //an imaginary or complex value means the problem uses complex numbers
      if (['imaginary', 'complex'].indexOf(e.target.value) !== -1) {
        var box = form.querySelector('[name=complex]');
        if (box) box.checked = true;
      }
    }
  });

  /* ---------- rows ---------- */

  var counters = {};
  function nextIndex(prefix) {
    if (counters[prefix] === undefined) {
      var max = -1;
      form.querySelectorAll('[name^="' + prefix + '-"]').forEach(function (el) {
        var m = el.name.match(new RegExp('^' + prefix + '-(\\d+)-'));
        if (m) max = Math.max(max, +m[1]);
      });
      counters[prefix] = max + 1;
    }
    return counters[prefix]++;
  }

  function fromTemplate(id, prefix) {
    var html = document.getElementById(id).innerHTML;
    var i = nextIndex(prefix);
    html = html.split(prefix + '-0-').join(prefix + '-' + i + '-');
    var box = document.createElement(prefix === 'values' ? 'tbody' : 'div');
    box.innerHTML = html.trim();
    return box.firstElementChild;
  }

  function addValue() {
    var row = fromTemplate('value-template', 'values');
    document.getElementById('values-body').appendChild(row);
    showKind(row);
    return row;
  }

  document.getElementById('add-value').addEventListener('click', function () {
    addValue().querySelector('input').focus();
  });
  document.getElementById('add-image').addEventListener('click', function () {
    var row = fromTemplate('image-template', 'images');
    document.getElementById('images-body').appendChild(row);
    if (window.qgenDropzone) window.qgenDropzone(row.querySelector('.dropzone'));
  });
  form.addEventListener('click', function (e) {
    if (e.target.closest('.remove-row')) e.target.closest('.value-row').remove();
    if (e.target.closest('.remove-image')) e.target.closest('.image-row').remove();
  });

  /* ---------- show me 3 examples ---------- */

  var preview = document.getElementById('preview');
  var previewBtn = document.getElementById('preview-btn');
  previewBtn.addEventListener('click', function () {
    previewBtn.disabled = true;
    preview.innerHTML = '<p class="muted"><span class="spinner"></span> Making examples…</p>';
    fetch(previewBtn.dataset.url, { method: 'POST', body: new FormData(form), credentials: 'same-origin' })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        preview.innerHTML = html;
        preview.scrollIntoView({ behavior: 'smooth', block: 'start' });
        if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([preview]);
      }, function () { preview.innerHTML = '<div class="alert alert-error">Couldn\'t reach the server.</div>'; })
      .then(function () { previewBtn.disabled = false; });
  });

  /* ---------- AI helper ---------- */

  function setField(name, value) {
    var el = form.querySelector('[name="' + name + '"]');
    if (!el || value === undefined || value === null) return;
    if (el.type === 'checkbox') el.checked = !!value; else el.value = value;
  }

  function formHasContent(kind) {
    var rows = Array.prototype.some.call(form.querySelectorAll('#values-body input[type=text]'), function (i) { return i.value.trim(); });
    if (kind === 'values') return rows;
    return rows || ['question', 'answer', 'choices'].some(function (n) {
      var el = form.querySelector('[name=' + n + ']'); return el && el.value.trim();
    });
  }

  function fillValues(values) {
    document.getElementById('values-body').innerHTML = '';
    (values || []).forEach(function (v) {
      var row = addValue();
      Object.keys(v).forEach(function (k) {
        var el = row.querySelector('[name$="-' + k + '"]');
        if (!el) return;
        var val = v[k];
        if (Array.isArray(val)) val = val.join(', ');
        if (el.type === 'checkbox') el.checked = !!val; else if (val !== null) el.value = val;
      });
      showKind(row);
    });
    if (!(values || []).length) addValue();
  }

  form.querySelectorAll('.ai-go').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var kind = btn.dataset.kind;
      var text = document.getElementById(btn.dataset.src).value.trim();
      var status = form.querySelector('.ai-status');
      if (!text) { status.textContent = 'Please describe what you want first.'; return; }
      if (formHasContent(kind) && !confirm('Replace what\'s already in the form?')) return;
      form.querySelectorAll('.ai-go').forEach(function (b) { b.disabled = true; });
      status.innerHTML = '<span class="spinner"></span> Thinking… this can take up to a minute.';
      fetch(btn.dataset.url, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
        body: JSON.stringify({ text: text })
      }).then(function (r) { return r.json(); }).then(function (res) {
        if (!res.ok) { status.textContent = res.error || 'Something went wrong.'; return; }
        var f = res.fill || {};
        if (kind === 'problem') {
          ['qtype', 'title', 'question', 'answer', 'choices', 'combos', 'show_n', 'grading_notes', 'case_sensitive'].forEach(function (n) { setField(n, f[n]); });
          showType();
        }
        fillValues(f.values);
        var msg = kind === 'problem' ? 'Filled in. Please check it, then press “Show me 3 examples”.' : 'Values filled in. Please check them.';
        if (res.note) msg += ' Note: ' + res.note;
        if (res.problems && res.problems.length) msg += ' Still to fix: ' + res.problems.join(' ');
        status.textContent = msg;
      }, function () { status.textContent = 'Couldn\'t reach the server. Please try again.'; })
        .then(function () { form.querySelectorAll('.ai-go').forEach(function (b) { b.disabled = false; }); });
    });
  });

  /* ---------- start ---------- */
  showType();
  form.querySelectorAll('.value-row').forEach(showKind);
})();
