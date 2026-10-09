/* Coming back to a page as you left it: a page with a filter bar or folders notes, when you
 * leave it, the words in its filter (and its "Show" choice), which boxes were open and how
 * far down you were. Coming back to it (its Back button, the browser's Back, or the link to
 * the page you came from: static/js/trail.js marks those with data-came-back) puts all of
 * that back. Opening the page any other way starts it fresh. Kept for this browser tab only.
 * Loaded after the other page scripts, so the filter bars and boxes are ready. */
(function () {
  var KEY = 'qgen-left', MAX = 20, HOURS = 12;
  var main = document.querySelector('main');
  if (!main || !main.querySelector('[data-filter-bar], .folders-layout')) return;
  var here = location.pathname;

  function read() { try { return JSON.parse(sessionStorage.getItem(KEY) || '{}') || {}; } catch (e) { return {}; } }
  function bars() { return Array.prototype.slice.call(main.querySelectorAll('[data-filter-bar]')); }
  //each box by its name on the page (a box listed twice, in two folders, counted in order)
  function boxes() {
    var seen = {}, out = [];
    main.querySelectorAll('details.box:not(.box-mini):not([data-fixed])').forEach(function (d) {
      if (!window.qgenBoxes) return;
      var id = window.qgenBoxes.idOf(d);
      seen[id] = (seen[id] || 0) + 1;
      out.push({ key: id + '#' + seen[id], box: d });
    });
    return out;
  }

  window.addEventListener('pagehide', function () {
    var open = {};
    boxes().forEach(function (b) { open[b.key] = b.box.open ? 1 : 0; });
    var all = read();
    all[here] = {
      at: Date.now(), y: window.scrollY, open: open,
      bars: bars().map(function (bar) {
        var input = bar.querySelector('input[type=search]');
        return { words: input ? input.value : '',
                 picks: Array.prototype.map.call(bar.querySelectorAll('select'), function (s) { return s.selectedIndex; }) };
      })
    };
    //only the latest few pages
    Object.keys(all).sort(function (a, b) { return all[b].at - all[a].at; }).slice(MAX).forEach(function (k) { delete all[k]; });
    try { sessionStorage.setItem(KEY, JSON.stringify(all)); } catch (e) {}
  });

  var left = read()[here];
  if (!document.documentElement.hasAttribute('data-came-back') || !left || Date.now() - left.at > HOURS * 3600 * 1000) return;
  //the filters first (they open the boxes with a match), then each box just as it was
  bars().forEach(function (bar, i) {
    var was = left.bars && left.bars[i], input = bar.querySelector('input[type=search]');
    if (!was || !input) return;
    var changed = false;
    bar.querySelectorAll('select').forEach(function (s, j) {
      var k = was.picks && was.picks[j];
      if (typeof k === 'number' && k < s.options.length && s.selectedIndex !== k) { s.selectedIndex = k; changed = true; }
    });
    if (was.words && input.value !== was.words) { input.value = was.words; changed = true; }
    if (changed && bar.qgenRun) bar.qgenRun();
  });
  boxes().forEach(function (b) {
    if (b.key in left.open && !b.box.hidden) b.box.open = !!left.open[b.key];
  });
  //and the same place on the page
  if (left.y) {
    var go = function () { window.scrollTo(0, left.y); };
    go();
    window.addEventListener('load', function () { setTimeout(go, 0); });
  }
})();
