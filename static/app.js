'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="stripshot-token"]').content;
let busy = false;
let lastPreview = '';
let actionError = '';
const descriptions = {
  starting: ['Starting up', 'Reading the SD-card baselines. Wait before taking photos.'],
  watching: ['Ready for the moment', 'Watching for eight new JPEGs from each camera.'],
  downloading: ['Collecting the originals', 'The full 16-photo batch is saved. Downloading now.'],
  rendering: ['Making your strips', 'Arranging photos and applying your four overlays.'],
  submitting: ['Sending one sheet', 'Recording one print attempt with the spooler.'],
  print_uncertain: ['Check the printer', 'This batch will not print again automatically.'],
  error: ['Needs your attention', 'Collection or preparation is paused.'],
};
async function refresh() {
  try {
    const response = await fetch('/api/status');
    if (!response.ok) throw new Error('Dashboard status is unavailable');
    const state = await response.json();
    const [title, detail] = descriptions[state.phase] || ['Paused', 'Check the appliance.'];
    $('phase').textContent = title;
    $('phase-detail').textContent = detail;
    $('mode').textContent = state.demo ? 'DEMO / NO PRINTING' : state.printing_enabled ? 'LIVE / PRINT ENABLED' : 'LIVE / DRY RUN';
    for (const c of ['A', 'B']) {
      $('camera-' + c).textContent = state.cameras[c];
      $('count-' + c).replaceChildren(document.createTextNode(state.counts[c] + ' '));
      const small = document.createElement('small'); small.textContent = '/ 8';
      $('count-' + c).append(small);
      $('progress-' + c).value = Math.min(state.counts[c], 8);
    }
    const remaining = Math.max(0, 8-state.counts.A) + Math.max(0, 8-state.counts.B);
    $('waiting').textContent = state.current ? 'Processing 16 photos · new arrivals wait for the next batch.' : `Waiting for ${remaining} photographs.`;
    $('reset').disabled = busy || state.phase !== 'watching' || Boolean(state.current);
    if ($('demo')) $('demo').disabled = busy || state.phase !== 'watching' || Boolean(state.current);
    $('retry').hidden = !(state.phase === 'error' && state.current?.stage === 'preparing');
    $('acknowledge').hidden = state.phase !== 'print_uncertain';
    $('notice').hidden = !(state.error || actionError);
    $('notice').textContent = state.error || actionError;
    if (state.last) {
      const labels = {dry_run:'Your sheet is ready.', submitted:'One sheet submitted.', acknowledged_without_retry:'Print acknowledged.'};
      $('last-title').textContent = labels[state.last.status] || 'Batch complete.';
      $('last-detail').textContent = `16 photos · ${state.last.job_id || (state.last.status === 'dry_run' ? 'Dry run — no paper used' : 'No automatic reprint')}`;
      if (lastPreview !== state.last.id) {
        lastPreview = state.last.id;
        $('last-preview').src = `/batches/${encodeURIComponent(lastPreview)}/preview.jpg`;
        $('last-preview').hidden = false;
      }
    }
  } catch (error) {
    $('phase').textContent = 'Dashboard disconnected';
    $('phase-detail').textContent = 'Reconnecting… Check the running application if this persists.';
    $('reset').disabled = true;
    if ($('demo')) $('demo').disabled = true;
  }
}
async function post(url, body) {
  busy = true; actionError = '';
  document.querySelectorAll('button').forEach(button => button.disabled = true);
  try {
    const response = await fetch(url, {method:'POST', headers:{'X-Stripshot-Token':token}, body});
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
  try { const response = await fetch('/api/printer'); const data = await response.json(); $('printer-status').textContent = data.status; }
  catch { $('printer-status').textContent = 'Printer status unavailable'; }
}
refresh(); printerStatus();
setInterval(refresh, 1000); setInterval(printerStatus, 15000);
