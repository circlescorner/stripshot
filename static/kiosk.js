'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="stripshot-token"]').content;
let ready = false, posting = false, pending = false, beforeLast = null, last = null;
let uncertain = false;
async function fetchBounded(url, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try { return await fetch(url, {...options, signal: controller.signal}); }
  finally { clearTimeout(timeout); }
}
function disable() { ready = false; $('go').disabled = true; }
async function refresh() {
  try {
    const response = await fetchBounded('/api/kiosk/status');
    if (!response.ok) throw new Error('Disconnected');
    const state = await response.json();
    if (state.session_id && state.session_id !== token) { disable(); window.location.reload(); return; }
    last = state.last_id;
    // Wait for server evidence of the accepted batch, not an old ready response.
    if (pending && (!state.ready || last !== beforeLast)) { pending = false; uncertain = false; }
    ready = state.ready && !posting && !pending && !uncertain;
    $('go').disabled = !ready;
    $('mode').hidden = state.printing_enabled;
    const busy = ['capturing', 'downloading', 'rendering', 'submitting'].includes(state.phase);
    $('counts').hidden = !busy;
    for (const c of ['A','B']) $('count-' + c).textContent = c + ': ' + state.counts[c] + ' / 8';
    if (uncertain) {
      $('title').textContent = 'Please ask the attendant';
      $('detail').textContent = 'We are checking whether your session started.';
    } else if (state.phase === 'watching' && !posting && !pending) {
      $('title').textContent = 'Have fun. Be wierd.';
      $('detail').textContent = last && state.printing_enabled && state.last_status === 'submitted' ? 'Your photos were sent to the printer. Collect your strips below.' : 'Eight photos. Two cameras. Four keepsakes.';
    } else if (busy || posting || pending) {
      $('title').textContent = state.phase === 'capturing' ? 'Look at the cameras!' : 'Making your keepsakes';
      $('detail').textContent = state.phase === 'capturing' ? 'Keep posing — we’ll take eight photos on each camera.' : 'Please wait. Your session is in progress.';
    } else if (state.phase === 'starting') {
      $('title').textContent = 'Getting ready'; $('detail').textContent = 'Please wait a moment.';
    } else {
      $('title').textContent = 'Please ask the attendant';
      $('detail').textContent = 'Your session is safely paused.';
    }
    $('hint').hidden = !ready;
  } catch {
    disable(); $('title').textContent = 'Reconnecting';
    $('detail').textContent = 'Please wait, or ask the attendant if this continues.';
    $('hint').hidden = true;
  }
}
async function go() {
  if (!ready || posting || pending || uncertain) return;
  disable(); posting = true; pending = true; beforeLast = last;
  try {
    const response = await fetchBounded('/api/capture', {method:'POST', headers:{'X-Stripshot-Token': token}});
    if (!response.ok) { pending = false; uncertain = true; }
  } catch { uncertain = true; } // Never repeat an uncertain request.
  finally { posting = false; await refresh(); }
}
$('go').onclick = go;
window.StripshotSpace.bind(document, go);
async function poll() { await refresh(); setTimeout(poll, 750); }
poll();
