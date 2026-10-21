/* The tab's dots (the owner, 2026-10-20): unfinished quizzes (blue) over new ones (gold), colored circles
 * one above the other, each with its count small and black to its right on the tab's icon, left of the page's name. Drawn on every
 * page from the server's counts (<meta name="tab-counts">); messages.js redraws them as they change. */
(function () {
  //the tab: unfinished quizzes (blue) over new ones (gold), small dots with their counts one above
  //the other on the tab's icon, left of the page's name, the same colors as the boxes on My quizzes
  //(the owner, 2026-10-20: emoji in the title were too big); none: the site's own icon again
  var iconLink = document.querySelector('link[rel="icon"]'), siteIcon = iconLink ? iconLink.href : '';
  function tabDots(fresh, started) {
    fresh = +fresh || 0; started = +started || 0;
    if (!fresh && !started) {
      if (iconLink && iconLink.dataset.dots) { iconLink.href = siteIcon; delete iconLink.dataset.dots; if (!siteIcon) iconLink.remove(); }
      return;
    }
    var c = document.createElement('canvas'); c.width = c.height = 32;
    var g = c.getContext('2d'), css = getComputedStyle(document.documentElement);
    var dots = [];
    if (started) dots.push([started, css.getPropertyValue('--accent').trim() || '#3b82f6']);
    if (fresh) dots.push([fresh, css.getPropertyValue('--warn').trim() || '#eab308']);
    dots.forEach(function (d, i) {
      //(each circle on the left, one above the other, its count small and black to its right:
      //the owner, 2026-10-20)
      var y = dots.length === 1 ? 16 : 8 + i * 16;
      g.beginPath(); g.arc(8, y, 7.5, 0, 2 * Math.PI); g.fillStyle = d[1]; g.fill();
      g.fillStyle = '#000'; g.font = 'bold 14px sans-serif'; g.textAlign = 'left'; g.textBaseline = 'middle';
      g.fillText(d[0] > 9 ? '9+' : String(d[0]), 17, y + 1);
    });
    if (!iconLink) { iconLink = document.createElement('link'); iconLink.rel = 'icon'; document.head.appendChild(iconLink); }
    iconLink.type = 'image/png'; iconLink.href = c.toDataURL('image/png'); iconLink.dataset.dots = '1';
  }
  window.qgenTabDots = tabDots;
  var m = document.querySelector('meta[name="tab-counts"]'), v = m ? m.content.split(',') : [];
  tabDots(v[0], v[1]);
})();
