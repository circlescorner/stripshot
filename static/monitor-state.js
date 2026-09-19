'use strict';
(function(root){
  function unavailableText(label,session,remaining) {
    if(!session) return 'Reconnecting — please wait';
    if(!session.active) return `Camera ${label} preview unavailable — check the operator dashboard`;
    if(label==='A') return 'MalanaphyVick Wedding';
    if(['capture_held','error','print_uncertain','reconnecting'].includes(session.phase)) return 'Session paused — please ask the attendant';
    if(session.phase!=='capturing') return 'Making your strips…';
    if(remaining!==null && remaining>0) return `${Math.ceil(remaining)} — get ready!`;
    return `Taking photo${session.round ? ' '+session.round+' of 8' : ''}…`;
  }
  if(typeof module!=='undefined') module.exports=unavailableText;
  else root.StripshotMonitorText=unavailableText;
})(typeof window!=='undefined'?window:globalThis);
