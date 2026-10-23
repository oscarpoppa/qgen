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
    var css = getComputedStyle(document.documentElement), dots = [];
    if (started) dots.push([started, css.getPropertyValue('--accent').trim() || '#3b82f6']);
    if (fresh) dots.push([fresh, css.getPropertyValue('--warn').trim() || '#eab308']);
    //the site's own icon underneath, the dots over its right edge, each count inside its circle
    //(the owner, 2026-10-22: the icon went away while the dots showed; there's no room beside them then)
    function draw(img) {
      var c = document.createElement('canvas'); c.width = c.height = 32;
      var g = c.getContext('2d');
      if (img) { try { g.drawImage(img, 0, 0, 32, 32); } catch (e) {} }
      dots.forEach(function (d, i) {
        var y = dots.length === 1 ? 23 : 9 + i * 15;
        g.beginPath(); g.arc(24, y, 8, 0, 2 * Math.PI); g.fillStyle = d[1]; g.fill();
        g.lineWidth = 1.5; g.strokeStyle = 'rgba(0,0,0,.55)'; g.stroke();
        g.fillStyle = '#000'; g.font = 'bold ' + (d[0] > 9 ? 9 : 12) + 'px sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
        g.fillText(d[0] > 9 ? '9+' : String(d[0]), 24, y + 1);
      });
      if (!iconLink) { iconLink = document.createElement('link'); iconLink.rel = 'icon'; document.head.appendChild(iconLink); }
      iconLink.type = 'image/png'; iconLink.href = c.toDataURL('image/png'); iconLink.dataset.dots = '1';
    }
    if (!siteIcon) { draw(null); return; }
    var img = new Image();
    img.onload = function () { draw(img); };
    img.onerror = function () { draw(null); };
    img.src = siteIcon;
  }
  window.qgenTabDots = tabDots;
  var m = document.querySelector('meta[name="tab-counts"]'), v = m ? m.content.split(',') : [];
  tabDots(v[0], v[1]);
})();
