# Storage, calibration and display recovery — September 19 update

This update adds always-visible operator controls. No physical capture, calibration
print, existing-batch rerun, or live-instance restart was performed for verification.
The live recovery tree remains `/tmp/stripshot-two-cameras-hgc2l_yp/`.

## Photo storage

The main recovery tree always retains originals, finished sheets, frozen artwork,
state, manifests, SHA-256 records and held batches. It is never pruned automatically.

Additional-copy settings select an existing absolute destination, a session-name
prefix (letters/numbers/underscore/hyphen), UTC-date or batch organization, original
JPEG/MPO bytes, PNG sheets, and optional JPEG strips (quality 60–100). Unique batch
IDs prevent name collisions. Settings freeze with each batch; only completed batches
are copied. Changing the extra-copy destination affects future sessions. The explicit
last-batch copy button applies current saved settings to that completed batch.

Copies use durable pending/copying/completed/failed records, validate source original
hashes, verify output hashes, refuse differing existing files, and report failures.
Interrupted copies may resume; this never submits print jobs or triggers shutters.
A missing/replaced destination is rejected by filesystem identity. Reconnect it or
save a new destination for future copies. These selected exports are additional
photo copies, not a full recovery-tree backup: they do not include all artwork,
held batches or camera ownership state.

Manual retention is a review-note control, stored durably under retention-reviews/.
It has no delete action. No retention period or automatic deletion is enabled.

## Main-storage migration

See DATA-MIGRATION.md. Scheduling a destination does not copy live state. The next
startup acquires source locks before migration and before opening any camera.
Pending migration is visible and cancellable. No actual migration was scheduled
or executed on the live tree during this update.

## Calibration

1. Save intended calibration, then Prepare calibration sheet (no print). Inspect
   its target ID, preview and frozen X/Y settings.
2. Print calibration sheet is a separate explicit one-copy action with confirmation.
   Live printing must already be authorized. The target hash is checked and durable
   print intent is recorded before calling CUPS. A target can be submitted only once.
   An uncertain result, including interrupted intent, cannot retry automatically or
   through the same print button. Inspect CUPS and the physical printer before
   acknowledging; acknowledgement never prints.
3. On the corresponding sheet, measure from each cut left/right edge to the center
   of its nearby vertical middle-gauge line, in millimeters. Measure strip 1's top
   and bottom cut edges to the center of the corresponding horizontal lines.
   The 20 mm square checks scale; no scale correction is inferred automatically.
4. Calculate displays a proposal and saves measurement history without applying it.
   X = printed X + (right − left) × 300 / 25.4 / 2; positive moves right.
   Y = printed Y + (bottom − top) × 300 / 25.4 / 2; positive moves down.
   Round the final value to the nearest pixel, exact halves to even. Reject outside
   ±60 pixels. Apply is a separate action for future sheets/dry runs only.

Accepted X remains +20, +15, +6, −2 pixels; accepted Y is zero. Q3's accepted residual
measurements were not applied again. Custom X/Y values use the explicit operator
calibration marker and remain physically unqualified. Active batches retain their
frozen printer/calibration settings. JPEG/MPO primary-frame handling is unchanged.

## Display recovery

The old fetch timeout did not bound image.decode(), leaving a plausible route to a
stranded frame loop. This was a code finding, not a reproduced hardware diagnosis.
The frame and session loops now bound the entire operation (including response body
and decoding) at two seconds. They fence stale results, decode off-screen, revoke
candidate URLs on timeout and displayed URLs on replacement/page exit, and recover
on visibility, online and page-cache restoration. Failed frames retry after 500 ms;
healthy frame cadence follows X-Preview-FPS, and session status polls every 400 ms.

The footer differentiates a fresh server preview with a stalled browser display,
server reconnection, and reported camera failure. Recovery only reads cached HTTP
endpoints; it never requests camera reconnect, worker replacement or capture.
Wedding branding, session countdown/blackout text and guest wording are preserved.
The four Waitress workers, shared asynchronous printer status and preview camera-file
buffer lifetime are unchanged. The historical generic 404 cause remains unknown.

## Deployment and qualification limits

Package replacement does not reload the running Python process. Stop the existing
owner in a controlled maintenance window, verify exit/cleanup, restart using the
existing START-KIOSK.sh command, then reload operator/monitor pages once to load the
new JavaScript. Thereafter transient display stalls recover automatically.

The old simulated 8092 service still responds; it was not stopped or treated as the
live kiosk. 8094 was unreachable. The update-only 8095/8096 render demos used no started
camera workers or printer; both were stopped and confirmed unreachable after inspection.

Established 8+8 capture, recovery and DNP DS40 results remain valid historical
evidence. Native abrupt-failure handling, long-duration endurance, new custom
calibration and full OS kiosk lockdown remain unqualified. No merge is authorized.
