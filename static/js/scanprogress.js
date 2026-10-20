/* The Dashboard's unfinished scans (templates _scan_progress.html): the chip opens and closes its
 * pop-over (Esc or a click elsewhere closes it too); while a page is being read, ask every few
 * seconds how far it has got, keeping the pop-over open if it was, and stop when nothing is. */
(function () {
  var box = document.getElementById('scan-progress-box');
  if (!box) return;
  function chip() { return box.querySelector('.scan-chip'); }
  function pop() { return box.querySelector('.scan-pop'); }
  function show(open) {
    if (!pop()) return;
    pop().hidden = !open;
    chip().setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  box.addEventListener('click', function (e) { if (e.target.closest('.scan-chip')) show(pop().hidden); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && pop() && !pop().hidden) { show(false); chip().focus(); } });
  document.addEventListener('mousedown', function (e) { if (pop() && !pop().hidden && !box.contains(e.target)) show(false); });
  function poll() {
    fetch(box.dataset.url, { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (s) {
      var open = pop() && !pop().hidden;
      box.innerHTML = s.html;
      show(open);
      //(every few seconds while a page is being read; otherwise now and then, so a scan
      //started in another tab shows up)
      setTimeout(poll, s.reading ? 4000 : 30000);
    }).catch(function () { setTimeout(poll, 30000); });
  }
  setTimeout(poll, box.dataset.reading ? 3000 : 30000);
})();
