'use strict';
(function(root) {
  class SlideshowOrder {
    constructor(random = Math.random) { this.random=random; this.ids=[]; this.index=0; this.shuffle=false; }
    shuffled(ids) {
      const result=[...ids];
      for(let i=result.length-1;i>0;i--) { const j=Math.floor(this.random()*(i+1)); [result[i],result[j]]=[result[j],result[i]]; }
      return result;
    }
    get current() { return this.ids[this.index] ?? null; }
    update(ids, shuffle) {
      const current=this.current;
      const existing=new Set(this.ids);
      if (shuffle===this.shuffle && ids.length===this.ids.length && ids.every(id=>existing.has(id))) return;
      this.shuffle=shuffle; this.ids=shuffle ? this.shuffled(ids) : [...ids];
      this.index=Math.max(0,this.ids.indexOf(current));
    }
    move(direction) {
      if (!this.ids.length) return null;
      this.index=(this.index+direction+this.ids.length)%this.ids.length;
      return this.current;
    }
  }
  if(typeof module!=='undefined') module.exports=SlideshowOrder;
  else root.SlideshowOrder=SlideshowOrder;
})(typeof window!=='undefined' ? window : globalThis);
