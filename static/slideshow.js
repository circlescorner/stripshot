'use strict';
const order=new window.SlideshowOrder();
const slide=document.getElementById('slide'), message=document.getElementById('slide-message');
let catalog=new Map(), seconds=5, paused=false, timer=null, revision=0, showing=null;
function schedule() { clearTimeout(timer); if(!paused && order.ids.length>1) timer=setTimeout(()=>advance(1),seconds*1000); }
async function show() {
  const selected=order.current, myRevision=++revision;
  clearTimeout(timer);
  if(!selected) { showing=null; slide.hidden=true; message.hidden=false; message.textContent='Waiting for completed photos…'; document.getElementById('slide-count').textContent=''; return; }
  const image=new Image(); image.src=catalog.get(selected).url;
  let timeout;
  try {
    await Promise.race([image.decode(),new Promise((_,reject)=>{timeout=setTimeout(()=>reject(new Error('Photo timed out')),5000);})]);
    if(myRevision!==revision) return;
    slide.src=image.src; slide.hidden=false; message.hidden=true; showing=selected;
    document.getElementById('slide-count').textContent=`${order.index+1} / ${order.ids.length}`;
  } catch {
    if(myRevision!==revision) return;
    slide.hidden=true; message.hidden=false; message.textContent='Photo unavailable — use the arrow keys to continue'; showing=selected;
  } finally {clearTimeout(timeout);}
  if(myRevision===revision) schedule();
}
function advance(direction) { order.move(direction); show(); }
document.getElementById('previous').onclick=()=>advance(-1);
document.getElementById('next').onclick=()=>advance(1);
document.getElementById('pause').onclick=()=>{paused=!paused; document.getElementById('pause').textContent=paused?'Play':'Pause';schedule();};
document.getElementById('fullscreen').onclick=()=>document.documentElement.requestFullscreen().catch(()=>{});
document.addEventListener('keydown',event=>{if(event.altKey||event.ctrlKey||event.metaKey||event.target.closest('input,select,textarea')) return; if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();advance(event.key==='ArrowLeft'?-1:1);}});
async function refresh() {
  const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),5000);
  try {
    const response=await fetch('/api/slideshow',{cache:'no-store',signal:controller.signal});
    if(!response.ok) throw new Error('Slideshow unavailable');
    const data=await response.json(), previousSeconds=seconds;
    seconds=data.settings.seconds; catalog=new Map(data.photos.map(p=>[p.id,p]));
    order.update(data.photos.map(p=>p.id),data.settings.shuffle_all);
    if(showing!==order.current) await show();
    else { document.getElementById('slide-count').textContent=order.ids.length ? `${order.index+1} / ${order.ids.length}` : ''; if(seconds!==previousSeconds) schedule(); }
  } catch { if(!showing) message.textContent='Slideshow disconnected — reconnecting…'; }
  finally {clearTimeout(timeout);setTimeout(refresh,5000);}
}
refresh();
