/* What's checked on a page with a checked bar (Problems, Quizzes, People, the Archive) is kept,
 * whatever folder is open: moving between folders (tabs, the folder list, a folder's own page,
 * Back) never loses it, and a line of chips in the bar, "Checked: “A” ✕ “B” ✕", lists every
 * checked thing, each with ✕ to uncheck it (the owner, 2026-10-15). Kept in this browser tab
 * (sessionStorage), per page; cleared once the bar's action is done.
 * For the bar's scripts: window.qgenCheckedIds() (every checked one, here or not, in the order
 * checked) and window.qgenCheckedClear(). */
(function () {
  var form = document.getElementById('file-form');
  var bar = form && form.closest('.folder-tools-bar');
  if (!bar) return;
  var TICKS = '.folder-main input[name="items"], .folder-main input.pick-person';
  var KEY = 'qgen-checked:' + location.pathname;
  var kept = [];  // [[id, name]]
  try { kept = JSON.parse(sessionStorage.getItem(KEY) || '[]') || []; } catch (e) { kept = []; }
  function save() { try { sessionStorage.setItem(KEY, JSON.stringify(kept)); } catch (e) {} }
  function has(id) { return kept.some(function (k) { return k[0] === id; }); }
  function ticks() { return Array.prototype.slice.call(document.querySelectorAll(TICKS)); }
  function nameOf(t) {
    var l = t.getAttribute('aria-label') || '';
    return l.replace(/^Check\s+/, '') || t.value;
  }

  //the chips: under the bar's buttons, across the bar
  var strip = document.createElement('div');
  strip.className = 'checked-strip small';
  strip.setAttribute('aria-live', 'polite');
  bar.appendChild(strip);
  function draw() {
    strip.innerHTML = '';
    strip.hidden = !kept.length;
    if (!kept.length) return;
    var lead = document.createElement('span');
    lead.className = 'muted';
    lead.textContent = 'Checked:';
    strip.appendChild(lead);
    kept.forEach(function (k) {
      var chip = document.createElement('span');
      chip.className = 'checked-chip';
      chip.appendChild(document.createTextNode(k[1]));
      var x = document.createElement('button');
      x.type = 'button'; x.className = 'chip-x'; x.textContent = '✕';
      x.title = 'Uncheck ' + k[1];
      x.setAttribute('aria-label', 'Uncheck ' + k[1]);
      x.addEventListener('click', function () { set(k[0], null, false); sync(k[0], false); });
      chip.appendChild(x);
      strip.appendChild(chip);
    });
  }
  function set(id, name, on) {
    var i = -1;
    kept.forEach(function (k, j) { if (k[0] === id) i = j; });
    if (on && i === -1) kept.push([id, name]);
    if (!on && i !== -1) kept.splice(i, 1);
    save(); draw();
    //(the bar recounts and grays its buttons from this list, after it's changed)
    setTimeout(function () { document.dispatchEvent(new CustomEvent('qgen-checked')); }, 0);
  }
  //(the boxes on this page follow; the bar recounts)
  function sync(id, on) {
    var changed = null;
    ticks().forEach(function (t) { if (t.value === id && t.checked !== on) { t.checked = on; changed = t; } });
    if (changed) changed.dispatchEvent(new Event('change', { bubbles: true }));
    else document.dispatchEvent(new CustomEvent('qgen-checked'));
  }
  document.addEventListener('change', function (e) {
    var t = e.target;
    if (!t.matches || !t.matches(TICKS)) return;
    set(t.value, nameOf(t), t.checked);
  });

  window.qgenCheckedIds = function () { return kept.map(function (k) { return k[0]; }); };
  window.qgenCheckedClear = function () {
    kept = []; save(); draw();
    ticks().forEach(function (t) { t.checked = false; });
  };

  //coming back to the page (another folder, a reload): what was checked is checked again
  var first = null;
  ticks().forEach(function (t) { if (has(t.value) && !t.checked) { t.checked = true; first = first || t; } });
  draw();
  if (first) first.dispatchEvent(new Event('change', { bubbles: true }));
  document.dispatchEvent(new CustomEvent('qgen-checked'));
})();
