# Wedding branding, photo order and safe recovery — 2026-09-18

## Operator behavior

The guest brand is exactly `MalanaphyVickWedding`; the ready heading is exactly
`Have fun. Be wierd.`. Both monitor pages show the brand in a reserved top band,
leaving the entire camera frame visible. This does not alter photographs or artwork.

Each strip has four independent top-to-bottom selectors in the operator layout form.
Defaults remain A1,B1,A2,B2 / A3,B3,A4,B4 / A5,B5,A6,B6 / A7,B7,A8,B8.
All sixteen photographs must be used exactly once. Duplicate or omitted selections
are rejected, never silently rearranged. Save is atomic in operator-layout.json;
ordering is frozen with the layout at batch start. Existing manifests without
photo_order use the original default ordering. The larger-margin preset preserves
an edited order. Saved artwork captions reflect the saved order.

## Camera ownership and recovery

Software mode continues to use one persistent owning worker per camera. With
preview_fps enabled, preview traffic keeps the sessions active; a viewfinder check
at most every five seconds restores preview when it has stopped, using the existing
Card destination checks. It issues no native shutter and never inventories old files.
This is a keepalive attempt, not a promise against Nikon thermal/power limits.
When preview_fps is zero this preview keepalive is disabled.

An idle disconnect can automatically reconnect (auto_reconnect defaults true).
Retries wait 30 seconds after failure. Held batches require the operator's
**Reconnect cameras — no photos** action, followed by a separate explicit resume
when the saved shutter records permit it. Reconnect does not change batch records,
issue shutters, submit prints, or unhold a batch. Returned-path-only and uncertain
intent records remain non-resumable. Known identities must still match on resume.

A replacement worker starts only after failed workers have exited, cleanup succeeded,
all owning workers completed opening, and capture futures have settled. Recovery
re-enumerates ports and verifies the configured serial, skipping ports owned by a
healthy or still-running worker. Stale ports of fully stopped failed workers are
not reserved, allowing both cameras to change USB addresses. A serial mismatch is
closed before trying another candidate. Unconfirmed cleanup blocks replacement.
A reconnect open exceeding 120 seconds reports a fault; its worker stays reserved.
Do not start another owner to work around a stuck native call. Check connections and
perform a controlled restart after the old process has exited.

Startup failures that stop the coordinator still need a restart. Uncertain print
submissions remain held; acknowledge only after checking CUPS and physical output.
The printer options, offsets +20,+15,+6,-2, durable intents and exact-file recovery
remain unchanged. No automatic retry of a native shutter or CUPS job was added.

## HTTP warnings

The historic generic `Request failed: 404 Not Found` contains no URL, and no saved
request log was available to identify it conclusively. A read-only request to the
old running kiosk's /favicon.ico returned 401, not 404; therefore favicon is not a
verified explanation of that warning. The update serves /favicon.ico as 204 and
logs method and path on every request failure. Requests taking at least one second
also log method, path, duration and response status (never credentials or tokens).
The dashboard avoids requesting a missing last-sheet preview, such as an acknowledged
print whose preview artifact is absent.

Waitress stays at four HTTP workers. Previews serve cached JPEG bytes and never call
USB. Each monitor polls sequentially. Dashboard refresh now rejects overlap from
its action-completion and regular poll paths. Printer status previously ran lpstat
synchronously for up to five seconds on each HTTP request; it now shares one bounded
background read, cached for fifteen seconds. Queue-depth warnings alone neither prove
capture failure nor justify more workers. Slow actions and disk fsync can still delay
requests; use the new path/duration logs if warnings recur.

## Validation and qualification limits

The 91-test suite passed; nine focused recovery/ordering tests cover frozen/persistent
ordering, actual render pixels including legacy defaults, serial mismatch rejection,
healthy-port exclusion, cleanup/live-worker/pending-capture guards, idle recovery,
held uncertain-batch preservation, and shared nonblocking printer polling. Native
camera and CUPS operations in these new tests are mocked/simulated. Node Space-key
regression passed. Browser checks confirmed custom save/reload, rejected duplicates,
both visible simulated previews, and exact guest branding. A 15-second HTTP check with both preview pages plus dashboard/guest/printer polling
made 198 additional requests with zero errors, maximum 38.81 ms, and no queue-depth
warnings. This measured simulated idle load, not a hardware capture or endurance run.
No new physical exposure,
print, USB disconnect, service change or SD deletion was performed.

Prior hardware success remains valid: the full kiosk-to-camera-to-DS40 run was
confirmed for batch-3d64d259b8fb4e778541380db1fd34d9 / DNP_DS40-14. New keepalive and
reconnect behavior still need supervised native disconnect/endurance observation
when separately scheduled. Abrupt power loss, indefinite uptime, unattended operation
and OS kiosk lockdown are not qualified. Do not repeat the already successful batches.

## Activate the update

The delivery package is updated; the existing live server is not restarted by this
change. At an idle point, stop the old launcher with Ctrl+C and wait for cleanup and
process exit, then run the same START-KIOSK.sh --live-printing command. Reload the
operator, guest and both preview pages before using the new controls. Do not open a
second launcher while the old owner is running. Operator password remains private.
