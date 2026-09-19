# Saved photos, calibration and live view

The operator page shows the current saved-photo path and a link to browse completed
photos and finished sheets. Click any thumbnail to view its full-resolution file.
The previously used location was `/tmp/stripshot-two-cameras-hgc2l_yp/batches/`, with a
`batch-…` folder per session containing `A01.jpg`–`A08.jpg`, `B01.jpg`–`B08.jpg`,
`sheet.png`, frozen artwork and the manifest. Unfinished sessions stay in their session folder. After the reported power-off on
September 19, the old `/tmp/stripshot-two-cameras-hgc2l_yp` directory was absent.
Preserved hardware manifests and reports remain in the existing deliverables;
the user subsequently requested a fresh session. New photos will be saved under
`/home/m/Pictures/Stripshot/batches/`; old photos were not imported or deleted.
No camera-owner restart was performed during development.

Storage migration, destination controls, additional copies and retention machinery
have been removed. Existing photo data and recovery evidence are unchanged.

## DS40 remaining prints

The operator's Output panel shows prints remaining on the roll, media type,
percentage remaining and the time of the last driver report. It polls CUPS every
15 seconds without blocking the dashboard, including when printing is disabled.
The count comes from Gutenprint's `marker-message`; `marker-levels` is a percentage
and is never converted into a guessed print count. With 6×8 media, one count is
one 6×8 sheet (four finished strips), not one individual strip.

This is the last count reported to CUPS, typically updated by normal printing.
A roll change may not appear until the driver next reports supplies. The panel
shows the report time rather than claiming a fresh hardware reading. Missing
counts, failed reads and disconnections show unavailable, not zero.

The only supply operation is IPP Get-Printer-Attributes, using `ipptool` from
Ubuntu's `cups-ipp-utils`. It does not submit a job or claim the printer USB device.
A read-only check on September 19 returned 150 remaining, 75%, on 6×8 (A5) media.
See [CUPS supply attributes](https://openprinting.github.io/cups/libcups/spec-ipp.html)
and the [Gutenprint maintainer's DS40 reporting explanation](https://sourceforge.net/p/gimp-print/discussion/4359/thread/e678f457ba/).

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

September 19 live diagnosis on port 8090 reproduced `TypeError: Illegal invocation`
in `ResilientLoop.tick` and `wake`: native Window timer functions were stored on the
loop and called with the loop as their receiver. This stopped browser polling even
while both camera workers reported about 15 FPS. Both cached JPEG endpoints returned
HTTP 200 in about 1 ms. Wrapping the default timer calls fixes their receiver without
changing camera ownership or frame handling. The regression test now models browser
receiver restrictions that Node timers do not enforce.

After installing the static JavaScript and reloading the two test browser pages,
both displayed continuously refreshed decoded 640×424 frames with no new console
errors. The existing Firefox camera windows need a reload (Ctrl+R). No server restart
is needed for this static-only fix. The live process on 8090 stayed running; no camera
reconnect, shutter, print, calibration or artwork change was performed. GTK messages
and the isolated queue warning were not the cause of this reproduced failure.


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

The operator dashboard, printer status, calibration status, guest kiosk and slideshow
catalog now bound both HTTP headers and JSON body decoding. A timed-out read resumes
normal polling; no action request is automatically repeated. Older kiosk status
responses cannot overwrite a newer response or a newly started session. An uncertain
capture remains blocked until server status supplies evidence of that session.

Caliper proposals are cleared when measurements or the selected target change.
Late measurement/status responses cannot restore an obsolete proposal. Operator
forms reject concurrent submissions, and completing another action preserves disabled
controls instead of enabling every button.

## Border preservation

PNGs must never be cropped. Each PNG now has its own horizontal width percentage
and horizontal offset in the operator panel. Scale is 10–100%, centered before
applying the offset. Vertical fit controls provide the same fitting for height.
Only offsets that keep the entire
resized 600-pixel-wide source canvas within its strip are accepted. For example,
90% width permits offsets from -30 to +30 pixels. The form shows the allowed range,
and the renderer independently rejects any out-of-bounds placement.

Calibration now translates the photos before compositing the full PNG. Neither X
nor Y calibration can clip PNG edges. Saved calibration numbers are retained, but
their effect on artwork is replaced by the independent PNG controls. Source PNGs,
original photos and already rendered sheets are not rewritten. There is no automatic
enlargement, edge-color extension or hidden fitting. Changes are saved in
`operator-overlays.json`, frozen into each new batch and recorded in dry-run manifests.
The [scan-alignment workflow](SCAN-ALIGNMENT.md) calculates PNG fitting from four
separate flatbed scans of a numbered reference print, with review before applying.
This guarantees complete artwork in rendered files; physical edge/cut qualification
has not been repeated.

## Deployment and verification

Earlier Python/template updates require a controlled application restart. The
September 19 timer correction only requires reloading the camera pages. No live owner was restarted during development.
No physical capture or print was used to verify this update. Accepted hardware
results and all earlier evidence are preserved. No new physical printer qualification is claimed. Native abrupt
failure, endurance, custom calibration and full OS lockdown remain unqualified.
