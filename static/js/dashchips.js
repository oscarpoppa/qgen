/* The Dashboard: folded boxes don't each take a tile. They sit together in one row of buttons
 * above the open boxes (like the folder buttons on folder pages), so a tall open box never
 * leaves holes beside short folded ones, and a folded wide box isn't stranded at the bottom.
 *
 * A button opens its box, which then takes its place among the open ones; folding an open box
 * (its heading) puts it back in the row. Opening one this way is remembered like opening it by
 * its heading (static/js/boxes.js), so the Dashboard's refresh keeps it open. Expand all /
 * Collapse all open or fold them all. Built again after each refresh. */
(function () {
  var live = document.getElementById('dash-live');
  if (!live) return;

  function build() {
    var grid = live.querySelector('.dash-grid');
    if (!grid) return;
    var old = live.querySelector('.dash-chips');
    if (old) old.remove();
    var boxes = Array.prototype.filter.call(grid.children, function (d) { return d.matches('details.dash-card'); });
    var row = document.createElement('div');
    row.className = 'dash-chips';
    row.setAttribute('role', 'group');
    row.setAttribute('aria-label', 'Folded boxes');
    boxes.forEach(function (d) {
      d.classList.toggle('dash-folded', !d.open);
      if (d.open) return;
      var head = d.querySelector(':scope > summary');
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'dash-chip';
      b.setAttribute('aria-expanded', 'false');
      if (d.id) b.setAttribute('aria-controls', d.id);
      //the heading's icon, name and badges (a heading can't go in a button: its text instead)
      Array.prototype.forEach.call(head.childNodes, function (c) {
        if (c.nodeType === 1 && c.classList.contains('fold')) return;
        var copy = c.cloneNode(true);
        if (copy.nodeType === 1 && /^H\d$/.test(copy.tagName)) {
          var span = document.createElement('span');
          span.className = copy.className;
          span.textContent = copy.textContent;
          copy = span;
        }
        b.appendChild(copy);
      });
      var title = head.querySelector('.box-title');
      b.title = 'Open “' + (title ? title.textContent.trim() : 'this box') + '”';
      b.addEventListener('click', function () {
        d._byHand = Date.now();  // remembered, like a click on its heading (boxes.js)
        d.open = true;
        var to = d;
        setTimeout(function () { to.scrollIntoView({ block: 'nearest' }); }, 50);
      });
      row.appendChild(b);
    });
    row.hidden = !row.children.length;
    grid.parentNode.insertBefore(row, grid);
  }

  var t = null;
  function soon() { clearTimeout(t); t = setTimeout(build, 0); }
  //a box opened or folded (by hand, Expand all, Collapse all), and the Dashboard redrawn
  live.addEventListener('toggle', function (e) { if (e.target.matches && e.target.matches('details.dash-card')) soon(); }, true);
  //(the redraw replaces what's in #dash-live; the row of buttons going in or out doesn't count)
  function redrawn(m) {
    return m.target === live && Array.prototype.some.call(m.addedNodes, function (n) {
      return n.nodeType === 1 && !n.classList.contains('dash-chips');
    });
  }
  if (window.MutationObserver) new MutationObserver(function (list) { if (list.some(redrawn)) soon(); })
    .observe(live, { childList: true });
  build();
})();
