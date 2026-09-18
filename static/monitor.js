'use strict';
const frame = document.getElementById('frame');
const message = document.getElementById('message');
const label = document.body.dataset.camera;
let objectURL = null;
let lastGood = 0;
let targetFps = 3;
async function refresh() {
  const started = performance.now();
  let failed = false;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 1500);
  try {
    const response = await fetch(`/api/preview/${encodeURIComponent(label)}.jpg`, {cache:'no-store', signal:controller.signal});
    const requested = Number(response.headers.get('X-Preview-FPS'));
    if (Number.isFinite(requested) && requested >= 1 && requested <= 15) targetFps = requested;
    if (!response.ok) throw new Error('Preview unavailable');
    const blob = await response.blob();
    const next = URL.createObjectURL(blob);
    const previous = objectURL;
    objectURL = next;
    frame.src = next;
    await frame.decode();
    if (previous) URL.revokeObjectURL(previous);
    lastGood = performance.now();
    frame.hidden = false;
    document.getElementById('wedding').hidden = false;
    message.hidden = true;
  } catch {
    failed = true;
    frame.hidden = true;
    document.getElementById('wedding').hidden = true;
    message.hidden = false;
    message.textContent = `Camera ${label} preview unavailable — check the operator dashboard`;
  } finally {
    clearTimeout(timer);
    setTimeout(refresh, failed ? 500 : Math.max(10, 1000 / targetFps - (performance.now() - started)));
  }
}
setInterval(() => {
  if (performance.now() - lastGood > 2200) {
    frame.hidden = true;
    document.getElementById('wedding').hidden = true;
    message.hidden = false;
  }
}, 250);
document.getElementById('fullscreen').onclick = () => document.documentElement.requestFullscreen().catch(() => {});
refresh();
