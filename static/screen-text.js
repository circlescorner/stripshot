 'use strict';
(function(){
 let data=null,timer=null,controller=null,stopped=false;
 const api={
  get countdownCamera(){return data?.settings.countdown_camera||'B';},
  set(element,key,fallback,values={}){
   if(!element)return;
   const item=data?.settings.items[key];
   element.textContent=(item?.text??fallback).replace(/\{(camera|count|round)\}/g,(_,key)=>String(values[key]??''));
   if(!item)return;
   Object.assign(element.style,{fontFamily:data.fonts[item.font],fontSize:`min(${item.size}px, 12vw)`,fontWeight:String(item.weight),fontStyle:item.italic?'italic':'normal',color:item.color,backgroundColor:item.background,textAlign:item.align,letterSpacing:item.spacing+'px',lineHeight:String(item.line_height),whiteSpace:'pre-wrap',overflowWrap:'anywhere'});
  }
 };
 window.StripshotScreenText=api;
 async function refresh(){
  clearTimeout(timer);if(stopped)return;controller?.abort();controller=new AbortController();const active=controller;
  const deadline=setTimeout(()=>active.abort(),3000);
  try{const response=await fetch('/api/screen-settings',{cache:'no-store',signal:active.signal});if(response.ok){const next=await response.json();if(!active.signal.aborted){data=next;window.dispatchEvent(new Event('stripshot-screen-settings'));}}}catch{}finally{clearTimeout(deadline);if(!stopped)timer=setTimeout(refresh,5000);}
 }
 window.addEventListener('pagehide',()=>{stopped=true;clearTimeout(timer);controller?.abort();});
 window.addEventListener('pageshow',()=>{if(stopped){stopped=false;refresh();}});
 refresh();
})();
