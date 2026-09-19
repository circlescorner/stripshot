/* One image fetch/decode at a time; retain only the current and two neighbors. */
'use strict';
(function(root){
class ImageWindow {
  constructor(){this.cache=new Map();this.sequence=0;this.controller=null;this.keep=new Set();}
  cancel(){this.sequence++;this.controller?.abort();this.controller=null;}
  close(){this.cancel();for(const url of this.cache.values())URL.revokeObjectURL(url);this.cache.clear();}
  async get(url,signal){
    if(this.cache.has(url))return this.cache.get(url);
    const response=await fetch(url,{signal,cache:'default'});
    if(!response.ok)throw Error('Image unavailable');
    const blob=await response.blob();if(signal.aborted)throw Error('Cancelled');
    const object=URL.createObjectURL(blob),image=new Image();let keep=false;
    const clear=()=>{if(!keep){image.src='';URL.revokeObjectURL(object);}};
    signal.addEventListener('abort',clear,{once:true});
    try{
      image.src=object;
      await Promise.race([image.decode(),new Promise((_,reject)=>signal.addEventListener('abort',()=>reject(Error('Cancelled')),{once:true}))]);
      if(signal.aborted)throw Error('Cancelled');
      this.cache.set(url,object);keep=true;return object;
    }finally{signal.removeEventListener('abort',clear);clear();}
  }
  async show(url,neighbors,onReady){
    this.cancel();const sequence=this.sequence,controller=new AbortController();this.controller=controller;
    const urls=[...new Set([url,...neighbors])].slice(0,3);this.keep=new Set(urls);
    let timer=setTimeout(()=>controller.abort(),7000);
    try{
      const object=await this.get(url,controller.signal);
      if(sequence!==this.sequence)return false;
      onReady(object);
      for(const [key,value] of this.cache){if(!this.keep.has(key)){URL.revokeObjectURL(value);this.cache.delete(key);}}
      clearTimeout(timer);
      // Preload neighbors sequentially after publication. Navigation cancels this.
      this.preload(urls.slice(1),controller,sequence);
      return true;
    }catch(error){if(sequence!==this.sequence)return false;throw error;}
    finally{clearTimeout(timer);}
  }
  async preload(urls,controller,sequence){
    for(const url of urls){
      if(sequence!==this.sequence||controller.signal.aborted)return;
      const timer=setTimeout(()=>controller.abort(),5000);
      try{await this.get(url,controller.signal);}catch{return;}finally{clearTimeout(timer);}
    }
  }
}
if(typeof module!=='undefined')module.exports=ImageWindow;else root.StripshotImageWindow=ImageWindow;
})(typeof window!=='undefined'?window:globalThis);
