# Saved photos, calibration and live view

The operator page shows the current saved-photo path and a link to browse completed
photos and finished sheets. Click any thumbnail to view its full-resolution file.
The current location is `/tmp/stripshot-two-cameras-hgc2l_yp/batches/`, with a
`batch-…` folder per session containing `A01.jpg`–`A08.jpg`, `B01.jpg`–`B08.jpg`,
`sheet.png`, frozen artwork and the manifest. Unfinished sessions stay in that folder.

Storage migration, destination controls, additional copies and retention machinery
have been removed. Existing photo data and recovery evidence are unchanged.

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

## Fit calibration to the strip

New finished sheets enlarge each axis only as much as its saved correction needs,
then crop within that strip. Width is 600 + 2 × |X offset| pixels; height is
1800 + 2 × |Y offset| pixels. This preserves the center translation and covers
all output pixels with scaled source content, without padding or extended colors.
Scaling each axis independently avoids unnecessary top/bottom cropping when only
horizontal correction is large, but changes the design's proportions slightly.

The operator page shows the resulting percentages. Current saved offsets
[26,16,6,-2] and Y=2 need width increases [8.67%,5.33%,2.00%,0.67%] and a 0.22%
height increase. More than 3% was explicitly selected to preserve these shifts.
The saved offsets and source artwork are unchanged. Existing completed sheets are
not overwritten; already-frozen batches retain their old rendering behavior.
Diagnostic calibration targets remain unscaled so the 20 mm gauge stays meaningful.

## Deployment and verification

A controlled application restart and one page reload are required to load changed
Python, templates and JavaScript. No live owner was restarted during development.
No physical capture or print was used to verify this update. Accepted hardware
results and all earlier evidence are preserved. Border coverage was checked in the
rendered pixels; it is not a new physical printer qualification. Native abrupt
failure, endurance, custom calibration and full OS lockdown remain unqualified.
