const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
 const nodes=new Proxy({}, {get:(target,key)=>target[key]??={hidden:true,checked:true,value:'0'}}),calls=[];
 const baseline=Array.from({length:4},()=>({scale_x_percent:90,offset_x_px:0,scale_y_percent:95,offset_y_px:0}));
 const result={baseline,settings:baseline.map(v=>({...v,scale_x_percent:94})),limits:[]};
 const context={$:key=>nodes[key],busy:false,actionError:'',structuredClone,previewOverlay(){},post:()=>new Promise(resolve=>calls.push(resolve))};
 vm.createContext(context);vm.runInContext(fs.readFileSync('static/edge-fit.js','utf8'),context);
 const update=value=>vm.runInContext('updateEdgeBaseline('+JSON.stringify(value)+')',context);
 update(baseline);const first=nodes['edge-form'].onsubmit({preventDefault(){}});
 nodes['edge-form'].oninput();calls.shift()(result);await first;assert.equal(nodes['edge-use'].hidden,true,'edited measurements fence pending proposal');
 const second=nodes['edge-form'].onsubmit({preventDefault(){}});calls.shift()(result);await second;assert.equal(nodes['edge-use'].hidden,false);
 update(baseline.map(v=>({...v,offset_x_px:1})));assert.equal(nodes['edge-use'].hidden,true,'changed canonical alignment invalidates proposal');
 nodes['edge-use'].onclick();assert.equal(nodes['overlay-scale-1'].value,'0','stale proposal cannot fill manual values');
 assert.equal(calls.length,0,'review never automatically posts an alignment save');
 console.log('Measured edge review: edited-input fencing, canonical-fit staleness and no automatic save: PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
