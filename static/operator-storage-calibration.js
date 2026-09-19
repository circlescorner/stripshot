'use strict';
let storageLoaded=false,storageJob=null,calibrationTarget=null,caliperProposal=null;
const toolPost=(action,data={})=>post('/api/operator-tools/'+action,JSON.stringify(data),true);
async function refreshTools(){
 try{
  const response=await boundedFetch('/api/status');if(!response.ok)throw Error('Storage status unavailable');
  const state=await response.json(),storage=state.photo_storage;
  $('storage-root').textContent='Current recovery storage: '+state.data_dir;
  $('storage-migration-status').textContent=state.storage_migration&&!state.storage_migration.cancelled?'Pending stopped migration: '+state.storage_migration.destination:'No migration scheduled.';
  $('storage-status').textContent=storage.message+(storage.failed_jobs?.length?' · Failed copies awaiting retry: '+storage.failed_jobs.map(job=>job.id).join(', '):'');storageJob=storage.failed_jobs?.[0]||storage.latest;
  if(!storageLoaded){
   for(const key of ['enabled','originals','sheet','strips'])$('storage-'+key).checked=storage.settings[key];
   for(const key of ['folder','name','grouping','quality'])$('storage-'+key).value=storage.settings[key];
   storageLoaded=true;
  }
  const targetResponse=await boundedFetch('/api/calibration-target');if(!targetResponse.ok)throw Error('Calibration status unavailable');
  calibrationTarget=await targetResponse.json();
  $('calibration-target-status').textContent=calibrationTarget ? `${calibrationTarget.id}: ${calibrationTarget.status} ${calibrationTarget.job_id||''} · printed X ${calibrationTarget.strip_offsets_px.join(', ')}; Y ${calibrationTarget.sheet_offset_y_px}`:'No calibration target prepared.';
  if(calibrationTarget){$('calibration-target-link').href=calibrationTarget.url+'/sheet.png';$('calibration-target-link').hidden=false;}
 }catch(error){$('storage-status').textContent='Controls disconnected: '+error.message;}
 finally{setTimeout(refreshTools,3000);}
}
$('storage-form').onsubmit=async event=>{
 event.preventDefault();const data={};
 for(const key of ['enabled','originals','sheet','strips'])data[key]=$('storage-'+key).checked;
 for(const key of ['folder','name','grouping'])data[key]=$('storage-'+key).value;
 data.quality=Number($('storage-quality').value);
 $('storage-message').textContent=await toolPost('storage_settings',data)?'Saved for future sessions. Existing data and active batches unchanged.':actionError;
};
$('storage-location-form').onsubmit=async event=>{event.preventDefault();const result=await toolPost('storage_location',{destination:$('storage-location').value});$('storage-message').textContent=result?'Migration scheduled to '+result.destination+'. Stop the existing owner fully before restarting. No live data has been copied.':actionError;};
$('storage-cancel').onclick=async()=>{const result=await toolPost('storage_cancel');$('storage-message').textContent=result?result.message:actionError;};
$('storage-export').onclick=async()=>{$('storage-message').textContent=await toolPost('storage_export')?'Additional copy queued (if enabled).':actionError;};
$('storage-retry').onclick=async()=>{$('storage-message').textContent=storageJob&&await toolPost('storage_retry',{id:storageJob.id})?'Copy retry queued.':actionError||'No failed copy available.';};
$('retention-form').onsubmit=async event=>{event.preventDefault();const result=await toolPost('storage_retention',{note:$('retention-note').value});$('storage-message').textContent=result?result.message:actionError;};
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
refreshTools();
