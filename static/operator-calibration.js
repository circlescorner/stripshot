'use strict';
let calibrationTarget=null,caliperProposal=null,calibrationRevision=0;
const toolPost=(action,data={})=>post('/api/operator-tools/'+action,JSON.stringify(data),true);
function refreshCalibrationButtons(){
 $('caliper-apply').disabled=busy || !caliperProposal;
}
function clearProposal(){
 caliperProposal=null;
 $('caliper-proposal').textContent='';
 refreshCalibrationButtons();
}
function setCalibrationTarget(target){
 if(target?.id!==calibrationTarget?.id)clearProposal();
 calibrationTarget=target;
 $('calibration-target-link').hidden=!target;
 if(target)$('calibration-target-link').href=target.url+'/sheet.png';
 $('calibration-target-status').textContent=target ? `${target.id}: ${target.status} ${target.job_id||''} · printed X ${target.strip_offsets_px.join(', ')}; Y ${target.sheet_offset_y_px}`:'No calibration target prepared.';
}
async function refreshCalibration(){
 const revision=calibrationRevision;
 try{
  const target=await requestJson('/api/calibration-target');
  if(revision===calibrationRevision && !busy)setCalibrationTarget(target);
 }catch(error){if(revision===calibrationRevision && !busy)$('calibration-target-status').textContent=error.message;}
 finally{setTimeout(refreshCalibration,3000);}
}
$('calibration-prepare').onclick=async()=>{
 if(busy)return;
 ++calibrationRevision;clearProposal();
 const result=await toolPost('calibration_prepare');
 if(result)setCalibrationTarget(result);
 else $('calibration-target-status').textContent=actionError;
 $('caliper-apply').disabled=true;
};
$('calibration-print').onclick=async()=>{
 if(busy)return;
 if(!calibrationTarget){$('calibration-target-status').textContent='Prepare a target first.';return;}
 const id=calibrationTarget.id;
 if(!confirm('Physically print ONE calibration sheet '+id+'? This submission will never automatically retry.'))return;
 ++calibrationRevision;
 const result=await toolPost('calibration_print',{id});
 $('calibration-target-status').textContent=result?`${id}: ${result.status} ${result.job_id||''}`:actionError+' Check target status and CUPS; do not assume no print was sent.';
};
$('calibration-acknowledge').onclick=async()=>{
 if(busy || !calibrationTarget)return;
 const id=calibrationTarget.id;
 if(!confirm('Have you checked CUPS and the physical printer? Acknowledge this attempt without retrying?'))return;
 ++calibrationRevision;
 const result=await toolPost('calibration_acknowledge',{id});
 $('calibration-target-status').textContent=result?`${id}: ${result.status}`:actionError;
};
$('caliper-form').onsubmit=async event=>{
 event.preventDefault();if(busy)return;
 clearProposal();$('caliper-message').textContent='';
 if(!calibrationTarget){$('caliper-message').textContent='Prepare and print a target first.';return;}
 const id=calibrationTarget.id, revision=++calibrationRevision;
 const result=await toolPost('calibration_measure',{id,top_mm:Number($('measure-top').value),bottom_mm:Number($('measure-bottom').value),strips:[1,2,3,4].map(i=>({left_mm:Number($('measure-left-'+i).value),right_mm:Number($('measure-right-'+i).value)}))});
 if(revision!==calibrationRevision || calibrationTarget?.id!==id)return;
 if(result){caliperProposal=result.proposed;$('caliper-proposal').textContent='Proposed X (pixels): '+caliperProposal.strip_offsets_px.join(', ')+'\nProposed Y (pixels): '+caliperProposal.sheet_offset_y_px+'\nNot applied. Custom calibration remains physically unqualified.';}
 else $('caliper-message').textContent=actionError;
 $('caliper-apply').disabled=!caliperProposal;
};
$('caliper-form').addEventListener('input',()=>{++calibrationRevision;clearProposal();});
$('caliper-apply').onclick=async()=>{
 if(busy || !caliperProposal)return;
 const proposal=caliperProposal;
 const result=await post('/api/calibration',JSON.stringify(proposal),true);
 $('caliper-message').textContent=result?'Applied for future sheets. Active batches retain frozen settings.':actionError;
 if(result){proposal.strip_offsets_px.forEach((v,i)=>{$('calibration-'+(i+1)).value=v;});$('calibration-y').value=proposal.sheet_offset_y_px;clearProposal();}
};
refreshCalibration();
