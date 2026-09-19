const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const requestJson=require('../static/request-json.js');
const turn=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const elements=()=>new Proxy({}, {get:(target,id)=>target[id]??=( {value:10,disabled:false,hidden:false,textContent:'',replaceChildren(){},append(){},addEventListener(type,fn){this[type]=fn;}} )});

async function requests(){
 const original=global.fetch;
 try {
  let count=0,signal;
  global.fetch=async(url,options)=>{count++;signal=options.signal;return new Promise(()=>{});};
  await assert.rejects(requestJson('/status',{},15),/timed out/);
  assert.equal(signal.aborted,true);assert.equal(count,1);
  const body=deferred();
  global.fetch=async(url,options)=>{count++;signal=options.signal;return {ok:true,json:()=>body.promise};};
  await assert.rejects(requestJson('/action',{method:'POST'},15),/timed out/);
  assert.equal(signal.aborted,true);assert.equal(count,2,'uncertain POST is never retried');
  body.resolve({late:true});await turn();
  global.fetch=async()=>({ok:true,json:async()=>({fresh:true})});
  assert.deepEqual(await requestJson('/status'),{fresh:true},'a request after a stalled body succeeds');
  global.fetch=async()=>({ok:false,status:409,json:async()=>({error:'Already attempted'})});
  await assert.rejects(requestJson('/action'),/Already attempted/);
  global.fetch=async()=>({ok:true,json:async()=>{throw new SyntaxError('Bad JSON');}});
  await assert.rejects(requestJson('/status'),/Bad JSON/);
 }finally{global.fetch=original;}
}

async function kiosk(){
 const nodes=elements(),requests=[],timers=[];
 const context={document:{getElementById:id=>nodes[id],querySelector:()=>({content:'session'})},
  window:{StripshotSpace:{bind(){}},StripshotRequestJson:(url,options)=>{const d=deferred();requests.push({url,options,...d});return d.promise;},location:{reload(){throw Error('Unexpected reload');}}},
  setTimeout:fn=>timers.push(fn)};
 vm.createContext(context);vm.runInContext(fs.readFileSync('static/kiosk.js','utf8'),context);
 const state=(ready,last=null)=>({session_id:'session',ready,last_id:last,phase:ready?'watching':'capturing',counts:{A:0,B:0},printing_enabled:false});
 requests.shift().resolve(state(true));await turn();assert.equal(nodes.go.disabled,false);
 // Leave an old status request pending, then start a session.
 timers.shift()();const old=requests.shift();
 const go=nodes.go.onclick();const capture=requests.shift();assert.equal(capture.url,'/api/capture');
 old.resolve(state(true,'obsolete'));await turn();assert.equal(nodes.go.disabled,true);
 capture.reject(Error('Body timed out'));await turn();
 requests.shift().resolve(state(true));await go;
 assert.equal(nodes.go.disabled,true,'uncertain capture stays blocked despite old ready state');
 await nodes.go.onclick();assert.equal(requests.length,0,'no automatic or repeated shutter request');
 const refresh=vm.runInContext('refresh()',context);requests.shift().resolve(state(false));await refresh;
 const completed=vm.runInContext('refresh()',context);requests.shift().resolve(state(true,'new'));await completed;
 assert.equal(nodes.go.disabled,false,'server evidence releases the pending session');
 // Newer successful state must not be replaced by an older failure.
 const first=vm.runInContext('refresh()',context),a=requests.shift();
 const second=vm.runInContext('refresh()',context),b=requests.shift();
 b.resolve(state(true,'new'));await second;a.reject(Error('stale failure'));await first;
 assert.equal(nodes.go.disabled,false);
}

async function operator(){
 const nodes=elements(),calls=[];
 nodes['caliper-apply'].disabled=true;
 const buttons=[nodes['caliper-apply'],nodes.reset];
 const context={document:{getElementById:id=>nodes[id],querySelector:()=>({content:'token'}),querySelectorAll:selector=>selector==='button'?buttons:[]},
  window:{StripshotSpace:{bind(){}},StripshotRequestJson:(url,options)=>{const d=deferred();calls.push({url,options,...d});return d.promise;}},setTimeout(){}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('static/app.js','utf8'),context);
 const first=vm.runInContext("post('/api/layout','{}',true)",context);
 assert.equal(nodes.reset.disabled,true);
 assert.equal(await vm.runInContext("post('/api/calibration','{}',true)",context),false);
 assert.equal(calls.filter(c=>c.options?.method==='POST').length,1,'busy forms cannot queue another action');
 calls.find(c=>c.options?.method==='POST').resolve({ok:true});await first;
 assert.equal(nodes['caliper-apply'].disabled,true,'unrelated action preserves disabled apply button');
 assert.equal(nodes.reset.disabled,false);
 calls.find(c=>c.url==='/api/status').reject(Error('Disconnected'));
 calls.find(c=>c.url==='/api/printer').resolve({status:'Idle',prints_remaining:150,media:'6x8 (A5)',percent:75,reported_at:1000,message:'Last reported by the printer driver'});await turn();
 assert.equal(nodes['printer-remaining'].textContent,'Prints remaining on roll: 150');
 assert.equal(nodes['printer-media'].textContent,'6x8 (A5) · 75% remaining');
 const failedStatus=vm.runInContext('printerStatus()',context);calls.at(-1).reject(Error('Disconnected'));await failedStatus;
 assert.equal(nodes['printer-remaining'].textContent,'Prints remaining on roll: unavailable');
 assert.equal(nodes.capture.disabled,true);
}

