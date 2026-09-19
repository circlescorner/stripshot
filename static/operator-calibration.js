'use strict';
let calibrationTarget=null,caliperProposal=null;
const toolPost=(action,data={})=>post('/api/operator-tools/'+action,JSON.stringify(data),true);
async function refreshCalibration(){
 try{
  const response=await boundedFetch('/api/calibration-target');
  if(!response.ok)throw Error('Calibration status unavailable');
  calibrationTarget=await response.json();
  $('calibration-target-status').textContent=calibrationTarget ? `${calibrationTarget.id}: ${calibrationTarget.status} ${calibrationTarget.job_id||''} · printed X ${calibrationTarget.strip_offsets_px.join(', ')}; Y ${calibrationTarget.sheet_offset_y_px}`:'No calibration target prepared.';
  if(calibrationTarget){$('calibration-target-link').href=calibrationTarget.url+'/sheet.png';$('calibration-target-link').hidden=false;}
 }catch(error){$('calibration-target-status').textContent=error.message;}
 finally{setTimeout(refreshCalibration,3000);}
}
$('calibration-prepare').onclick=async()=>{const result=await toolPost('calibration_prepare');if(result){calibrationTarget=result;caliperProposal=null;$('caliper-proposal').textContent='';$('calibration-target-link').href=result.url+'/sheet.png';$('calibration-target-link').hidden=false;$('calibration-target-status').textContent=result.id+': ready — no print sent';}else $('calibration-target-status').textContent=actionError;};
$('calibration-print').onclick=async()=>{
 if(!calibrationTarget){$('calibration-target-status').textContent='Prepare a target first.';return;}
 const id=calibrationTarget.id;
 if(!confirm('Physically print ONE calibration sheet '+id+'? This submission will never automatically retry.'))return;
 const result=await toolPost('calibration_print',{id});
 $('calibration-target-status').textContent=result?`${id}: ${result.status} ${result.job_id||''}`:actionError+' Check target status and CUPS; do not assume no print was sent.';
};
$('calibration-acknowledge').onclick=async()=>{if(calibrationTarget&&confirm('Have you checked CUPS and the physical printer? Acknowledge this attempt without retrying?'))await toolPost('calibration_acknowledge',{id:calibrationTarget.id});};
$('caliper-form').onsubmit=async event=>{
 event.preventDefault();caliperProposal=null;
 if(!calibrationTarget)return;
 const result=await toolPost('calibration_measure',{id:calibrationTarget.id,top_mm:Number($('measure-top').value),bottom_mm:Number($('measure-bottom').value),strips:[1,2,3,4].map(i=>({left_mm:Number($('measure-left-'+i).value),right_mm:Number($('measure-right-'+i).value)}))});
 if(result){caliperProposal=result.proposed;$('caliper-proposal').textContent='Proposed X (pixels): '+caliperProposal.strip_offsets_px.join(', ')+'\nProposed Y (pixels): '+caliperProposal.sheet_offset_y_px+'\nNot applied. Custom calibration remains physically unqualified.';$('caliper-apply').disabled=false;}else $('caliper-message').textContent=actionError;
};
$('caliper-apply').onclick=async()=>{if(!caliperProposal)return;const result=await post('/api/calibration',JSON.stringify(caliperProposal),true);$('caliper-message').textContent=result?'Applied for future sheets. Active batches retain frozen settings.':actionError;if(result){caliperProposal.strip_offsets_px.forEach((v,i)=>{$('calibration-'+(i+1)).value=v;});$('calibration-y').value=caliperProposal.sheet_offset_y_px;}};
refreshCalibration();
