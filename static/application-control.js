'use strict';
let applicationInstance = null, applicationPending = null;
function updateApplicationControls(state) {
  applicationInstance = state.instance_id;
  if (applicationPending && state.instance_id && state.instance_id !== applicationPending.instance) {
    window.location.reload(); // Refresh CSRF tokens and all saved controls after restart.
    return;
  }
  if (applicationPending?.failed && !state.application_control_action) applicationPending = null;
  for (const action of ['stop','restart']) $('application-'+action).disabled = busy || Boolean(applicationPending) || !state.application_control_available;
}
function applicationDisconnected() {
  for (const action of ['stop','restart']) $('application-'+action).disabled = true;
  if (!applicationPending) return;
  $('phase').textContent = applicationPending.action === 'stop' ? 'Stripshot is offline' : 'Restarting Stripshot';
  $('phase-detail').textContent = applicationPending.action === 'stop'
    ? 'Use the desktop icon to start Stripshot again.' : 'Waiting for the booth to return…';
}
for (const action of ['stop','restart']) $('application-'+action).onclick = async () => {
  if (busy || applicationPending || $('application-'+action).disabled || !applicationInstance) return;
  const prompt = action === 'stop'
    ? 'Stop Stripshot? The cameras and booth will close. Use the desktop icon to start it again.'
    : 'Restart Stripshot now? The booth will briefly disconnect, then return with its current printing mode and saved settings.';
  if (!confirm(prompt)) return;
  applicationPending = {action, instance:applicationInstance, failed:false};
  $('application-message').textContent = action === 'stop' ? 'Stopping Stripshot…' : 'Restarting Stripshot…';
  const result = await post('/api/application-control', JSON.stringify({action}), true);
  if (result) $('application-message').textContent = action === 'stop'
    ? 'Stop accepted. Use the desktop icon to start Stripshot again.'
    : 'Restart accepted. This page will reload when Stripshot returns.';
  else {
    if (applicationPending) applicationPending.failed = true;
    $('application-message').textContent = 'Request not confirmed. Checking booth status; no automatic retry. '+actionError;
  }
};
