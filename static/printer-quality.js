 'use strict';
let qualityMenu=null,qualityReady=false,qualityIdle=false;
function updatePrinterQualityState(state){qualityIdle=state.phase==='watching'&&!state.current&&!state.capture_busy;qualityButtons();}
function qualityButtons(){document.getElementById('quality-save').disabled=busy||!qualityReady||!qualityIdle;document.getElementById('quality-baseline').disabled=busy||!qualityReady;}
function fillQuality(values){for(const field of qualityMenu.fields)document.getElementById('quality-'+field.key).value=values[field.key];}
async function loadQuality(){
 try{qualityMenu=await requestJson('/api/printer-quality');
  if(!qualityMenu.available)throw Error(qualityMenu.error||'Controls unavailable for this driver');
  const container=document.getElementById('printer-quality-fields');container.replaceChildren();
  for(const field of qualityMenu.fields){
   const label=document.createElement('label'),title=document.createElement('strong'),select=document.createElement('select'),help=document.createElement('span');
   title.textContent=field.label;select.id='quality-'+field.key;
   for(const value of field.values){const option=document.createElement('option');option.value=value.value;option.textContent=value.label;select.append(option);}
   help.textContent=field.description;label.append(title,select,help);container.append(label);
  }
  fillQuality(qualityMenu.saved);qualityReady=true;document.getElementById('quality-message').textContent='Showing saved quality values. Changes need Save.';
 }catch(error){document.getElementById('quality-message').textContent=error.message;}finally{qualityButtons();}
}
document.getElementById('printer-quality-form').oninput=()=>{document.getElementById('quality-message').textContent='Unsaved quality changes. Save to use for future sessions.';};
document.getElementById('quality-baseline').onclick=()=>{fillQuality(qualityMenu.baseline);document.getElementById('quality-message').textContent='Baseline selected. Save to apply; alignment and other settings are unchanged.';};
document.getElementById('printer-quality-form').onsubmit=async event=>{
 event.preventDefault();if(!qualityReady||!qualityIdle||busy)return;
 const candidate=Object.fromEntries(qualityMenu.fields.map(f=>[f.key,document.getElementById('quality-'+f.key).value]));
 const result=await post('/api/printer-quality',JSON.stringify(candidate),true);
 document.getElementById('quality-message').textContent=result?'Print quality saved for future sessions. No job sent.':'Save not confirmed. '+actionError;
 if(result)qualityMenu.saved=result.saved;qualityButtons();
};
loadQuality();
