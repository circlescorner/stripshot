'use strict';
const frame = document.getElementById('frame');
const message = document.getElementById('message');
const label = document.body.dataset.camera;
const bootAt=performance.now();
let objectURL = null, lastGood = 0, targetFps = 3;
let session = null, sessionAt = 0, countdownUntil = null, frameAvailable = false;
function paint() {
  const now=performance.now();
  const state=now-sessionAt<2500 ? session : null;
  const remaining=state && countdownUntil!==null ? Math.max(0,(countdownUntil-now)/1000) : null;
  const countdownCamera=window.StripshotScreenText?.countdownCamera||'B';
  const counting=label===countdownCamera && state?.active && state.phase==='capturing' && remaining!==null && remaining>0;
  const visible=frameAvailable && now-lastGood<2200 && !counting;
  frame.hidden=!visible;
  document.getElementById('wedding').hidden=!visible;
  message.hidden=visible;
  const detail=document.getElementById('recovery-detail'), health=state?.previews?.[label];
  if(detail)detail.textContent=visible||state?.active?'':!state?'Reconnecting to server…':health?.failed?'Camera failure — check operator':health?.frame_age_seconds!==null&&health?.frame_age_seconds<2?'Recovering browser display…':'Waiting for camera preview';
  const screen=window.StripshotScreenText;
  if(!visible){const content=!sessionAt&&now-bootAt<3000?{key:'loading',text:`Waiting for camera ${label}…`}:window.StripshotMonitorText.state(label,state,remaining,countdownCamera);if(screen)screen.set(message,'monitor.'+content.key,content.text,{camera:label,count:Math.ceil(remaining||0),round:state?.round||''});else message.textContent=content.text;}
  screen?.set(document.getElementById('wedding'),'monitor.brand','MalanaphyVickWedding');
  screen?.set(document.getElementById('camera-label'),'monitor.footer','CAMERA {camera}',{camera:label});
  screen?.set(document.getElementById('fullscreen'),'monitor.fullscreen','Full screen');
  if(detail&&!visible&&!state?.active){const key=!state?'connection':health?.failed?'failed':health?.frame_age_seconds!==null&&health?.frame_age_seconds<2?'browser':'waiting';screen?.set(detail,'monitor.recovery_'+key,detail.textContent);}

}
const frames=new window.StripshotResilientLoop(async ({signal,current,started})=>{
  let candidate=null;
  // Revoke even when image.decode() never settles. Never reuse the display
  // image for decoding: a timed-out decode cannot later mutate its src.
  const cleanup=()=>{if(candidate){URL.revokeObjectURL(candidate);candidate=null;}};
  signal.addEventListener('abort',cleanup,{once:true});
  try {
    const response=await fetch(`/api/preview/${encodeURIComponent(label)}.jpg`,{cache:'no-store',signal});
    if(!response.ok)throw new Error('Preview unavailable');
    const requested=Number(response.headers.get('X-Preview-FPS'));
    const blob=await response.blob();
    if(!current())return 500;
    candidate=URL.createObjectURL(blob);
    const decoded=new Image();decoded.src=candidate;
    await decoded.decode();
    if(!current())return 500;
    if(Number.isFinite(requested)&&requested>=1&&requested<=30)targetFps=requested;
    const old=objectURL;objectURL=candidate;candidate=null;
    frame.src=objectURL;
    if(old)URL.revokeObjectURL(old);
    lastGood=performance.now();frameAvailable=true;paint();
    return Math.max(10,1000/targetFps-(performance.now()-started));
  } catch {if(current()){frameAvailable=false;paint();}return 500;}
  finally {cleanup();signal.removeEventListener('abort',cleanup);}
},{deadline:2000,delay:500});
const sessions=new window.StripshotResilientLoop(async ({signal,current})=>{
  const response=await fetch('/api/monitor/status',{cache:'no-store',signal});
  if(!response.ok)throw new Error('Session status unavailable');
  const state=await response.json();
  if(current()){
    session=state;sessionAt=performance.now();
    countdownUntil=session.countdown_remaining===null?null:sessionAt+session.countdown_remaining*1000;
    paint();
  }
  return 400;
},{deadline:2000,delay:500});
function wake(){frames.wake();sessions.wake();}
document.addEventListener('visibilitychange',()=>{if(!document.hidden)wake();});
window.addEventListener('online',wake);
window.addEventListener('pageshow',wake);
window.addEventListener('pagehide',()=>{frames.stop();sessions.stop();if(objectURL){URL.revokeObjectURL(objectURL);objectURL=null;}frameAvailable=false;});
window.addEventListener('pageshow',()=>{frames.start();sessions.start();});
window.addEventListener('stripshot-screen-settings',paint);
setInterval(paint,100);
document.getElementById('fullscreen').onclick = () => document.documentElement.requestFullscreen().catch(() => {});
frames.start();sessions.start();
