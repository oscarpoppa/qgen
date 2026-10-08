/* The top bar's "online" menu (teachers): load who's on the site each time it opens.
 * The count itself is kept up to date by messages.js. */
(function () {
  var menu = document.querySelector('details.online-menu');
  if (!menu) return;
  var pop = menu.querySelector('.online-pop');
  menu.addEventListener('toggle', function () {
    if (!menu.open) return;
    fetch(menu.dataset.url, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.text() : null; })
      .then(function (html) {
        pop.innerHTML = html ? html + '<p class="small"><a href="' + menu.dataset.dashboard + '" title="See what everyone online is working on">Dashboard →</a></p>'
                             : '<p class="muted small">Couldn\'t load the list. Please try again.</p>';
      }, function () { pop.innerHTML = '<p class="muted small">Couldn\'t load the list. Please try again.</p>'; });
  });
})();
