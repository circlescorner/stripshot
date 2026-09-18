# Hardware qualification — 2026-09-18

## Confirmed, do not repeat

Ubuntu Lenovo W541, two Nikon D3300s with SD cards. The actual software-mode
appliance completed three ordinary 8+8 batches and one interrupted/resumed batch.
Each completed four-strip sheet retained sixteen exact originals. The handoff
verified all 64 originals against persisted SHA-256 values. Those camera batches were dry runs.

Evidence: `/tmp/stripshot-two-cameras-hgc2l_yp/`.

- `batch-80e1a3596e004067ba1ab9bdad1c6bec`
- `batch-8706787ba17d49afb58a006e5c0c14b8`
- `batch-de84f688b7c543098b5b11530f773460`
- `batch-6eaac710179842c2a54591869f3c4176` (three paired rounds before Ctrl+C,
  five after restart and explicit resume; eight unique identities per camera).

Both browser previews were visibly confirmed after allowing blob images in CSP.
Preview rate approximately 2.7–2.75 FPS per camera; typical paired rounds 4.8–5.3 s,
occasionally about 6 s initially. This is not synchronized exposure timing.
The successful one-camera full-card audit remains at
`/tmp/stripshot-usb-preview-wbgpvkfk/`; do not repeat its long inventories.

## Printer discovery, host terminal

Operator reports queue `DNP_DS40` enabled, idle, accepting jobs and default;
URI `gutenprint53+usb://dnp-ds40/DS4X07015836`, Gutenprint v5.3.4.
Default PageSize `w432h576-div4`, resolution `300dpi`, RGB, Glossy,
StpiShrinkOutput Crop, StpNoCutWaste False. Reported media: 6x8 (A5),
164 native prints remaining (82%). Supply values may be cached.
Sandbox “Scheduler is not running” was not host evidence; no service changes made.

## Physical printer results

Three individually authorized synthetic jobs completed: DNP_DS40-10 (four strips,
centering error), DNP_DS40-11 (measurement target), DNP_DS40-12 (corrected target).
Operator accepted Q3 centering. Offsets +20, +15, +6, -2 px at 300 DPI; residual
center errors at most 0.35 mm in the reported middle-gauge measurements.
See CENTERING-CORRECTION.md and ds40-accepted-calibration.json for exact settings.
This acceptance applies to the synthetic target, not yet to production artwork.

## Outstanding

Separately authorized production printing;
final monitor placement/usability; native disconnect and abrupt power loss.
Subprocess SIGKILL tests use simulated cameras and do not qualify native USB.
Uncertain shutters remain held, never automatically replaced.

Application printing defaults to disabled; explicit qualified opt-in is now available.
No live kiosk capture or print was performed during development.
No SD deletion or service changes. No unattended-readiness claim. PR stays draft.

Accepted calibration is now integrated as opt-in frozen batch settings. Existing
originals were hash-checked and re-rendered without capture or physical printing.
The operator explicitly confirmed the existing down-strip photo order; it is unchanged.

## Q4 and kiosk development

The operator confirmed corrected photo job DNP_DS40-13 was centered, correctly
ordered and unclipped. The public kiosk and guarded Space trigger are implemented.
Qualified automatic printing now has an explicit startup opt-in; no live kiosk
was started by this development run. A simulated browser Space-trigger completed
one 8+8 dry-run batch and ignored extra presses during capture. Mocked live-print
integration checks one CUPS call and restart without reprint. Supervised combined
physical qualification and OS kiosk lockdown remain pending.

## Full kiosk hardware path confirmed

Operator reported the Space/Go workflow worked entirely. Saved evidence identifies
batch-3d64d259b8fb4e778541380db1fd34d9, status submitted, job DNP_DS40-14,
with no active batch. This establishes the supervised integrated run, not
indefinite endurance. No repeat of successful capture tests is needed.

Operator margin/scale controls and scoped sleep inhibitors are now implemented.
See LAYOUT-AND-UPTIME.md. New local defaults use slightly larger margins/95% photos.
No new physical capture or print was issued for this change.
