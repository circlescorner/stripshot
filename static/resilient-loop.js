'use strict';
(function(root){
  // A stalled fetch/decode must not strand the next iteration. Late work gets
  // an aborted signal and must check current() before publishing any result.
  class ResilientLoop {
    constructor(run,{deadline=2000,delay=500,clock=()=>performance.now(),set=(fn,ms)=>setTimeout(fn,ms),clear=id=>clearTimeout(id)}={}) {
      // Native browser timers must not receive the loop as their receiver.
      Object.assign(this,{run,deadline,delay,clock,set,clear});
      this.timer=null;this.active=null;this.sequence=0;this.stopped=true;
    }
    start(){if(!this.stopped)return;this.stopped=false;this.tick();}
    stop(){this.stopped=true;this.sequence++;this.clear(this.timer);this.active?.abort();this.active=null;}
    wake(){if(this.stopped)return;this.sequence++;this.clear(this.timer);this.active?.abort();this.active=null;this.tick();}
    async tick(){
      if(this.stopped)return;
      const sequence=++this.sequence,controller=new AbortController(),started=this.clock();
      this.active=controller;
      let timer,wait=this.delay;
      const current=()=>!this.stopped && sequence===this.sequence && !controller.signal.aborted;
      try {
        wait=await Promise.race([
          Promise.resolve().then(()=>this.run({signal:controller.signal,current,started})),
          new Promise((_,reject)=>{timer=this.set(()=>{controller.abort();reject(new Error('Operation timed out'));},this.deadline);})
        ]);
      } catch { /* Retry the display operation; never a shutter or print request. */ }
      finally {
        this.clear(timer);controller.abort();
        if(sequence===this.sequence && !this.stopped){
          this.active=null;
          this.timer=this.set(()=>this.tick(),Number.isFinite(wait)?Math.max(10,wait):this.delay);
        }
      }
    }
  }
  if(typeof module!=='undefined')module.exports=ResilientLoop;
  else root.StripshotResilientLoop=ResilientLoop;
})(typeof window!=='undefined'?window:globalThis);
