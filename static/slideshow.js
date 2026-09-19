 'use strict';
const slide=document.getElementById('slide'),message=document.getElementById('slide-message');
const loader=new window.StripshotImageWindow(),seed=crypto.randomUUID();
let selected='',showing='',seconds=5,paused=false,total=0,timer=null,refreshTimer=null,active=null,revision=0,stopped=false;
// A bounded actual-visit history preserves Back/Forward when new sessions arrive.
let history=[],historyIndex=-1,sourceKey='';
function schedule(){clearTimeout(timer);if(!paused&&!stopped&&!document.hidden&&total>1)timer=setTimeout(()=>navigate(1),seconds*1000);}
function controls(){document.getElementById('previous').disabled=total<2;document.getElementById('next').disabled=total<2;}
async function refresh(move=0,target=''){
  active?.abort();const controller=new AbortController();active=controller;const mine=++revision;
  const deadline=setTimeout(()=>controller.abort(),6000);clearTimeout(timer);
  try{
    const params=new URLSearchParams({current:target||selected,move:String(target?0:move),seed});
    const response=await fetch('/api/slideshow?'+params,{signal:controller.signal,cache:'no-store'});
    if(!response.ok)throw Error('Disconnected');const data=await response.json();if(mine!==revision)return;
    total=data.total;seconds=data.settings.seconds;controls();
    const key=data.settings.source+':'+data.settings.shuffle_all;
    if(key!==sourceKey){history=[];historyIndex=-1;sourceKey=key;}
    document.getElementById('slide-source').textContent={all:'ALL PHOTOS',latest:'LATEST SESSION',sheets:'FINISHED SHEETS'}[data.settings.source];
    document.getElementById('slide-connection').textContent='';
    if(!data.photo){selected=showing='';loader.close();slide.hidden=true;message.hidden=false;message.textContent='Waiting for completed '+(data.settings.source==='sheets'?'sheets':'photos')+'…';document.getElementById('slide-count').textContent='';return;}
    selected=data.photo.id;
    if(target&&selected===target){historyIndex=history.lastIndexOf(target);}else if(history[historyIndex]!==selected){history=history.slice(0,historyIndex+1);history.push(selected);if(history.length>100)history.shift();historyIndex=history.length-1;}
    document.getElementById('slide-count').textContent=`${data.index+1} / ${total}`;
    if(showing===selected)message.hidden=true;
    if(showing!==selected){
      message.hidden=false;message.textContent='Loading next photo…';
      await loader.show(data.photo.url,data.neighbors.map(p=>p.url),src=>{
        if(mine!==revision)return;slide.src=src;slide.alt=data.photo.caption;slide.hidden=false;showing=selected;message.hidden=true;
        document.getElementById('slide-caption').textContent=data.photo.caption;
      });
    }
  }catch{if(mine===revision){document.getElementById('slide-connection').textContent='Connection or image unavailable. Retrying…';message.hidden=false;message.textContent=showing?'Keeping the last photo while reconnecting…':'Photos unavailable — reconnecting…';}}
  finally{clearTimeout(deadline);if(mine===revision){active=null;schedule();clearTimeout(refreshTimer);if(!stopped&&!document.hidden)refreshTimer=setTimeout(()=>refresh(),10000);}}
}
function navigate(direction){const index=historyIndex+direction;const target=index>=0&&index<history.length?history[index]:'';refresh(direction,target);}
function togglePause(){paused=!paused;document.getElementById('pause').textContent=paused?'Play':'Pause';document.getElementById('pause').setAttribute('aria-pressed',String(paused));schedule();}
function fullscreen(){if(document.fullscreenElement)document.exitFullscreen().catch(()=>{});else document.documentElement.requestFullscreen().catch(()=>{});}
document.getElementById('previous').onclick=()=>navigate(-1);document.getElementById('next').onclick=()=>navigate(1);
document.getElementById('pause').onclick=togglePause;document.getElementById('fullscreen').onclick=fullscreen;
document.addEventListener('keydown',event=>{if(event.altKey||event.ctrlKey||event.metaKey||event.target.closest('input,select,textarea,button,a'))return;if(['ArrowLeft','ArrowRight',' ','f','F'].includes(event.key)){event.preventDefault();if(event.repeat)return;if(event.key.startsWith('Arrow'))navigate(event.key==='ArrowLeft'?-1:1);else if(event.key===' ')togglePause();else fullscreen();}});
window.addEventListener('pagehide',()=>{stopped=true;revision++;active?.abort();clearTimeout(timer);clearTimeout(refreshTimer);loader.close();showing='';});
window.addEventListener('pageshow',()=>{if(stopped){stopped=false;refresh();}});
document.addEventListener('visibilitychange',()=>{if(document.hidden){clearTimeout(timer);clearTimeout(refreshTimer);active?.abort();loader.cancel();}else refresh();});
window.addEventListener('online',()=>{if(!stopped&&!document.hidden)refresh();});
refresh();
