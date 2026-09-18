'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="stripshot-token"]').content;
let busy = false;
let lastPreview = '';
let actionError = '';
let layoutLoaded = false;
let refreshing = false;
async function boundedFetch(url, options = {}, timeoutMs = 5000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try { return await fetch(url, {...options, signal:controller.signal}); }
  finally { clearTimeout(timeout); }
}
const descriptions = {
  reconnecting: ['Reconnecting cameras', 'Verifying camera identities and restoring previews. No shutter is issued.'],
  capturing: ['Taking your photos', 'Eight paired rounds, with previews between shots.'],
  capture_held: ['Capture paused', 'Review the saved shutter records before resuming or abandoning.'],
  starting: ['Starting up', 'Reading the SD-card baselines. Wait before taking photos.'],
  watching: ['Ready for the moment', 'Watching for eight new JPEGs from each camera.'],
  downloading: ['Collecting the originals', 'The full 16-photo batch is saved. Downloading now.'],
  rendering: ['Making your strips', 'Arranging photos and applying your four overlays.'],
  submitting: ['Sending one sheet', 'Recording one print attempt with the spooler.'],
  print_uncertain: ['Check the printer', 'This batch will not print again automatically.'],
  error: ['Needs your attention', 'Collection or preparation is paused.'],
};
async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try {
    const response = await boundedFetch('/api/status');
    if (!response.ok) throw new Error('Dashboard status is unavailable');
    const state = await response.json();
    if (!layoutLoaded && state.layout) {
      fillLayout(state.layout);
      layoutLoaded = true;
    }
    if (state.layout) {
      const order = state.layout.photo_order ?? Array.from({length:4}, (_,i) => [`A${i*2+1}`,`B${i*2+1}`,`A${i*2+2}`,`B${i*2+2}`]);
      order.forEach((strip,i) => { $('saved-order-'+(i+1)).textContent = strip.join(' · '); });
    }
    $('uptime').textContent = `Running for ${Math.floor(state.uptime_seconds / 3600)}h ${Math.floor(state.uptime_seconds % 3600 / 60)}m · No application session expiry`;
    const [title, detail] = descriptions[state.phase] || ['Paused', 'Check the appliance.'];
    $('phase').textContent = title;
    $('phase-detail').textContent = state.capture_mode === 'software' && state.phase === 'watching' ? 'Ready to take eight photos on each camera.' : state.capture_mode === 'software' && state.phase === 'starting' ? 'Opening camera sessions and previews.' : detail;
    $('mode').textContent = state.demo ? 'DEMO / NO PRINTING' : state.printing_enabled ? 'LIVE / PRINT ENABLED' : 'LIVE / DRY RUN';
    for (const c of ['A', 'B']) {
      $('camera-' + c).textContent = state.cameras[c] + (state.previews?.[c]?.recent_fps ? ` · ${state.previews[c].recent_fps} preview FPS` : '');
      $('count-' + c).replaceChildren(document.createTextNode(state.counts[c] + ' '));
      const small = document.createElement('small'); small.textContent = '/ 8';
      $('count-' + c).append(small);
      $('progress-' + c).value = Math.min(state.counts[c], 8);
    }
    const remaining = Math.max(0, 8-state.counts.A) + Math.max(0, 8-state.counts.B);
    $('waiting').textContent = state.capture_mode === 'software' ? (state.current ? `${state.counts.A + state.counts.B} exact photos downloaded for this batch.` : 'Ready for a new 16-photo batch.') : state.current ? 'Processing 16 photos · new arrivals wait for the next batch.' : `Waiting for ${remaining} photographs.`;
    if ($('capture')) $('capture').disabled = busy || state.phase !== 'watching' || Boolean(state.current);
    $('reconnect-cameras').hidden = !state.reconnect_available;
    $('reconnect-cameras').disabled = busy || state.capture_busy;
    $('resume-capture').hidden = state.phase !== 'capture_held';
    $('abandon-capture').hidden = state.phase !== 'capture_held';
    $('resume-capture').disabled = busy || state.capture_busy;
    $('abandon-capture').disabled = busy || state.capture_busy;
    $('capture-records').hidden = state.phase !== 'capture_held';
    if (state.current?.shots) {
      $('capture-records').textContent = ['A', 'B'].map(c => c + ': ' + state.current.shots[c].map((s, i) =>
        `${i + 1} ${s.downloaded_at ? 'downloaded' : s.identity ? 'identified' : s.intent_at ? 'uncertain — no replacement' : 'not issued'}`
      ).join(', ')).join(' / ');
    }
    $('reset').disabled = busy || state.phase !== 'watching' || Boolean(state.current);
    if ($('demo')) $('demo').disabled = busy || state.phase !== 'watching' || Boolean(state.current);
    $('retry').hidden = !(state.phase === 'error' && state.current?.stage === 'preparing');
    $('acknowledge').hidden = state.phase !== 'print_uncertain';
    $('notice').hidden = !(state.error || actionError);
    $('notice').textContent = actionError || state.error;
    if (state.last) {
      const labels = {dry_run:'Your sheet is ready.', submitted:'One sheet submitted.', acknowledged_without_retry:'Print acknowledged.'};
      $('last-title').textContent = labels[state.last.status] || 'Batch complete.';
      $('last-detail').textContent = `16 photos · ${state.last.job_id || (state.last.status === 'dry_run' ? 'Dry run — no paper used' : 'No automatic reprint')}`;
      if (!state.last.preview_available) { $('last-preview').hidden = true; lastPreview = ''; }
      if (state.last.preview_available && lastPreview !== state.last.id) {
        lastPreview = state.last.id;
        $('last-preview').src = `/batches/${encodeURIComponent(lastPreview)}/preview.jpg`;
        $('last-preview').hidden = false;
      }
    }
  } catch (error) {
    $('phase').textContent = 'Dashboard disconnected';
    $('phase-detail').textContent = 'Reconnecting… Check the running application if this persists.';
    $('reset').disabled = true;
    if ($('capture')) $('capture').disabled = true;
    if ($('demo')) $('demo').disabled = true;
  } finally { refreshing = false; }
}
async function post(url, body, json = false) {
  busy = true; actionError = '';
  document.querySelectorAll('button').forEach(button => button.disabled = true);
  try {
    const response = await boundedFetch(url, {method:'POST', headers:{'X-Stripshot-Token':token, ...(json ? {'Content-Type':'application/json'} : {})}, body}, 135000);
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Action failed');
    return true;
  } catch (error) { actionError = error.message; return false; }
  finally {
    busy = false;
    document.querySelectorAll('button').forEach(button => button.disabled = false);
    await refresh();
  }
}
$('reset').onclick = () => { if (confirm('Ignore the pending photos and count the next 8 from each camera? No files will be deleted.')) post('/api/reset'); };
if ($('capture')) $('capture').onclick = () => post('/api/capture');
$('reconnect-cameras').onclick = () => post('/api/reconnect');
$('resume-capture').onclick = () => post('/api/resume_capture');
$('abandon-capture').onclick = () => { if (confirm('Abandon this incomplete batch? All SD files, downloaded photos and shutter records will be kept.')) post('/api/abandon_capture'); };
$('retry').onclick = () => post('/api/retry');
$('acknowledge').onclick = () => { if (confirm('Have you checked CUPS and the physical printer? Continue without submitting this batch again?')) post('/api/acknowledge'); };
if ($('demo')) $('demo').onclick = () => post('/api/demo');
document.querySelectorAll('input[data-strip]').forEach(input => input.onchange = async () => {
  if (!input.files.length) return;
  const data = new FormData(); data.append('file', input.files[0]);
  if (await post('/api/overlays/' + input.dataset.strip, data)) $('overlay-' + input.dataset.strip).src = `/overlays/${input.dataset.strip}.png?v=${Date.now()}`;
  input.value = '';
});
async function printerStatus() {
  try { const response = await boundedFetch('/api/printer'); const data = await response.json(); $('printer-status').textContent = data.status; }
  catch { $('printer-status').textContent = 'Printer status unavailable'; }
}
async function statusLoop() { await refresh(); setTimeout(statusLoop, 1000); }
async function printerLoop() { await printerStatus(); setTimeout(printerLoop, 15000); }
statusLoop(); printerLoop();

