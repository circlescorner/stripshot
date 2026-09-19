# Operator preview speed

Restart with the existing START-KIOSK.sh --live-printing command and reload the
operator and both monitor pages. Under **Live preview speed**, choose the target
FPS per camera and click **Save preview speed**. Try **5 FPS** first; then try 8
or 10 only if actual FPS improves and the previews remain stable. The range is
1–15 FPS. Both cameras use the same target and their actual recent FPS is displayed.
The current 3 FPS default is preserved until the operator saves a change.

The setting applies without another restart, only while the cameras are ready
with no active batch. It is saved atomically in operator-preview.json in the data
directory and restored at startup/reconnect. Include this file in migration/backups.
The control requires operator authentication and its CSRF token in kiosk mode.
Configurations with preview disabled must enable it at startup before live adjustment.

The owning workers still perform every USB operation. Their schedule now measures
start-to-start preview intervals instead of adding a whole delay after each transfer.
The browser uses the target reported in the JPEG response rather than a fixed
200 ms delay. Browser fetches are sequential, cached frames remain bounded, and
camera commands take priority over preview requests. Unavailable previews back off
to 500 ms polling. Capture count, identities and uncertain-shutter/print protections
are unchanged; faster preview recovery can affect the time between paired rounds.

Requested FPS is not guaranteed FPS. Camera transfer time, USB bandwidth and native
live-view behavior can limit the result; higher targets also increase load/heat.
No Nikon hardware test, exposure or print was performed for this change. Sustained
native operation above the previously observed ~2.7 FPS remains unqualified.

Validation: 95 Python tests passed in 64.772 seconds, including persistence, both
workers, saved-frame response headers, configuration bounds, busy-batch rejection,
failed-save preservation, and operator authentication/CSRF. Node Spacebar regression
and both JavaScript syntax checks passed. An attempted browser check outlasted the
self-terminating demo server, so no new visual browser verification is claimed.


September 19 software update: see [storage, calibration and display recovery](STORAGE-CALIBRATION-RECOVERY.md). Existing hardware results are preserved; this update used simulated/mocked verification only and did not repeat physical capture or printing.
