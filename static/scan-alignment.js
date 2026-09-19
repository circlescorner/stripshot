'use strict';
let scanState = {target:null,strips:{},proposal:null}, scanRevision = 0;
let scanProposalVisible = false;
let legacyPrintTarget = null;
let scanCurrentSettings = null;
function refreshScanButtons() {
  const target = scanState.target;
  const uncertain=['print_intent','print_uncertain'].includes((target || legacyPrintTarget)?.status);
  $('scan-prepare').disabled = busy || uncertain;
  $('scan-acknowledge').hidden = !uncertain;
  $('scan-acknowledge').disabled = busy || !uncertain;
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
function updateScanAlignmentSettings(settings) {
  scanCurrentSettings=settings;
  updateScanSavedStatus();
}
function updateScanSavedStatus() {
  const proposal=scanState.proposal;
  const sameFit=(a,b)=>['scale_x_percent','offset_x_px','scale_y_percent','offset_y_px'].every(
    key=>(a[key] ?? (key==='scale_y_percent'?100:0))===(b[key] ?? (key==='scale_y_percent'?100:0)));
  $('scan-saved-status').textContent = proposal?.applied
    ? (scanCurrentSettings && !proposal.settings.every((s,i)=>sameFit(s,scanCurrentSettings[i]))
      ? 'Strip alignment has changed since this scan correction. Manual edits replace the scan values; they do not add another adjustment.'
      : 'Saved alignment applies to photos and PNG together. Keep your layout margins as they are. A fresh printed reference is still needed to verify the physical result.')
    : `${Object.keys(scanState.strips).length} of 4 scans accepted. Accepting scans does not change placement; review and Apply saves alignment for photos and PNG together.`;
}
function showScanState(state, reveal=false) {
  const changed = state.target?.id !== scanState.target?.id || state.proposal?.id !== scanState.proposal?.id;
  scanState = state;
  if (changed) hideScanProposal();
  $('scan-target-status').textContent = state.target ? `${state.target.id} · ${state.target.status}` : 'Prepare a scan reference to begin.';
  if (!state.target && legacyPrintTarget) $('scan-target-status').textContent='An earlier reference print needs review: '+legacyPrintTarget.id;
  updateScanSavedStatus();
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
    if (!state.target) {
      const previous=await requestJson('/api/calibration-target');
      if(revision!==scanRevision || busy)return;
      legacyPrintTarget=['print_intent','print_uncertain'].includes(previous?.status) ? previous : null;
    } else legacyPrintTarget=null;
    if (revision===scanRevision && !busy) showScanState(state);
  } catch(error) { if(revision===scanRevision && !busy) {hideScanProposal();$('scan-message').textContent=error.message;} }
  finally {setTimeout(refreshScan,5000);}
}
$('scan-prepare').onclick=async()=>{
  if(busy || $('scan-prepare').disabled)return;
  if(Object.keys(scanState.strips).length && !confirm('Prepare a fresh reference? Your saved strip alignment stays in place. This starts a new set of four scans; the previous scan files are kept.'))return;
  ++scanRevision; hideScanProposal();
  const result=await toolPost('scan_prepare');
  if(result) {legacyPrintTarget=null;showScanState({target:{id:result.id,status:result.status,url:result.url},strips:{},proposal:null});}
  $('scan-message').textContent=result?'Reference prepared. Preview it, then print one sheet.':actionError;
};
$('scan-acknowledge').onclick=async()=>{
  if(busy || $('scan-acknowledge').disabled)return;
  const target=scanState.target || legacyPrintTarget;
  if(!target || !['print_intent','print_uncertain'].includes(target.status))return;
  if(!confirm('Have you checked CUPS and the physical printer? Acknowledge this reference print attempt without retrying it?'))return;
  ++scanRevision;
  const result=await toolPost('calibration_acknowledge',{id:target.id});
  if(result){
    if(scanState.target)showScanState({...scanState,target:{...scanState.target,status:result.status}});
    else {legacyPrintTarget=null;showScanState(scanState);}
  }
  $('scan-message').textContent=result?'Reference print acknowledged. No new print was sent.':actionError;
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
  $('scan-message').textContent=result?'Strip alignment saved for photos and PNG together. Prepare, print and scan a fresh reference to verify the border margins.':actionError;
};
refreshScan();
