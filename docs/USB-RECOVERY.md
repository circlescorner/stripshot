# USB-disconnection recovery

## Incident evidence and limits

The reported trigger was unplugging and reconnecting both camera USB connections.
Operator Restart did not recover the booth, and the desktop launcher reported an
occupied kiosk port. The user reports recovery after releasing the cameras'
shutters and trying again. This observation does not establish a manual recovery
procedure or identify the underlying software fault.

The retained runtime log shows a restart refused by `ApplicationControl.finish()`
because camera cleanup was incomplete. It does not record the individual cleanup
operation or establish which process owned the port during the incident. Neither
an orphan process nor a permanently broken Restart control has been established.

Read-only inspection on September 19 found one application process, two connected
cameras with fresh previews, no active/held batch, and **live printing enabled**.
Development did not restart that booth or alter its installed files, printing mode,
settings, scans, snapshots or saved photos. No USB manipulation, shutter release,
physical capture, print, or scan correction was performed.

## Changes supported by isolated reproduction

- The old camera adapter propagated a setting-restoration error even after native
  `exit()` succeeded. Workers treated that as unconfirmed USB release, preventing
  reconnection/restart. Settings warnings are now recorded separately from failed
  release; a new camera must still pass the existing Card/preview checks. A failed
  or blocked native exit continues to prevent a replacement worker.
- Operator Stop/Restart now closes capture admission, waits for the coordinator
  and camera workers, and retains the HTTP server and data lock during cleanup.
  Operator reports the camera and operation it is waiting for. If a blocked call
  returns and releases successfully, the accepted action continues automatically.
  If USB release fails, no replacement is started; the existing process must be
  exited from its terminal before relaunching. Do not clear its lock file.
- Restart checks the coordinator as well as all workers, closes the server, and
  replaces the same process with the current live/dry printing flag. The data lock
  remains held until exec closes the descriptor. Another startup must acquire that
  lock before opening cameras. Active/held batches still refuse both controls.
- Startup reserves its listening socket **before camera discovery**. A conflicting
  port prevents camera access even when the requested data directory is different.
- The desktop port probe now uses the server's `SO_REUSEADDR` policy. An isolated
  server-close reproduction made the old probe fail with `EADDRINUSE` solely due
  to recent connections; the updated probe succeeded. This is a confirmed possible
  false alarm, not proof of the incident's cause.
- An actual occupied port reports listener PID/program when the OS exposes it,
  the Operator URL, and guidance to inspect the existing terminal. A failed HTTP
  probe never establishes that a process is orphaned. The launcher never kills it.
  If the server becomes ready during the probe, only its Operator page is opened.
- Camera errors now log the worker operation, adapter stage, and cleanup outcome.
  Operator status includes these details. A page reload retains pending shutdown
  status; prolonged restart disconnection points to the existing terminal.

## Validation and remaining physical check

Mocked native calls cover USB loss, successful release after a settings failure,
failed release, and blocking cleanup. Tests assert no replacement/shutter while
blocked, ownership retained, coordinator completion required, and held-batch
refusal. Existing tests check serial-matched reconnection without touching the
healthy camera, uncertain-shutter preservation, and live/dry restart flags.

An isolated simulated-camera process kept HTTP and its ownership lock while its
camera close was blocked. Releasing the test gate completed Restart with the same
PID, new instance ID, unchanged saved files/settings and printing mode; Stop then
exited cleanly. No production camera or data directory was used.

Real USB-loss recovery remains unqualified. A future attended test must be planned
when the booth is not needed, with no active/held batch, retained logs and current
mode recorded. Native driver calls that never return remain a limitation of the
thread-based camera design: the application deliberately does not create another
camera owner to work around them. The current healthy booth was left running.
