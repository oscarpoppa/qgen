/* Essay grading: highlight parts of a student's answer as right or wrong.
 * Highlights are kept as [start, end, "right"|"wrong"] character offsets in
 * a hidden input; the student's text is only ever inserted as text. */
(function () {
  var active = null; // the answer box the last selection was made in

  function spansOf(area) {
    try { return JSON.parse(document.getElementById(area.dataset.for).value || '[]'); }
    catch (e) { return []; }
  }

  function save(area, spans) {
    spans.sort(function (a, b) { return a[0] - b[0]; });
    document.getElementById(area.dataset.for).value = JSON.stringify(spans);
    draw(area);
  }

  function draw(area) {
    var text = area.dataset.text || '';
    var spans = spansOf(area);
    area.textContent = '';
    if (!text) { area.textContent = '(no answer)'; return; }
    var pos = 0;
    spans.forEach(function (s, i) {
      if (s[0] > pos) area.appendChild(document.createTextNode(text.slice(pos, s[0])));
      var m = document.createElement('mark');
      m.className = 'hl-' + s[2];
      m.textContent = text.slice(s[0], s[1]);
      m.title = 'Click to remove this highlight';
      m.dataset.index = i;
      area.appendChild(m);
      pos = s[1];
    });
    if (pos < text.length) area.appendChild(document.createTextNode(text.slice(pos)));
  }

  /* character offset of a point inside the answer box (text or element positions alike) */
  function offset(area, node, off) {
    var r = document.createRange();
    r.setStart(area, 0);
    r.setEnd(node, off);
    return r.toString().length;
  }

  /* the selected stretch of this answer, as [start, end]. A selection that runs past the
   * answer (dragging past its end, triple-click, Ctrl+A) keeps just the part inside it,
   * so selecting everything highlights the whole answer. */
  function selectionIn(area) {
    var sel = window.getSelection();
    if (!area.dataset.text || !sel.rangeCount || sel.isCollapsed) return null;  // "(no answer)" isn't highlightable
    var r = sel.getRangeAt(0);
    if (!r.intersectsNode(area)) return null;
    var whole = document.createRange();
    whole.selectNodeContents(area);
    var length = whole.toString().length;
    var a = whole.compareBoundaryPoints(Range.START_TO_START, r) > 0 ? 0 : offset(area, r.startContainer, r.startOffset);
    var b = whole.compareBoundaryPoints(Range.END_TO_END, r) < 0 ? length : offset(area, r.endContainer, r.endOffset);
    a = Math.max(0, Math.min(a, length));
    b = Math.max(0, Math.min(b, length));
    return a < b ? [a, b] : null;
  }

  document.querySelectorAll('.hl-area').forEach(function (area) {
    draw(area);
    area.addEventListener('mouseup', function () { active = area; });
    area.addEventListener('keyup', function () { active = area; });
    area.addEventListener('click', function (e) {
      if (e.target.tagName === 'MARK' && window.getSelection().isCollapsed) {
        var spans = spansOf(area);
        spans.splice(+e.target.dataset.index, 1);
        save(area, spans);
      }
    });
    var box = area.parentNode;
    box.querySelectorAll('.hl-btn').forEach(function (btn) {
      btn.addEventListener('mousedown', function (e) { e.preventDefault(); }); // keep the selection
      btn.addEventListener('click', function () {
        //nothing selected: the whole answer (highlighting is optional; the grade is the Credit box)
        var range = selectionIn(area) || (area.dataset.text ? [0, area.dataset.text.length] : null);
        if (!range) return;  // "(no answer)": nothing to highlight
        //a new highlight replaces any it overlaps
        var spans = spansOf(area).filter(function (s) { return s[1] <= range[0] || s[0] >= range[1]; });
        spans.push([range[0], range[1], btn.dataset.kind]);
        window.getSelection().removeAllRanges();
        save(area, spans);
      });
    });
    box.querySelector('.hl-clear').addEventListener('click', function () {
      if (!spansOf(area).length) return;
      var q = 'Remove all highlights from this answer?';
      (window.qgenAsk ? window.qgenAsk(q, 'Remove all', true) : Promise.resolve(window.confirm(q)))
        .then(function (yes) { if (yes) save(area, []); });
    });
  });
})();
