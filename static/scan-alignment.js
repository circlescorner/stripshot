'use strict';
let scanState = {target:null,strips:{},proposal:null}, scanRevision = 0;
let scanProposalVisible = false;
function refreshScanButtons() {
  const target = scanState.target;
  $('scan-prepare').disabled = busy;
  $('scan-print').disabled = busy || target?.status !== 'ready';
  for (let i=1;i<=4;i++) $('scan-file-'+i).disabled = busy || !['submitted','acknowledged_without_retry'].includes(target?.status);
  $('scan-calculate').disabled = busy || Object.keys(scanState.strips).length !== 4;
  $('scan-apply').disabled = busy || !scanProposalVisible || !scanState.proposal || scanState.proposal.applied || !$('scan-edges-confirmed').checked;
}
function hideScanProposal() {
  scanProposalVisible = false;
  $('scan-results').hidden = true;
  $('scan-edges-confirmed').checked = false;
  refreshScanButtons();
}
function showScanState(state, reveal=false) {
  const changed = state.target?.id !== scanState.target?.id || state.proposal?.id !== scanState.proposal?.id;
  scanState = state;
  if (changed) hideScanProposal();
  $('scan-target-status').textContent = state.target ? `${state.target.id} · ${state.target.status}` : 'Prepare a scan reference to begin.';
  $('scan-target-link').hidden = !state.target;
  if (state.target) $('scan-target-link').href = state.target.url+'/sheet.png';
  for (let i=1;i<=4;i++) {
    const strip = state.strips[i];
    $('scan-strip-status-'+i).textContent = strip ? 'Scan accepted. Inspect the green paper outline.' : 'Waiting for a scan';
    $('scan-preview-link-'+i).hidden = !strip;
    if (strip) {
      $('scan-preview-link-'+i).href = strip.preview_url;
      if ($('scan-preview-'+i).getAttribute('src') !== strip.preview_url) $('scan-preview-'+i).src = strip.preview_url;
    }
  }
  if (reveal && state.proposal) {
    const rows = $('scan-result-rows'); rows.replaceChildren();
    state.proposal.settings.forEach((setting,i) => {
      const row = document.createElement('tr'), measurement=state.proposal.measurements[i];
      for (const value of [i+1,`${setting.scale_x_percent}% / ${setting.scale_y_percent}%`,
          `${setting.offset_x_px} / ${setting.offset_y_px} px`,
          measurement.before_margins_mm.join(' / ')+' mm',measurement.after_margins_mm.join(' / ')+' mm']) {
        const cell=document.createElement('td');cell.textContent=value;row.append(cell);
      }
      rows.append(row);
    });
    $('scan-results').hidden = false; scanProposalVisible = true;
  }
  refreshScanButtons();
}
async function refreshScan() {
  const revision=scanRevision;
  try {
    const state=await requestJson('/api/scan-alignment');
    if (revision===scanRevision && !busy) showScanState(state);
  } catch(error) { if(revision===scanRevision && !busy) {hideScanProposal();$('scan-message').textContent=error.message;} }
  finally {setTimeout(refreshScan,5000);}
}
$('scan-prepare').onclick=async()=>{
  if(busy)return;
  ++scanRevision; hideScanProposal();
  const result=await toolPost('scan_prepare');
  if(result) {setCalibrationTarget(result);showScanState({target:{id:result.id,status:result.status,url:result.url},strips:{},proposal:null});}
  $('scan-message').textContent=result?'Reference prepared. Preview it, then print one sheet.':actionError;
};
$('scan-print').onclick=async()=>{
  if(busy || scanState.target?.status!=='ready')return;
  const id=scanState.target.id;
  if(!confirm('Physically print ONE numbered scan reference sheet? No photos will be taken.'))return;
  ++scanRevision;hideScanProposal();
  const result=await toolPost('calibration_print',{id});
  if(result)showScanState({...scanState,target:{...scanState.target,status:result.status}});
  $('scan-message').textContent=result?.status==='submitted'
    ? 'One sheet submitted. Scan its four numbered strips separately.'
    : 'Print not confirmed. Check the target status and printer; this target will not automatically retry. '+actionError;
};
for(let i=1;i<=4;i++) $('scan-file-'+i).onchange=async()=>{
  const input=$('scan-file-'+i);
  if(busy || !input.files.length || !scanState.target)return;
  const revision=++scanRevision,id=scanState.target.id;
  hideScanProposal();$('scan-message').textContent=`Measuring strip ${i}…`;
  const form=new FormData();form.append('file',input.files[0]);
  const result=await post(`/api/scan-alignment/${id}/${i}`,form);
  input.value='';
  if(revision!==scanRevision)return;
  if(result)showScanState(result);
  else {delete scanState.strips[i];showScanState({...scanState,proposal:null});}
  $('scan-message').textContent=result?`Strip ${i} measured. Check its green paper outline.`:actionError;
};
$('scan-clearance').oninput=()=>{++scanRevision;hideScanProposal();};
$('scan-edges-confirmed').onchange=refreshScanButtons;
$('scan-propose-form').onsubmit=async event=>{
  event.preventDefault();if(busy || !scanState.target)return;
  const revision=++scanRevision;hideScanProposal();
  const result=await toolPost('scan_propose',{id:scanState.target.id,clearance_mm:Number($('scan-clearance').value)});
  if(revision!==scanRevision)return;
  if(result)showScanState(result,true);
  $('scan-message').textContent=result?'Review the four paper outlines and proposed margins. Nothing has been applied.':actionError;
};
$('scan-apply').onclick=async()=>{
  if(busy || $('scan-apply').disabled)return;
  const revision=++scanRevision;
  const result=await toolPost('scan_apply',{id:scanState.target.id,proposal_id:scanState.proposal.id});
  if(revision!==scanRevision)return;
  if(result) {
    showScanState(result,true);
    result.proposal.settings.forEach((setting,i)=>{
      $('overlay-scale-'+(i+1)).value=setting.scale_x_percent;
      $('overlay-offset-'+(i+1)).value=setting.offset_x_px;
      $('overlay-scale-y-'+(i+1)).value=setting.scale_y_percent;
      $('overlay-offset-y-'+(i+1)).value=setting.offset_y_px;
      previewOverlay(i+1);
    });
  }
  $('scan-message').textContent=result?'PNG alignment saved. Prepare, print and scan a fresh reference to verify the border margins.':actionError;
};
refreshScan();
