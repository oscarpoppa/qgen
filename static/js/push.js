/* Instant updates (app/push.py): the page keeps a connection to the server, which says
 * "something changed" the moment anything this person could see is saved. Each time,
 * the page fires 'qgen-changed' on document: the check-in (messages.js) runs at once and
 * the Dashboard redraws (dashboard.js).
 *
 * While connected, window.qgenLive is true, the page says "still here" over the
 * connection every check-in time (that keeps the person "online"), and the full check-in
 * runs only every few minutes as a backup. When the connection drops, the page checks in
 * as before until it's back; on coming back it checks at once, for anything missed. */
(function () {
  var me = document.currentScript;
  var every = Math.max(10000, +(me && me.dataset.every) || 30000);
  window.qgenLive = false;
  if (typeof io !== 'function') return;  // the connection library didn't load: check-ins as before

  var watchKey = document.body.dataset.watch || '';
  var socket = io({ transports: ['websocket', 'polling'] });
  var beat = null;

  function changed() { document.dispatchEvent(new Event('qgen-changed')); }
  function here() { if (!document.hidden) socket.emit('here', { watch: watchKey }); }

  socket.on('connect', function () {
    window.qgenLive = true;
    document.documentElement.classList.add('push-on');
    here();
    clearInterval(beat);
    beat = setInterval(here, every);
    changed();  // anything saved while not connected
  });
  socket.on('disconnect', function () {
    window.qgenLive = false;
    document.documentElement.classList.remove('push-on');
    clearInterval(beat);
  });
  socket.on('changed', changed);
  document.addEventListener('visibilitychange', function () { if (!document.hidden && socket.connected) here(); });
})();
