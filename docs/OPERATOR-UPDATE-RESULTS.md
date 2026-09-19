# DS40 roll count and browser recovery

The operator page shows the saved-photo folder and a read-only browser for completed
originals and finished sheets. The added migration, backup and retention system was
removed. Existing data and recovery evidence remain in place.

The proposed calibration enlargement/cropping was rejected and removed. Rendering
again translates the original composite with the saved calibration; no new scaling
or edge-color extension is applied. The white-edge issue remains unresolved.
Saved calibration and frozen batches remain unchanged. An unshifted preview was
rendered separately from saved originals at the user's request; it changes no settings.

The operator Output panel now shows the DS40's remaining print count, media,
percentage and last driver-report time. Read-only CUPS verification returned
150 prints on 6×8 (A5) media, 75%. The isolated browser preview displayed those
same values. Supply reads share the existing background poll, work with printing
disabled, and never create jobs or open the printer USB device. Missing, timed-out
or failed reads show unavailable; percentages are not treated as print counts.

Browser recovery now bounds JSON bodies as well as HTTP headers for the operator,
calibration status, printer status, guest kiosk and slideshow catalog. Late kiosk
responses are fenced, uncertain actions never retry automatically, and overlapping
operator submissions are rejected. Caliper proposals are invalidated when inputs or
targets change; late responses cannot restore obsolete proposals. Disabled buttons
remain disabled after unrelated actions. README no longer claims edge filling exists.

Verification: 114 Python tests passed in 66.665 seconds. Five Node regression suites
passed, including stalled JSON bodies, failed/late kiosk status, uncertain capture,
concurrent operator submissions and obsolete caliper proposals. Printer tests cover zero/unknown counts, missing
tools, timeouts, recovery and nonblocking shared polling. Flask test-client
checks rendered operator, kiosk and slideshow pages and verified script loading order
and availability. Tests used isolated fake cameras and temporary data. No actual saved calibration, layout, artwork, originals or recovery records were
modified. After the reported power-off, `/tmp/stripshot-two-cameras-hgc2l_yp`
was absent. Preserved hardware manifests/reports remain in the previous outputs;
no replacement live data directory or restoration was performed.

No physical capture or print, live-owner restart, data relocation or merge occurred.
This is software verification, not new physical printer qualification. Native abrupt
failure, endurance, custom calibration and OS kiosk lockdown remain unqualified.
A controlled application restart and page reload are needed to load the updated package.
