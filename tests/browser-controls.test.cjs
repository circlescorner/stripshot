const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const requestJson=require('../static/request-json.js');
const turn=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const elements=()=>new Proxy({}, {get:(target,id)=>target[id]??=( {style:{},value:10,disabled:false,hidden:false,textContent:'',getAttribute(name){return this[name]??null;},setCustomValidity(value){this.validationMessage=value;},reportValidity(){},replaceChildren(){},append(){},addEventListener(type,fn){this[type]=fn;}} )});

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
 nodes['scan-apply'].disabled=true;
 const buttons=[nodes['scan-apply'],nodes.reset];
 const context={document:{getElementById:id=>nodes[id],querySelector:()=>({content:'token'}),querySelectorAll:selector=>selector==='button'?buttons:[]},
  window:{StripshotSpace:{bind(){}},StripshotRequestJson:(url,options)=>{const d=deferred();calls.push({url,options,...d});return d.promise;}},setTimeout(){}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('static/app.js','utf8'),context);
 const first=vm.runInContext("post('/api/layout','{}',true)",context);
 assert.equal(nodes.reset.disabled,true);
 assert.equal(await vm.runInContext("post('/api/calibration','{}',true)",context),false);
 assert.equal(calls.filter(c=>c.options?.method==='POST').length,1,'busy forms cannot queue another action');
 calls.find(c=>c.options?.method==='POST').resolve({ok:true});await first;
 assert.equal(nodes['scan-apply'].disabled,true,'unrelated action preserves disabled apply button');
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

async function overlays(){
 const nodes=elements(),calls=[];
 const state={overlay_settings:[{scale_x_percent:90,offset_x_px:-12},...Array.from({length:3},()=>({scale_x_percent:100,offset_x_px:0}))],
  calibration:{strip_offsets_px:[26,16,6,-2]},slideshow:{},previews:{A:{},B:{}},
  cameras:{A:'connected',B:'connected'},counts:{A:0,B:0},phase:'watching'};
 const context={document:{getElementById:id=>nodes[id],querySelector:()=>({content:'token'}),
  querySelectorAll:()=>[],createTextNode:()=>({}),createElement:()=>({})},
  window:{StripshotSpace:{bind(){}},StripshotRequestJson:async(url,options)=>{
   if(url==='/api/status')return state;
   if(url==='/api/printer')return {};
   const d=deferred();calls.push({url,options,...d});return d.promise;
  }},setTimeout(){}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('static/app.js','utf8'),context);
 await turn();assert.equal(nodes['overlay-scale-1'].value,90);
 assert.equal(nodes['overlay-offset-1'].value,-12);
 assert.equal(nodes['overlay-1'].style.transform,'translate(-2%, 0%) scale(0.9, 1)');
 nodes['overlay-scale-2'].value=80;nodes['overlay-scale-2'].oninput();
 nodes['overlay-offset-2'].value=30;nodes['overlay-offset-2'].oninput();
 assert.equal(nodes['overlay-2'].style.transform,'translate(5%, 0%) scale(0.8, 1)');
 assert.equal(nodes['overlay-1'].style.transform,'translate(-2%, 0%) scale(0.9, 1)');
 await vm.runInContext('refresh()',context);
 assert.equal(nodes['overlay-scale-2'].value,80,'polling preserves unsaved edits');
 const save=nodes['overlay-settings-form'].onsubmit({preventDefault(){}});await turn();
 assert.equal(calls[0].url,'/api/overlay-settings');
 const expected=[state.overlay_settings[0],{scale_x_percent:80,offset_x_px:30},...state.overlay_settings.slice(2)];
 assert.deepEqual(JSON.parse(calls[0].options.body),expected);
 assert.equal(calls[0].options.headers['X-Stripshot-Token'],'token');
 calls[0].resolve({ok:true});await save;
 assert.match(nodes['overlay-settings-message'].textContent,/saved/);
 nodes['overlay-scale-2'].value=100;nodes['overlay-offset-2'].value=0;nodes['overlay-scale-2'].oninput();
 assert.equal(nodes['overlay-offset-1'].value,-12,'editing one PNG leaves the other fit unchanged');
 const failed=nodes['overlay-settings-form'].onsubmit({preventDefault(){}});await turn();
 calls[1].reject(Error('Disk full'));await failed;
 assert.match(nodes['overlay-settings-message'].textContent,/Save not confirmed.*Disk full/);
 assert.equal(calls.length,2,'failed save is not automatically retried');
 nodes['overlay-offset-2'].value=1;nodes['overlay-offset-2'].oninput();
 assert.match(nodes['overlay-offset-2'].validationMessage,/crop/);
 await nodes['overlay-settings-form'].onsubmit({preventDefault(){}});
 assert.equal(calls.length,2,'cropping placement cannot be saved');
}

