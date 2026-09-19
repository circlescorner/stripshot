const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const listeners={},win={addEventListener:(name,handler)=>listeners['window:'+name]=handler};
vm.runInNewContext(fs.readFileSync('static/spacebar.js','utf8'),{window:win});
let starts=0, ready=true;
win.StripshotSpace.bind({addEventListener:(name,fn)=>listeners[name]=fn},()=>{if(ready) starts++;});
function key(type,values={}) { const event={code:'Space',target:{closest:()=>null},preventDefault(){this.prevented=true;},...values};listeners[type](event);return event; }
assert.equal(key('keydown').prevented,true);assert.equal(starts,1);
key('keydown',{repeat:true});key('keydown');assert.equal(starts,1);
key('keyup');ready=false;key('keydown');assert.equal(starts,1);
ready=true;key('keydown',{repeat:true});assert.equal(starts,1);
key('keyup');key('keydown');assert.equal(starts,2);
for(const values of [{ctrlKey:true},{altKey:true},{metaKey:true},{shiftKey:true},{isComposing:true},{target:{closest:()=>({})}}]) { key('keyup');key('keydown',values); }
assert.equal(starts,2);
key('keyup');key('keydown');listeners['window:blur']();key('keydown',{repeat:true});assert.equal(starts,3);
console.log('Spacebar: held/repeated/editable/modified/busy keys guarded');
