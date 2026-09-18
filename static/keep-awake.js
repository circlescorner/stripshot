'use strict';
// A screen wake lock complements the launcher's OS sleep inhibitor.
(() => {
  let lock = null, requesting = false;
  function status(message) {
    const target = document.getElementById('wake-status');
    if (target) target.textContent = message;
  }
  async function acquire() {
    if (document.visibilityState !== 'visible' || lock || requesting) return;
    if (!navigator.wakeLock) { status('Screen wake lock unavailable; use the kiosk launcher for OS sleep inhibition.'); return; }
    requesting = true;
    try {
      lock = await navigator.wakeLock.request('screen');
      status('Screen kept awake while this page is visible.');
      lock.addEventListener('release', () => { lock = null; status('Screen wake lock released; will retry when visible.'); });
    } catch { status('Screen wake lock unavailable; check host power settings.'); }
    finally { requesting = false; }
  }
  document.addEventListener('visibilitychange', acquire);
  window.addEventListener('focus', acquire);
  setInterval(acquire, 30000);
  acquire();
})();