async function scanAlignment(){
 const nodes=elements(),gets=[],posts=[];
 const state={target:{id:'cal-test',status:'submitted',url:'/calibration-targets/cal-test'},
  strips:Object.fromEntries([1,2,3,4].map(i=>[i,{scan_id:'scan-'+i,fit_error_px:.4,preview_url:'/scan-'+i+'.jpg'}])),proposal:null};
 const proposal={id:'proposal-1',applied:false,settings:Array.from({length:4},()=>({scale_x_percent:90,offset_x_px:-20,scale_y_percent:99,offset_y_px:2})),
  measurements:Array.from({length:4},()=>({before_margins_mm:[-1,1,-1,1],after_margins_mm:[1,1,1,1]}))};
 const context={$:id=>nodes[id],busy:false,actionError:'Rejected',confirm:()=>true,setTimeout(){},previewOverlay(){},setCalibrationTarget(){},
  document:{createElement:()=>({append(){}})},FormData:class{append(){}},
  requestJson:()=>{const d=deferred();gets.push(d);return d.promise;},
  toolPost:(action,body)=>{const d=deferred();posts.push({action,body,...d});return d.promise;},
  post:(url,body)=>{const d=deferred();posts.push({url,body,...d});return d.promise;}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('static/scan-alignment.js','utf8'),context);
 gets.shift().resolve(state);await turn();
 assert.equal(nodes['scan-calculate'].disabled,false);
 const calculate=nodes['scan-propose-form'].onsubmit({preventDefault(){}});
 posts.shift().resolve({...state,proposal});await calculate;
 assert.equal(nodes['scan-results'].hidden,false);
 assert.equal(nodes['scan-apply'].disabled,true,'paper-edge review is required');
 nodes['scan-edges-confirmed'].checked=true;nodes['scan-edges-confirmed'].onchange();
 assert.equal(nodes['scan-apply'].disabled,false);
 nodes['scan-clearance'].oninput();assert.equal(nodes['scan-apply'].disabled,true);
 const refresh=vm.runInContext('refreshScan()',context);gets.shift().resolve({...state,proposal});await refresh;
 assert.equal(nodes['scan-apply'].disabled,true,'polling cannot resurrect an invalidated proposal');
 const stale=nodes['scan-propose-form'].onsubmit({preventDefault(){}});
 nodes['scan-clearance'].oninput();posts.shift().resolve({...state,proposal});await stale;
 assert.equal(nodes['scan-results'].hidden,true,'late calculation after edited input is discarded');
 const recalc=nodes['scan-propose-form'].onsubmit({preventDefault(){}});posts.shift().resolve({...state,proposal});await recalc;
 nodes['scan-edges-confirmed'].checked=true;nodes['scan-edges-confirmed'].onchange();
 const apply=nodes['scan-apply'].onclick();const action=posts.shift();
 assert.equal(action.action,'scan_apply');assert.equal(action.body.proposal_id,'proposal-1');
 action.resolve({...state,proposal:{...proposal,applied:true}});await apply;
 assert.equal(nodes['scan-apply'].disabled,true);assert.equal(nodes['overlay-scale-y-1'].value,99);
 nodes['scan-file-1'].files=[{}];const upload=nodes['scan-file-1'].onchange();
 posts.shift().resolve(false);await upload;
 assert.equal(nodes['scan-calculate'].disabled,true,'failed replacement cannot use an old scan');
 assert.equal(nodes['scan-preview-link-1'].hidden,true);
 vm.runInContext('updateScanAlignmentSettings('+JSON.stringify(proposal.settings)+')',context);
 vm.runInContext('showScanState('+JSON.stringify({...state,proposal:{...proposal,applied:true}})+')',context);
 assert.match(nodes['scan-saved-status'].textContent,/Saved alignment/);
 const manual=proposal.settings.map(s=>({...s,offset_x_px:0}));
 vm.runInContext('updateScanAlignmentSettings('+JSON.stringify(manual)+')',context);
 assert.match(nodes['scan-saved-status'].textContent,/Manual edits replace/);
 vm.runInContext('showScanState('+JSON.stringify({...state,target:{...state.target,status:'print_uncertain'}})+')',context);
 assert.equal(nodes['scan-acknowledge'].hidden,false);
 assert.equal(nodes['scan-prepare'].disabled,true,'uncertain reference cannot be replaced');
 assert.equal(nodes['scan-print'].disabled,true,'uncertain reference cannot be printed again');
 const acknowledge=nodes['scan-acknowledge'].onclick();const ack=posts.shift();
 assert.equal(ack.action,'calibration_acknowledge');assert.equal(ack.body.id,'cal-test');
 ack.resolve({status:'acknowledged_without_retry'});await acknowledge;
 assert.equal(nodes['scan-acknowledge'].hidden,true);
 assert.equal(nodes['scan-file-1'].disabled,false);
 assert.equal(posts.length,0,'acknowledgement never submits another print');
 const legacy=vm.runInContext('refreshScan()',context);
 gets.shift().resolve({target:null,strips:{},proposal:null});await turn();
 gets.shift().resolve({id:'old-reference',status:'print_uncertain'});await legacy;
 assert.equal(nodes['scan-acknowledge'].hidden,false,'old reference attempts can still be acknowledged');
 const oldAck=nodes['scan-acknowledge'].onclick();const pending=posts.shift();
 assert.equal(pending.body.id,'old-reference');pending.resolve({status:'acknowledged_without_retry'});await oldAck;
 assert.equal(nodes['scan-prepare'].disabled,false);
}

