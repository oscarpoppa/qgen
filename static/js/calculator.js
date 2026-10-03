/* The on-screen calculator on quizzes marked "Calculator allowed": a small window over
 * the quiz that can be moved, typed into or clicked. It works everything out here in the
 * browser (nothing is sent anywhere), and "Use in answer" puts the result in the answer
 * box the student was last in.
 *
 * It understands + − × ÷, powers (^, ²), √, π, percent, parentheses, sin/cos/tan in
 * degrees, and Ans (the last result). 2π and 3(4 + 1) multiply. */
(function () {
  /* ---------- working it out (no eval: a small parser of its own) ---------- */

  function CalcError(msg) { this.msg = msg; }
  var FUNCS = {
    sin: function (d) { return trig(Math.sin(d * Math.PI / 180)); },
    cos: function (d) { return trig(Math.cos(d * Math.PI / 180)); },
    tan: function (d) {
      var c = Math.cos(d * Math.PI / 180);
      if (Math.abs(c) < 1e-12) throw new CalcError('tan of ' + format(d) + '° has no value');
      return trig(Math.tan(d * Math.PI / 180));
    },
    sqrt: root
  };
  //sin 30 is exactly 0.5, not 0.49999999999999994
  function trig(v) { return Math.round(v * 1e12) / 1e12; }
  function root(v) {
    if (v < 0) throw new CalcError('Can\'t take the square root of a negative number');
    return Math.sqrt(v);
  }

  function tokenize(text) {
    var s = text.replace(/[×✕]/g, '*').replace(/÷/g, '/').replace(/[−–]/g, '-'), out = [], i = 0, m;
    while (i < s.length) {
      var rest = s.slice(i), c = s[i];
      if (/\s/.test(c)) { i++; continue; }
      if ((m = /^(\d+\.?\d*|\.\d+)(e[+-]?\d+)?/i.exec(rest))) {
        out.push({ t: 'num', v: parseFloat(m[0]), written: true }); i += m[0].length; continue;
      }
      if ((m = /^[a-z]+/i.exec(rest))) {
        var w = m[0].toLowerCase();
        if (FUNCS[w]) out.push({ t: 'func', v: w });
        else if (w === 'pi') out.push({ t: 'num', v: Math.PI });
        else if (w === 'ans') out.push({ t: 'ans' });
        else if (w[0] === 'x') { out.push({ t: 'op', v: '*' }); i += 1; continue; }  // 2x3
        else throw new CalcError('“' + m[0] + '” isn\'t something the calculator knows');
        i += w.length; continue;
      }
      if (c === 'π') out.push({ t: 'num', v: Math.PI });
      else if (c === '√') out.push({ t: 'func', v: 'sqrt' });
      else if ('+-*/^()%²³'.indexOf(c) >= 0) out.push({ t: 'op', v: c });
      else throw new CalcError('“' + c + '” isn\'t something the calculator knows');
      i++;
    }
    return out;
  }

  function evaluate(text, ans) {
    var toks = tokenize(text), pos = 0;
    if (!toks.length) throw new CalcError('');
    function peek() { return toks[pos]; }
    function isOp(v) { var k = peek(); return k && k.t === 'op' && k.v === v; }
    function startsValue(k) { return k && (k.t === 'num' || k.t === 'ans' || k.t === 'func' || (k.t === 'op' && k.v === '(')); }

    function expr() {
      var v = term();
      while (isOp('+') || isOp('-')) { var op = toks[pos++].v, r = term(); v = op === '+' ? v + r : v - r; }
      return v;
    }
    function term() {
      var v = unary();
      for (;;) {
        if (isOp('*')) { pos++; v *= unary(); }
        else if (isOp('/')) {
          pos++;
          var d = unary();
          if (d === 0) throw new CalcError('Can\'t divide by zero');
          v /= d;
        }
        //written side by side: 2π, 3(4+1), (2)(3), 2√9 (but not two plain numbers like 2 3)
        else if (startsValue(peek()) && !(peek().written && toks[pos - 1].written)) v *= unary();
        else return v;
      }
    }
    function unary() {
      if (isOp('-')) { pos++; return -unary(); }
      if (isOp('+')) { pos++; return unary(); }
      return power();
    }
    function power() {
      var v = postfix();
      if (isOp('^')) { pos++; v = Math.pow(v, unary()); }  // 2^3^2 = 2^9, 2^-1 = 0.5
      return v;
    }
    function postfix() {
      var v = primary();
      for (;;) {
        if (isOp('²')) { pos++; v = v * v; }
        else if (isOp('³')) { pos++; v = v * v * v; }
        else if (isOp('%')) { pos++; v = v / 100; }
        else return v;
      }
    }
    function primary() {
      var k = toks[pos++];
      if (!k) throw new CalcError('Something is missing at the end');
      if (k.t === 'num') return k.v;
      if (k.t === 'ans') {
        if (ans === null || ans === undefined) throw new CalcError('There\'s no answer yet to use as Ans');
        return ans;
      }
      if (k.t === 'func') return FUNCS[k.v](unary());  // sin 30, sin(30), sin -30, √9, √(2+7)
      if (k.t === 'op' && k.v === '(') {
        var v = expr();
        if (isOp(')')) pos++;  // a missing ) at the very end is forgiven
        else if (pos < toks.length) throw new CalcError('A bracket is missing');
        return v;
      }
      throw new CalcError(k.v === ')' ? 'There\'s a ) without its (' : 'Something is missing before “' + k.v + '”');
    }

    var v = expr();
    if (pos < toks.length) throw new CalcError(isOp(')') ? 'There\'s a ) without its (' : 'Something doesn\'t fit near the end');
    if (!isFinite(v)) throw new CalcError('That number is too big to work out');
    return v;
  }

  //at most 10 significant digits, no trailing zeros, no "e" until the number is enormous
  function format(v) {
    if (v === 0) return '0';
    var a = Math.abs(v);
    if (a >= 1e15 || a < 1e-9) return v.toPrecision(10).replace(/\.?0+e/, 'e');
    var s = parseFloat(v.toPrecision(10)).toString();
    if (/e/.test(s)) s = parseFloat(v.toPrecision(10)).toFixed(12).replace(/\.?0+$/, '');
    return s;
  }

  window.qgenCalc = { evaluate: evaluate, format: format, CalcError: CalcError };
  if (typeof document === 'undefined') return;

  /* ---------- the window ---------- */

  var open = document.getElementById('calc-open');
  var panel = document.getElementById('calc');
  if (!open || !panel) return;
  var input = panel.querySelector('.calc-input'), out = panel.querySelector('.calc-result');
  var useBtn = panel.querySelector('.calc-use'), note = panel.querySelector('.calc-note');
  var ans = null, done = false, lastBox = null;

  function store(k, v) { try { sessionStorage.setItem(k, v); } catch (e) {} }
  function stored(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } }

  function show(yes) {
    panel.hidden = !yes;
    open.setAttribute('aria-expanded', yes ? 'true' : 'false');
    store('qgen-calc-open', yes ? '1' : '');
    if (yes) { keepOnScreen(); input.focus(); }
  }
  open.addEventListener('click', function () { show(panel.hidden); });
  panel.querySelector('.calc-close').addEventListener('click', function () { show(false); open.focus(); });
  panel.addEventListener('keydown', function (e) { if (e.key === 'Escape') { show(false); open.focus(); } });

  //the answer box the student was last in (typed answers only)
  document.addEventListener('focusin', function (e) {
    var t = e.target;
    if (t.matches && t.matches('#take-form input[type=text]:not([disabled]):not([readonly]), #take-form input:not([type]):not([disabled])')) {
      lastBox = t;
      note.textContent = '';
    }
  });

  //as it's typed: the result so far (quietly nothing while it's unfinished)
  function preview() {
    note.textContent = '';
    try { out.textContent = '= ' + format(evaluate(input.value, ans)); out.classList.remove('calc-error'); }
    catch (e) { out.textContent = ''; }
  }
  function equals() {
    try {
      var v = evaluate(input.value, ans);
      ans = v;
      out.textContent = '= ' + format(v);
      out.classList.remove('calc-error');
      done = true;
    } catch (e) {
      if (!(e instanceof CalcError)) throw e;
      out.textContent = e.msg || '';
      out.classList.add('calc-error');
    }
  }

  //after =, an operator carries on from the answer; anything else starts a new calculation
  function insert(text) {
    if (done) {
      if (/^[+\-*/^²³%×÷−]/.test(text)) input.value = 'Ans';
      else input.value = '';
      input.setSelectionRange(input.value.length, input.value.length);
      done = false;
    }
    var start = input.selectionStart, end = input.selectionEnd;
    input.value = input.value.slice(0, start) + text + input.value.slice(end);
    input.setSelectionRange(start + text.length, start + text.length);
    preview();
  }

  panel.addEventListener('mousedown', function (e) { if (e.target.closest('.calc-keys button')) e.preventDefault(); });
  panel.querySelector('.calc-keys').addEventListener('click', function (e) {
    var b = e.target.closest('button');
    if (!b) return;
    input.focus();
    var k = b.dataset.key;
    if (k === '=') equals();
    else if (k === 'clear') { input.value = ''; out.textContent = ''; done = false; }
    else if (k === 'back') {
      done = false;
      var s = input.selectionStart, en = input.selectionEnd;
      if (s !== en) input.value = input.value.slice(0, s) + input.value.slice(en);
      else if (s > 0) { input.value = input.value.slice(0, s - 1) + input.value.slice(s); s--; }
      input.setSelectionRange(s, s);
      preview();
    }
    else insert(k);
  });
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); equals(); return; }
    //typing straight after =: same rule as the keys
    if (done && e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); insert(e.key); }
  });
  input.addEventListener('input', function () { done = false; preview(); });

  function result() {
    try { return format(evaluate(input.value, ans)); } catch (e) { return null; }
  }
  useBtn.addEventListener('click', function () {
    var r = result();
    if (r === null) { note.textContent = 'Work something out first.'; return; }
    if (!lastBox || !document.contains(lastBox)) { note.textContent = 'Click in an answer box first, then press this.'; return; }
    lastBox.value = r;
    lastBox.dispatchEvent(new Event('input', { bubbles: true }));  // counted and saved like typing
    note.textContent = 'Put ' + r + ' in your answer.';
  });
  panel.querySelector('.calc-copy').addEventListener('click', function () {
    var r = result();
    if (r === null) { note.textContent = 'Work something out first.'; return; }
    var said = function () { note.textContent = 'Copied ' + r + '.'; };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(r).then(said, function () {});
  });

  /* moving it by its title bar; kept on screen, and where it was after a reload */
  var head = panel.querySelector('.calc-head');
  function place(x, y) {
    var w = panel.offsetWidth, h = panel.offsetHeight;
    x = Math.max(4, Math.min(window.innerWidth - w - 4, x));
    y = Math.max(4, Math.min(window.innerHeight - h - 4, y));
    panel.style.left = x + 'px'; panel.style.top = y + 'px';
    panel.style.right = 'auto'; panel.style.bottom = 'auto';
    return [x, y];
  }
  function keepOnScreen() {
    if (panel.style.left) place(parseFloat(panel.style.left), parseFloat(panel.style.top));
  }
  head.addEventListener('pointerdown', function (e) {
    if (e.button !== 0 || e.target.closest('button')) return;
    e.preventDefault();
    var r = panel.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top;
    head.setPointerCapture(e.pointerId);
    function move(ev) { place(ev.clientX - dx, ev.clientY - dy); }
    function up() {
      head.removeEventListener('pointermove', move);
      head.removeEventListener('pointerup', up);
      head.removeEventListener('pointercancel', up);
      store('qgen-calc-at', parseFloat(panel.style.left) + ',' + parseFloat(panel.style.top));
    }
    head.addEventListener('pointermove', move);
    head.addEventListener('pointerup', up);
    head.addEventListener('pointercancel', up);
  });
  window.addEventListener('resize', keepOnScreen);

  var at = (stored('qgen-calc-at') || '').split(',');
  if (at.length === 2 && !window.matchMedia('(max-width: 640px)').matches) {
    panel.hidden = false;
    place(+at[0], +at[1]);
    panel.hidden = true;
  }
  if (stored('qgen-calc-open') === '1') { panel.hidden = false; open.setAttribute('aria-expanded', 'true'); keepOnScreen(); }
})();