window.StripshotSpace.bind(document, () => {
  const button = $('capture');
  if (button && !button.disabled && !busy) button.click();
});

function fillLayout(layout) {
  for (const name of ['margin','top','bottom','gap']) $('layout-' + name).value = (layout[name] * 25.4 / 300).toFixed(2);
  $('layout-scale').value = layout.photo_scale ?? 100;
  if (layout.photo_order || !layoutLoaded) {
    const order = layout.photo_order ?? Array.from({length:4}, (_,i) => [`A${i*2+1}`,`B${i*2+1}`,`A${i*2+2}`,`B${i*2+2}`]);
    order.forEach((strip,i) => strip.forEach((photo,j) => { $('order-'+(i+1)+'-'+(j+1)).value = photo; }));
  }
}
$('layout-larger').onclick = () => {
  fillLayout({margin:36,top:36,bottom:180,gap:24,photo_scale:95});
  $('layout-message').textContent = 'Suggested larger margins loaded. Save to apply to the next batch.';
};
$('layout-form').onsubmit = async event => {
  event.preventDefault();
  $('layout-message').textContent = '';
  const layout = {};
  for (const name of ['margin','top','bottom','gap']) layout[name] = Math.round(Number($('layout-' + name).value) * 300 / 25.4);
  layout.photo_order = Array.from({length:4}, (_,i) => Array.from({length:4}, (_,j) => $('order-'+(i+1)+'-'+(j+1)).value));
  layout.photo_scale = Number($('layout-scale').value);
  if (await post('/api/layout', JSON.stringify(layout), true)) {
    $('layout-message').textContent = 'Saved for future batches and restarts. Current batch unchanged.';
  } else {
    $('layout-message').textContent = 'Not saved. ' + actionError;
  }
};
