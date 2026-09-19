'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
// Node timers tolerate receivers that native browser timers reject.
const sandbox={performance,AbortController};
sandbox.window=sandbox;
sandbox.setTimeout=function(fn,ms){
 assert.ok(this===undefined || this===sandbox,'setTimeout must not receive the loop');
 return setTimeout(fn,ms);
};
sandbox.clearTimeout=function(id){
 assert.ok(this===undefined || this===sandbox,'clearTimeout must not receive the loop');
 return clearTimeout(id);
};
vm.runInNewContext(fs.readFileSync('static/resilient-loop.js','utf8'),sandbox);
const Loop=sandbox.StripshotResilientLoop;
(async()=>{
 let calls=0,firstCurrent,release,firstSignal;
 const first=new Promise(resolve=>{release=resolve;});
 const loop=new Loop(async ({current,signal})=>{
   calls++;
   if(calls===1){firstCurrent=current;firstSignal=signal;await first;}
   return 10;
 },{deadline:20,delay:10});
 loop.start();await new Promise(resolve=>setTimeout(resolve,65));
 assert.ok(calls>=2,'a stuck decode cannot strand the loop');
 assert.equal(firstSignal.aborted,true);assert.equal(firstCurrent(),false);
 release();loop.stop();const stopped=calls;
 await new Promise(resolve=>setTimeout(resolve,35));assert.equal(calls,stopped);
 let signal;
 const waking=new Loop(async context=>{signal=context.signal;return new Promise(()=>{});},{deadline:1000});
 waking.start();await Promise.resolve();const old=signal;waking.wake();await Promise.resolve();
 assert.equal(old.aborted,true);assert.notEqual(signal,old);waking.stop();
 console.log('Preview decode timeout, stale result fencing, wake and stop: PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
