'use strict';
const $ = id => document.getElementById(id);
const screenText=(id,key,text,values={})=>{if(window.StripshotScreenText)window.StripshotScreenText.set($(id),'kiosk.'+key,text,values);else $(id).textContent=text;};
const token = document.querySelector('meta[name="stripshot-token"]').content;
let ready = false, posting = false, pending = false, beforeLast = null, last = null;
let uncertain = false;
const requestJson = window.StripshotRequestJson;
let refreshSequence = 0;
function disable() { ready = false; $('go').disabled = true; }
async function refresh() {
  const sequence = ++refreshSequence;
  try {
    const state = await requestJson('/api/kiosk/status');
    if (sequence !== refreshSequence) return;
    if (state.session_id && state.session_id !== token) { disable(); window.location.reload(); return; }
    screenText('brand','brand','MalanaphyVickWedding');screenText('mode','mode','Practice mode · no printing');screenText('go','go','Go');screenText('hint','hint','Press Space or tap Go');
    last = state.last_id;
    // Wait for server evidence of the accepted batch, not an old ready response.
    if (pending && (!state.ready || last !== beforeLast)) { pending = false; uncertain = false; }
    ready = state.ready && !posting && !pending && !uncertain;
    $('go').disabled = !ready;
    $('mode').hidden = state.printing_enabled;
    const busy = ['capturing', 'downloading', 'rendering', 'submitting'].includes(state.phase);
    $('counts').hidden = !busy;
    for (const c of ['A','B']) screenText('count-'+c,'count',c+': '+state.counts[c]+' / 8',{camera:c,count:state.counts[c]});
    if (uncertain) {
      screenText('title','uncertain_title','Please ask the attendant');
      screenText('detail','uncertain_detail','We are checking whether your session started.');
    } else if (state.phase === 'watching' && !posting && !pending) {
      screenText('title','ready_title','Have fun. Be wierd.');
      const submitted=last&&state.printing_enabled&&state.last_status==='submitted';
      screenText('detail',submitted?'printed_detail':'ready_detail',submitted?'Your photos were sent to the printer. Collect your strips below.':'Eight photos. Two cameras. Four keepsakes.');
    } else if (busy || posting || pending) {
      screenText('title',state.phase==='capturing'?'capture_title':'render_title',state.phase==='capturing'?'Look at the cameras!':'Making your keepsakes');
      screenText('detail',state.phase==='capturing'?'capture_detail':'render_detail',state.phase==='capturing'?'Keep posing — we’ll take eight photos on each camera.':'Please wait. Your session is in progress.');
    } else if (state.phase === 'starting') {
      screenText('title','loading_title','Getting ready');screenText('detail','loading_detail','Please wait a moment.');
    } else {
      screenText('title','paused_title','Please ask the attendant');
      screenText('detail','paused_detail','Your session is safely paused.');
    }
    $('hint').hidden = !ready;
  } catch {
    if (sequence !== refreshSequence) return;
    disable(); screenText('title','disconnected_title','Reconnecting');
    screenText('detail','disconnected_detail','Please wait, or ask the attendant if this continues.');
    $('hint').hidden = true;
  }
}
async function go() {
  if (!ready || posting || pending || uncertain) return;
  ++refreshSequence;
  disable(); posting = true; pending = true; beforeLast = last;
  try {
    await requestJson('/api/capture', {method:'POST', headers:{'X-Stripshot-Token': token}});
  } catch { uncertain = true; } // Never repeat an uncertain request.
  finally { posting = false; await refresh(); }
}
$('go').onclick = go;
window.StripshotSpace.bind(document, go);
async function poll() { await refresh(); setTimeout(poll, 750); }
poll();
