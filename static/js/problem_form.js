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

  //a plain-words line under each value row saying what its kind does
  var KIND_HINTS = {
    '': 'Choose a kind to see its settings.',
    whole: 'A whole number between “from” and “to” (both included). “In steps of” 5 with 40 to 80 gives 40, 45, 50 … 80.',
    decimal: 'A number between “from” and “to” with this many decimal places (1 if empty). 1 to 10 with 2 places gives numbers like 4.37.',
    list: 'Each student gets one item from your comma-separated list. To pick 2 different items, put 2 in “how many”, then use [name1] and [name2].',
    calc: 'Worked out from other values, e.g. speed * hours. No brackets needed here. You can use + - * / ^ ( ) sqrt abs round min max.',
    imaginary: 'A number like 3i: the part in front of i is a whole number from “from” to “to”, never 0. Turns on complex numbers.',
    complex: 'A number like 2 + 3i: real part from the first range, imaginary part from the second (never 0). Turns on complex numbers.'
  };

  function showKind(row) {
    var kind = row.querySelector('select.kind').value;
    row.querySelectorAll('[class*="k-"]').forEach(function (el) {
      var kinds = Array.prototype.filter.call(el.classList, function (c) { return c.indexOf('k-') === 0; });
      if (kinds.length) el.hidden = kinds.indexOf('k-' + kind) === -1;
    });
    var hint = row.querySelector('.kind-hint');
    if (hint) hint.textContent = KIND_HINTS[kind] || '';
  }

  /* ---------- your value names as click-to-insert chips ---------- */

  var NAME = /^[A-Za-z][A-Za-z0-9_]*$/;

  //every name the values table defines, the way friendly.py counts them
  function valueNames() {
    var names = [];
    form.querySelectorAll('.value-row').forEach(function (row) {
      var raw = (row.querySelector('[name$="-name"]').value || '').trim();
      var kind = row.querySelector('select.kind').value;
      if (!raw) return;
      var parts = kind === 'list' && raw.indexOf('=') !== -1 ? raw.split('=').map(function (x) { return x.trim(); }) : [raw];
      var n = kind === 'list' ? parseInt(row.querySelector('[name$="-pick_n"]').value, 10) || 1 : 1;
      parts.forEach(function (p) {
        if (!NAME.test(p)) return;
        names.push(p);
        for (var i = 1; n > 1 && i <= n; i++) names.push(p + i);
      });
    });
    return names.filter(function (x, i) { return names.indexOf(x) === i; });
  }

  //the box a chip types into: the one last typed in, else the bar's own box
  var lastBox = null;
  form.addEventListener('focusin', function (e) {
    if (e.target.matches('[name=question], [name=answer], [name=choices], [name=combos]')) lastBox = e.target;
  });

  function renderChips() {
    var names = valueNames();
    form.querySelectorAll('.name-chips').forEach(function (bar) {
      bar.querySelectorAll('.chip').forEach(function (c) { c.remove(); });
      names.forEach(function (n) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'chip';
        b.dataset.name = n;
        b.textContent = '[' + n + ']';
        b.title = 'Insert ' + n + ' where you were typing';
        bar.appendChild(b);
      });
      bar.hidden = !names.length;
    });
  }

  function insertName(box, name) {
    //a Numeric or True/False answer is a formula: bare names, unless it already uses [placeholders]
    var bare = box.name === 'answer' && ['numeric', 'truefalse'].indexOf(qtype.value) !== -1 && box.value.indexOf('[') === -1;
    var text = bare ? name : '[' + name + ']';
    var start = box.selectionStart, end = box.selectionEnd;
    if (typeof start !== 'number') { start = end = box.value.length; }
    box.value = box.value.slice(0, start) + text + box.value.slice(end);
    box.focus();
    box.setSelectionRange(start + text.length, start + text.length);
    box.dispatchEvent(new Event('input', { bubbles: true }));
  }

  form.addEventListener('click', function (e) {
    var chip = e.target.closest('.chip');
    if (!chip) return;
    var bar = chip.closest('.name-chips');
    var own = form.querySelector('[name=' + bar.dataset.default + ']');
    var box = lastBox && !lastBox.closest('[hidden]') ? lastBox : own;
    insertName(box, chip.dataset.name);
  });
  //keep the focus (and the cursor position) in the box while clicking a chip
  form.addEventListener('mousedown', function (e) { if (e.target.closest('.chip')) e.preventDefault(); });
  form.addEventListener('input', function (e) {
    if (e.target.closest('.value-row')) renderChips();
  });

  qtype.addEventListener('change', showType);
  form.addEventListener('change', function (e) {
    if (e.target.matches('select.kind')) {
      showKind(e.target.closest('.value-row'));
      renderChips();
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
    if (e.target.closest('.remove-row')) { e.target.closest('.value-row').remove(); renderChips(); }
    if (e.target.closest('.remove-image')) e.target.closest('.image-row').remove();
  });

  /* ---------- math buttons and the math previews ---------- */

  //each button bar writes into its own box (data-target): the question (Numeric),
  //the choices (Pick one / several), or the exact form of a Numeric answer
  function mathTarget(button) {
    var bar = button.closest('.math-toolbar');
    return form.querySelector('[name="' + ((bar && bar.dataset.target) || 'question') + '"]');
  }

  //is the cursor already inside \( ... \) or \[ ... \] ?
  function insideMath(before) {
    var count = function (re) { return (before.match(re) || []).length; };
    return count(/\\\(/g) > count(/\\\)/g) || count(/\\\[/g) > count(/\\\]/g);
  }

  //"@" becomes the selected text, "¶" marks where the cursor goes (else where "@" was)
  function expand(tex, sel) {
    var out = '', cursor = -1, at = -1;
    for (var i = 0; i < tex.length; i++) {
      var ch = tex.charAt(i);
      if (ch === '@') { at = out.length; out += sel; }
      else if (ch === '¶') { cursor = out.length; }
      else out += ch;
    }
    if (!sel && at !== -1) cursor = at;
    return { text: out, cursor: cursor === -1 ? out.length : cursor };
  }

  form.addEventListener('mousedown', function (e) { if (e.target.closest('.math-btn')) e.preventDefault(); });
  form.addEventListener('click', function (e) {
    var b = e.target.closest('.math-btn');
    if (!b) return;
    var box = mathTarget(b);
    if (!box) return;
    var start = box.selectionStart, end = box.selectionEnd;
    //not typing in this box yet: add at the end
    if (typeof start !== 'number' || (document.activeElement !== box && lastBox !== box)) { start = end = box.value.length; }
    var before = box.value.slice(0, start);
    var piece = expand(b.dataset.tex, box.value.slice(start, end));
    var open = insideMath(before) ? '' : '\\( ', close = open ? ' \\)' : '';
    box.value = before + open + piece.text + close + box.value.slice(end);
    var pos = start + open.length + piece.cursor;
    box.focus();
    box.setSelectionRange(pos, pos);
    lastBox = box;
    box.dispatchEvent(new Event('input', { bubbles: true }));
  });

  //how each box's math will look (values in [brackets] show as typed)
  var HINT = 'Students will see this as typed (e.g. x^2 with a caret). To show it as math, put it between \\( and \\), or use the buttons above.';
  function showPreview(panel) {
    var box = form.querySelector('[name="' + panel.dataset.source + '"]');
    if (!box) return;
    var text = box.value, hasMath = /\\[\(\[]/.test(text);
    var body = panel.querySelector('.math-preview-body');
    if (window.MathJax && MathJax.typesetClear) MathJax.typesetClear([body]);
    //math typed without \( \) shows as plain characters: say so
    if (!hasMath && /\^|\\(sqrt|frac|pi|times|le|ge)\b/.test(text)) {
      panel.hidden = false;
      body.textContent = HINT;
      return;
    }
    panel.hidden = !hasMath;
    if (!hasMath) return;
    if (panel.dataset.source === 'choices') {
      //one choice per line, the correct ones (*) ticked
      body.textContent = text.split('\n').filter(function (l) { return l.trim(); })
        .map(function (l) { return /^\s*\*/.test(l) ? '✓ ' + l.replace(/^\s*\*\s*/, '') : '○ ' + l.trim(); }).join('\n');
    } else {
      body.textContent = text;
    }
    if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([body]).catch(function () {});
  }
  var previews = form.querySelectorAll('.math-preview[data-source]'), mathTimers = {};
  previews.forEach(function (panel) {
    var box = form.querySelector('[name="' + panel.dataset.source + '"]');
    if (!box) return;
    box.addEventListener('input', function () {
      clearTimeout(mathTimers[panel.dataset.source]);
      mathTimers[panel.dataset.source] = setTimeout(function () { showPreview(panel); }, 400);
    });
  });
  function showAllPreviews() { previews.forEach(showPreview); }
  window.addEventListener('load', function () {
    if (window.MathJax && MathJax.startup && MathJax.startup.promise) MathJax.startup.promise.then(showAllPreviews); else showAllPreviews();
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
    renderChips();
  }

  //"are you sure?" inside the page (confirm.js); the browser's own pop-ups can be switched off
  function ask(q, ok) { return window.qgenAsk ? window.qgenAsk(q, ok) : Promise.resolve(window.confirm(q)); }

  form.querySelectorAll('.ai-go').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var kind = btn.dataset.kind;
      var text = document.getElementById(btn.dataset.src).value.trim();
      var status = form.querySelector('.ai-status');
      if (!text) { status.textContent = 'Please describe what you want first.'; return; }
      if (formHasContent(kind)) {
        ask('Replace what\'s already in the form?', 'Replace').then(function (yes) { if (yes) fill(btn, kind, text, status); });
        return;
      }
      fill(btn, kind, text, status);
    });
  });

  function fill(btn, kind, text, status) {
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
  }

  /* ---------- one-click fixes from the helper panel ---------- */
  form.addEventListener('helper-action', function (e) {
    var a = e.detail;
    if (a.type === 'add_value') {
      var row = addValue();
      row.querySelector('[name$="-name"]').value = a.name;
      renderChips();
      row.querySelector('select.kind').focus();
    } else if (a.type === 'set_qtype') {
      qtype.value = a.value;
      showType();
    }
  });

  /* ---------- start ---------- */
  showType();
  form.querySelectorAll('.value-row').forEach(showKind);
  renderChips();
})();
