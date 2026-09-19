 'use strict';
const cards=Array.from(document.querySelectorAll('a[data-display]'));
const dialog=document.getElementById('review-dialog'),image=document.getElementById('review-image');
const message=document.getElementById('review-message'),loader=new window.StripshotImageWindow();
let selected=0,revision=0,opener=null;
async function show(index){
  selected=(index+cards.length)%cards.length;const card=cards[selected],myRevision=++revision;
  message.hidden=false;message.textContent='Loading photo…';
  document.getElementById('review-previous').disabled=cards.length<2;
  document.getElementById('review-next').disabled=cards.length<2;
  const neighbors=[cards[(selected+1)%cards.length],cards[(selected-1+cards.length)%cards.length]].map(c=>c.dataset.display);
  try{await loader.show(card.dataset.display,neighbors,src=>{
    if(myRevision!==revision||!dialog.open)return;
    image.src=src;image.alt=card.dataset.caption;image.hidden=false;message.hidden=true;
    document.getElementById('review-title').textContent=card.dataset.caption;
    document.getElementById('review-count').textContent=`${selected+1} / ${cards.length}`;
    document.getElementById('review-original').href=card.href;
  });}catch{if(myRevision===revision){message.hidden=false;message.textContent='Could not load this image. Use Next, or open the full-resolution file.';document.getElementById('review-original').href=card.href;}}
}
cards.forEach((card,index)=>card.addEventListener('click',event=>{
  if(event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
  event.preventDefault();opener=card;dialog.showModal();show(index);
}));
document.getElementById('review-close').onclick=()=>dialog.close();
document.getElementById('review-previous').onclick=()=>show(selected-1);
document.getElementById('review-next').onclick=()=>show(selected+1);
dialog.addEventListener('keydown',event=>{if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();show(selected+(event.key==='ArrowLeft'?-1:1));}});
dialog.addEventListener('close',()=>{revision++;loader.close();image.removeAttribute('src');image.hidden=true;opener?.focus();});
window.addEventListener('pagehide',()=>{revision++;loader.close();});
window.addEventListener('pageshow',()=>{if(dialog.open)show(selected);});
for(const time of document.querySelectorAll('[data-timestamp]'))time.textContent=new Date(Number(time.dataset.timestamp)*1000).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'});
for(const card of cards)card.querySelector('img')?.addEventListener('error',()=>{card.classList.add('image-unavailable');card.querySelector('img').alt='Thumbnail unavailable — open photo';});
