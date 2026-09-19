 'use strict';
(function(root){
 function state(label,session,remaining,countdownCamera='B'){
  if(!session)return {key:'disconnected',text:'Reconnecting — please wait'};
  if(!session.active)return {key:'unavailable',text:`Camera ${label} preview unavailable — check the operator dashboard`};
  if(label!==countdownCamera)return {key:'holding',text:'MalanaphyVick Wedding'};
  if(['capture_held','error','print_uncertain','reconnecting'].includes(session.phase))return {key:'paused',text:'Session paused — please ask the attendant'};
  if(session.phase!=='capturing')return {key:'rendering',text:'Making your strips…'};
  if(remaining!==null&&remaining>0)return {key:'countdown',text:`${Math.ceil(remaining)} — get ready!`};
  return {key:'capturing',text:`Taking photo${session.round?' '+session.round+' of 8':''}…`};
 }
 function text(label,session,remaining,countdownCamera){return state(label,session,remaining,countdownCamera).text;}
 text.state=state;
 if(typeof module!=='undefined')module.exports=text;else root.StripshotMonitorText=text;
})(typeof window!=='undefined'?window:globalThis);
