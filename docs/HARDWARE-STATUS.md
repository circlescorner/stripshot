# Hardware qualification — 2026-09-18

## Confirmed, do not repeat

Ubuntu Lenovo W541, two Nikon D3300s with SD cards. The actual software-mode
appliance completed three ordinary 8+8 batches and one interrupted/resumed batch.
Each completed four-strip sheet retained sixteen exact originals. The handoff
verified all 64 originals against persisted SHA-256 values. No physical print.

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

## Outstanding

Final monitor connections/placement/usability, native USB disconnect, abrupt
hardware failure/power loss, and all physical printing remain unqualified.
A real subprocess SIGKILL regression now checks restart at persisted intent and
returned-path boundaries using simulated cameras. It does not qualify native USB.
Uncertain shutters must hold and cannot be resumed or replaced automatically.

Printing remains hard-disabled in software mode. See PRINT-QUALIFICATION.md for
the proposed one-job test; explicit authorization is required before submission.
No SD deletions, service changes, physical exposures, or print submissions were
performed during this reconciliation. No unattended-readiness claim.
