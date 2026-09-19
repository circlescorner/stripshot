const assert=require('node:assert/strict');
const ImageWindow=require('../static/image-window.js');
const turn=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 const saved={fetch:global.fetch,Image:global.Image,URL:global.URL};
 let serial=0,active=0,maximum=0,decode=null,holdDecode=false,requests=[],revoked=[];
 global.URL={createObjectURL:()=>`blob:${++serial}`,revokeObjectURL:url=>revoked.push(url)};
 global.Image=class{decode(){return holdDecode?new Promise(resolve=>{decode=resolve;}):Promise.resolve();}};
 global.fetch=async(url,{signal})=>{requests.push(url);active++;maximum=Math.max(maximum,active);await turn();active--;if(signal.aborted)throw Error('aborted');return{ok:true,blob:async()=>({})};};
 const loader=new ImageWindow();let published=[];
 try{
  await loader.show('a',['b','c'],src=>published.push(src));await turn();await turn();await turn();
  assert.equal(maximum,1);assert.equal(loader.cache.size,3);
  const count=requests.length;await loader.show('b',['a','c'],src=>published.push(src));await turn();
  assert.equal(requests.length,count,'neighbor navigation reuses decoded cache');
  await loader.show('d',['e','f'],src=>published.push(src));await turn();await turn();await turn();
  assert.equal(loader.cache.size,3);assert.equal(revoked.length,3,'old window URLs released');
  holdDecode=true;const pending=loader.show('slow',[],src=>published.push(src));await turn();await turn();
  const late=decode;holdDecode=false;const fresh=loader.show('fresh',[],src=>published.push(src));await fresh;await pending;
  const current=published.at(-1);late();await turn();assert.equal(published.at(-1),current,'late decoding cannot publish');
  assert.equal(loader.cache.size,1);loader.close();assert.equal(loader.cache.size,0);
  assert.equal(new Set(revoked).size,serial,'every created URL eventually released');
  console.log('Image window: bounded sequential loading, cache reuse, stale decode fencing and cleanup: PASS');
 }finally{loader.close();Object.assign(global,saved);}
})().catch(error=>{console.error(error);process.exitCode=1;});
