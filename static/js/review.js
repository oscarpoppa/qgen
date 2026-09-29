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

  /* character offset of a point inside the answer box */
  function offset(area, node, off) {
    var walker = document.createTreeWalker(area, NodeFilter.SHOW_TEXT);
    var total = 0, n;
    while ((n = walker.nextNode())) {
      if (n === node) return total + off;
      total += n.textContent.length;
    }
    return total;
  }

  function selectionIn(area) {
    var sel = window.getSelection();
    if (!sel.rangeCount || sel.isCollapsed) return null;
    var r = sel.getRangeAt(0);
    if (!area.contains(r.startContainer) || !area.contains(r.endContainer)) return null;
    var a = offset(area, r.startContainer, r.startOffset);
    var b = offset(area, r.endContainer, r.endOffset);
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
        var range = selectionIn(area);
        if (!range) { alert('First select some words in this answer.'); return; }
        //a new highlight replaces any it overlaps
        var spans = spansOf(area).filter(function (s) { return s[1] <= range[0] || s[0] >= range[1]; });
        spans.push([range[0], range[1], btn.dataset.kind]);
        window.getSelection().removeAllRanges();
        save(area, spans);
      });
    });
    box.querySelector('.hl-clear').addEventListener('click', function () {
      if (spansOf(area).length && confirm('Remove all highlights from this answer?')) save(area, []);
    });
  });
})();