async function printing(){
 const nodes=elements(),calls=[];
 const state={printing_enabled:false,printing_change_available:true,demo:false,phase:'watching',
  calibration:{strip_offsets_px:[26,16,6,-2]},slideshow:{},previews:{A:{},B:{}},
  cameras:{A:'connected',B:'connected'},counts:{A:0,B:0},capture_mode:'software'};
 let failStatus=false;
 const context={document:{getElementById:id=>nodes[id],querySelector:()=>({content:'token'}),
  querySelectorAll:()=>[],createTextNode:()=>({}),createElement:()=>({})},
  window:{StripshotSpace:{bind(){}},StripshotRequestJson:async(url,options)=>{
   if(url==='/api/status'){if(failStatus)throw Error('Disconnected');return state;}
   if(url==='/api/printer')return {};
   const d=deferred();calls.push({url,options,...d});return d.promise;
  }},setTimeout(){}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('static/app.js','utf8'),context);
 await turn();assert.equal(nodes['printing-toggle'].disabled,false);
 assert.equal(nodes['printing-toggle'].textContent,'Enable live printing');
 const enable=nodes['printing-toggle'].onclick();await turn();
 assert.equal(calls[0].url,'/api/printing-settings');
 assert.deepEqual(JSON.parse(calls[0].options.body),{enabled:true});
 await nodes['printing-toggle'].onclick();assert.equal(calls.length,1,'no duplicate mode change');
 state.printing_enabled=true;calls[0].resolve({printing_enabled:true});await enable;
 assert.equal(nodes['printing-toggle'].textContent,'Use dry run');
 const disable=nodes['printing-toggle'].onclick();await turn();
 assert.deepEqual(JSON.parse(calls[1].options.body),{enabled:false});
 calls[1].reject(Error('Timed out'));await disable;
 assert.equal(calls.length,2,'uncertain change is not automatically retried');
 assert.match(nodes['printing-message'].textContent,/not confirmed/);
 state.printing_change_available=false;await vm.runInContext('refresh()',context);
 assert.equal(nodes['printing-toggle'].disabled,true);
 await nodes['printing-toggle'].onclick();assert.equal(calls.length,2);
 failStatus=true;await vm.runInContext('refresh()',context);
 assert.equal(nodes['printing-toggle'].disabled,true,'disconnect disables mode change');
}

async function calibration(){
 const nodes=elements(),gets=[],posts=[];
 const context={$:id=>nodes[id],busy:false,actionError:'Failed',confirm:()=>true,setTimeout(){},
  requestJson:()=>{const d=deferred();gets.push(d);return d.promise;},
  post:(url,body)=>{const d=deferred();posts.push({url,body,...d});return d.promise;}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('static/operator-calibration.js','utf8'),context);
 const target=id=>({id,url:'/calibration-targets/'+id,status:'submitted',strip_offsets_px:[26,16,6,-2],sheet_offset_y_px:2});
 gets.shift().resolve(target('first'));await turn();
 const measure=nodes['caliper-form'].onsubmit({preventDefault(){}});
 posts.shift().resolve({proposed:{strip_offsets_px:[25,15,5,-3],sheet_offset_y_px:1}});await measure;
 assert.equal(nodes['caliper-apply'].disabled,false);
 nodes['caliper-form'].input();assert.equal(nodes['caliper-apply'].disabled,true,'edited measurements invalidate proposal');
 await nodes['caliper-apply'].onclick();assert.equal(posts.length,0);
 const staleMeasure=nodes['caliper-form'].onsubmit({preventDefault(){}});
 nodes['caliper-form'].input();
 posts.shift().resolve({proposed:{strip_offsets_px:[0,0,0,0],sheet_offset_y_px:0}});await staleMeasure;
 assert.equal(nodes['caliper-apply'].disabled,true,'measurement results for edited inputs are discarded');
 const recalc=nodes['caliper-form'].onsubmit({preventDefault(){}});
 posts.shift().resolve({proposed:{strip_offsets_px:[25,15,5,-3],sheet_offset_y_px:1}});await recalc;
 const refresh=vm.runInContext('refreshCalibration()',context);gets.shift().resolve(target('second'));await refresh;
 assert.equal(nodes['caliper-apply'].disabled,true,'different target invalidates proposal');
 await nodes['caliper-apply'].onclick();assert.equal(posts.length,0);
 const oldRefresh=vm.runInContext('refreshCalibration()',context),old=gets.shift();
 const prepare=nodes['calibration-prepare'].onclick();posts.shift().resolve(target('third'));await prepare;
 old.resolve(target('second'));await oldRefresh;
 assert.match(nodes['calibration-target-status'].textContent,/third/,'stale polling cannot replace a newly prepared target');
}
(async()=>{await requests();await kiosk();await operator();await printing();await calibration();console.log('JSON deadlines, kiosk uncertainty/stale status, calibration proposal invalidation: PASS');})().catch(error=>{console.error(error);process.exitCode=1;});