async function applicationControls(){
 const nodes=elements(),posts=[];let reloads=0;
 const context={$:id=>nodes[id],busy:false,actionError:'Lost response',confirm:()=>true,
  window:{location:{reload(){reloads++;}}},
  post:(url,body)=>{const d=deferred();posts.push({url,body,...d});return d.promise;}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('static/application-control.js','utf8'),context);
 vm.runInContext("updateApplicationControls({instance_id:'old',application_control_available:true})",context);
 assert.equal(nodes['application-restart'].disabled,false);
 const restarting=nodes['application-restart'].onclick();
 assert.equal(posts[0].url,'/api/application-control');assert.deepEqual(JSON.parse(posts[0].body),{action:'restart'});
 await nodes['application-stop'].onclick();assert.equal(posts.length,1,'no second lifecycle request while pending');
 posts[0].resolve({accepted:true,action:'restart'});await restarting;
 vm.runInContext('applicationDisconnected()',context);
 assert.equal(nodes['phase'].textContent,'Restarting Stripshot');
 vm.runInContext("updateApplicationControls({instance_id:'new',application_control_available:true})",context);
 assert.equal(reloads,1,'new process refreshes stale operator token');
 // A rejected request is not retried; fresh state can make controls available again.
 vm.runInContext("applicationPending=null; updateApplicationControls({instance_id:'new',application_control_available:true})",context);
 const stopping=nodes['application-stop'].onclick();posts[1].resolve(false);await stopping;
 assert.match(nodes['application-message'].textContent,/not confirmed/);
 vm.runInContext("updateApplicationControls({instance_id:'new',application_control_available:true,application_control_action:null})",context);
 assert.equal(nodes['application-stop'].disabled,false);assert.equal(posts.length,2);
 vm.runInContext("applicationPending=null; updateApplicationControls({instance_id:'new',application_control_available:false,application_control_action:'restart',application_control_status:{state:'blocked',message:'Camera A: releasing PTP session. This instance still owns the booth.'}})",context);
 assert.match(nodes['application-message'].textContent,/Camera A/);
 assert.equal(nodes['application-restart'].disabled,true,'reload recovers the pending shutdown');
 vm.runInContext('applicationPending.started=Date.now()-31000; applicationDisconnected()',context);
 assert.match(nodes['application-message'].textContent,/existing Stripshot terminal/);
 assert.equal(posts.length,2,'blocked or slow shutdown never retries');
}

(async()=>{await requests();await kiosk();await operator();await printing();await overlays();await scanAlignment();await applicationControls();console.log('JSON deadlines, kiosk recovery, PNG adjustments, scan review, stop/restart controls, reference print recovery: PASS');})().catch(error=>{console.error(error);process.exitCode=1;});
