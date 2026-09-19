'use strict';
const frame = document.getElementById('frame');
const message = document.getElementById('message');
const label = document.body.dataset.camera;
let objectURL = null, lastGood = 0, targetFps = 3;
let session = null, sessionAt = 0, countdownUntil = null, frameAvailable = false;
function paint() {
  const now=performance.now();
  const state=now-sessionAt<2500 ? session : null;
  const remaining=state && countdownUntil!==null ? Math.max(0,(countdownUntil-now)/1000) : null;
  const counting=label==='B' && state?.active && state.phase==='capturing' && remaining!==null && remaining>0;
  const visible=frameAvailable && now-lastGood<2200 && !counting;
  frame.hidden=!visible;
  document.getElementById('wedding').hidden=!visible;
  message.hidden=visible;
  if(!visible) message.textContent=window.StripshotMonitorText(label,state,remaining);
}
async function refresh() {
  const started = performance.now();
  let failed = false;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 1500);
  let previous=null;
  try {
    const response = await fetch(`/api/preview/${encodeURIComponent(label)}.jpg`, {cache:'no-store', signal:controller.signal});
    const requested = Number(response.headers.get('X-Preview-FPS'));
    if (Number.isFinite(requested) && requested >= 1 && requested <= 15) targetFps = requested;
    if (!response.ok) throw new Error('Preview unavailable');
    const blob = await response.blob();
    previous=objectURL;
    objectURL=URL.createObjectURL(blob);
    frame.src=objectURL;
    await frame.decode();
    lastGood=performance.now(); frameAvailable=true;
  } catch { failed=true; frameAvailable=false; }
  finally {
    if(previous) URL.revokeObjectURL(previous);
    clearTimeout(timer); paint();
    setTimeout(refresh, failed ? 500 : Math.max(10, 1000 / targetFps - (performance.now() - started)));
  }
}
async function refreshSession() {
  const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),1500);
  try {
    const response=await fetch('/api/monitor/status',{cache:'no-store',signal:controller.signal});
    if(!response.ok) throw new Error('Session status unavailable');
    session=await response.json(); sessionAt=performance.now();
    countdownUntil=session.countdown_remaining===null ? null : sessionAt+session.countdown_remaining*1000;
  } catch { /* Stale session status expires; never pretend to know a next shutter. */ }
  finally {clearTimeout(timer);paint();setTimeout(refreshSession,400);}
}
setInterval(paint,100);
document.getElementById('fullscreen').onclick = () => document.documentElement.requestFullscreen().catch(() => {});
refresh();refreshSession();
