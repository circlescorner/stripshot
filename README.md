> Kiosk and live-print startup: see [KIOSK.md](docs/KIOSK.md). Space starts one
> software batch; the guest page has no operator controls. Live printing requires
> an explicit opt-in with the physically accepted DS40 profile.

# Stripshot

Current stage: software capture is integrated into the appliance and tested with
simulated cameras. The next hardware test is one two-camera batch. Physical
printing defaults to disabled. Do not enable unattended startup yet.

Two Nikon D3300s each take eight software-triggered photographs. Stripshot saves
and validates those exact sixteen JPEGs, renders four independently overlaid
strips, and produces one 2400 × 1800, 300 DPI sheet. All SD files are kept.
Computer-driven USB previews feed `/view/A` and `/view/B` on the W541 monitors.

## Next hardware test — one command

Stop the previous diagnostic/application, connect both D3300s with their working
USB cables and SD cards, and disconnect the intervalometers. Select JPEG capture
on both cameras; a returned RAW path deliberately holds the batch for review.
From this application directory, run in the Ubuntu terminal:

```bash
bash test-two-cameras
```

Open **http://127.0.0.1:8090/**. The launcher discovers current USB addresses, assigns
A/B by serial number, prints that mapping, and starts the actual appliance dashboard.
Open both monitor links, confirm that both views move, then click **Take 8 + 8
photos** once. This takes sixteen new photographs. No shots occur just from
launching the application. No historical SD-card scan runs.

The expected result is 8/8 per camera during capture, a completed four-strip sheet,
and moving previews again. Counters return to zero after completion. The last sheet
says **Your sheet is ready** with **Dry run — no paper used**. Upload the four PNGs
before starting if you want this batch to use your artwork. Each batch freezes its
own overlay copies, layout and print configuration at the start.

A successful code result does not prove usable monitor placement, subject framing,
physical preview recovery, or synchronized shutters. Observe those on the hardware.
Only take another batch when the first result is understood; no repeated full-card
audits are needed to re-establish the successful one-camera qualification.

The terminal prints an evidence directory, normally `/tmp/stripshot-two-cameras-*`:

- `state.json`: durable active/last batch and per-shot records.
- `batches/<id>/`: the exact sixteen originals, frozen overlays, sheet, preview,
  and final manifest.
- `report.json`: latest phase, counters, preview FPS and batch details.
- `cleanup.json`: whether workers exited and camera cleanup reported success.
- `qualification-config.json`: stable camera binding and disabled printing.

Ctrl+C ends the test. Reuse the printed directory for restart qualification:

```bash
bash test-two-cameras --data-dir /tmp/stripshot-two-cameras-EXACT_DIRECTORY
```

Restarting an interrupted capture **never automatically fires another shutter**.
The dashboard holds the batch for review. A fresh launcher run without `--data-dir`
creates a separate evidence directory; it does not recover the previous batch.
Do not run two applications against the same cameras. If cleanup reports a live
worker or failed USB release, ensure the old process has exited before restarting.

## What has actually been qualified

The successful one-camera full audit is retained at
`/tmp/stripshot-usb-preview-wbgpvkfk/report.json`: eight commands returned
DSC_0435.JPG–DSC_0442.JPG, all eight downloaded and decoded, preview recovered after
each shot, and a fresh-session complete inventory matched exactly those eight new
JPEG identities. That audit should not be repeated just to confirm the same result.

The actual two-camera appliance has completed repeated 8+8 batches, with visible
preview recovery and controlled Ctrl+C/restart/explicit resume confirmed. Preview
rates were about 2.7–2.75 FPS and typical paired rounds 4.8–5.3 seconds. See
[hardware status](docs/HARDWARE-STATUS.md) for exact evidence and remaining limits.
Abrupt native failure, final monitor placement, and the combined live kiosk workflow remain
unqualified. No additional ordinary capture batch is needed.

The legacy single-camera diagnostic remains available through `test-preview`.
Its eight-shot mode defaults to exact-file verification; `--full-card-audit` opts
into the long historical inventory and fresh-session audit. The new appliance
checks exact returned identities; it does **not** claim that no unrelated photos
were taken elsewhere on the cards.

## Durable software capture and recovery

`camera_mode: "software"` uses one persistent owning worker per camera. Browser
preview requests use cached JPEGs and never open camera sessions. Each paired round
requests one shot from A and B concurrently; no tight shutter synchronization is
claimed. Each worker stops live view, verifies Card and Memory-card capturetarget,
fsyncs the shutter intent, calls capture exactly once, saves the returned path,
identifies and downloads the exact JPEG, decodes it, and restarts preview. The
prior capturetarget is restored in `finally`.

Two additional preview frames must arrive within three seconds before the next
round. Frames may disappear during shutter/download; stale frames are hidden.
Native USB calls cannot be interrupted by a thread flag. A timeout holds the batch
and does not permit replacement shots. The dashboard reports recent measured FPS;
manifests contain intent/return timestamps, round duration and preview frame counts.

- **Interrupted capture:** startup holds it for operator review. Resume accepts
  saved exact identities and previously unissued slots only. Identified files are
  rechecked/downloaded without another shutter. A saved intent lacking full file
  identity is ambiguous and cannot be resumed automatically, even if a path exists.
- **Abandon held batch:** archives its records and keeps every SD/local file. It
  does not complete, print, or fire replacements for that batch. A new batch needs
  a separate explicit start. Preserve uncertain files for manual investigation.
- **Preparation failure:** retry/restart can re-download exact saved identities.
  Local copies are checked against saved SHA-256 hashes. Modified/missing camera
  files stop recovery. No other photos are substituted.
- **Reset next 16:** available between batches. Software mode has no external-file
  pending queue, so reset does not scan or delete anything. It cannot erase an
  active/uncertain batch.
- **Printer uncertainty:** the original durable print-intent protection remains.
  An uncertain CUPS submission never automatically retries. Software-mode printing
  requires explicit qualified opt-in; both current and recovered batch settings
  are validated. See docs/KIOSK.md for the accepted DS40 launch profile.

Software mode uses a distinct saved-state binding. Existing external-event data is
not silently reinterpreted. Use `config.software.example.json` and a separate data
directory. Preserve old data/configuration/artwork; copy intended overlays into the
new data directory or upload them using the dashboard. The launcher never edits the
old snapshot or its configuration.

Atomic JSON saves fsync both file and directory. A process lock protects each data
directory. No automatic SD deletion, local retention cleanup or formatting exists.
Keep cards in place through recovery; use a new data directory when changing cards.
Since software mode avoids historical inventory, it does not detect replacement of
an idle card by comparing all its old contents.

## Install / normal application entry point

The hardware launcher uses Ubuntu `python3-gphoto2`, `python3-flask`, and `python3-pil`.
It runs a local Werkzeug server for qualification only. For the normal Waitress app:

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
cp config.software.example.json config.json
.venv/bin/python app.py --discover
```

Put the serials into `config.json`, leave printing disabled, then run:

```bash
.venv/bin/python app.py --config config.json
```

The normal dashboard defaults to **http://127.0.0.1:8080/**. Open `/view/A` and
`/view/B` in separate browser windows, move them to the monitors and select Full
screen. USB addresses are rediscovered on launch; serials define A/B.

Leave `gvfs-gphoto2-volume-monitor.service` masked as already configured. No changes
to unrelated GVFS services or AppArmor are needed. Do not enable the supplied user
service until hardware qualification is complete.

## Demo and legacy external capture

`python3 tools/qualify-two-cameras --demo` runs the new workflow using local fake
cards. It requires a local server socket. `app.py --config config.demo.json` retains
the original event-based demo and **Simulate 8 + 8 photos** control.

Legacy `camera_mode: "events"` and `"poll"` remain supported for existing state and
regression testing. They inventory historical files, collect external arrivals,
retain overflow, and reconcile offline arrivals. They are not the chosen D3300 USB
preview workflow: physical intervalometers did not fire while USB control was active.

## Layout and artwork

| Strip | Photo order, top to bottom |
| --- | --- |
| 1 | A1, B1, A2, B2 |
| 2 | A3, B3, A4, B4 |
| 3 | A5, B5, A6, B6 |
| 4 | A7, B7, A8, B8 |

Upload four independent **600 × 1800 transparent PNGs**. Artwork is composited over
EXIF-oriented, center-cropped photos. The full sheet is **2400 × 1800 at 300 DPI**,
a landscape 8 × 6 inch image for one 6 × 8 sheet. Nikon JPEG/MPO downloads retain
original bytes; rendering uses the full-resolution primary image, not thumbnails.

**Strip alignment — photos + PNG** fits the finished composition to the paper.
Photos are laid out and the full PNG is composited first; one saved scale/offset
then moves both together. Use four separate 300/600-DPI flatbed scans of a numbered
reference to measure the paper edges, review the outlines and apply. The manual
controls under Advanced edit the same values. No PNG artwork is cropped.

Keep **Photo layout** margins and gaps as they are unless changing the design
inside a strip. Separate photo centering is no longer used for new sessions.
**Preview with saved photos** renders the combined result without capture or print.
Existing scans, uploads, originals, settings and finished sheets are preserved;
old unfinished batches retain their frozen rendering rules. See
[how the controls fit together](docs/STRIP-ALIGNMENT.md) and
[the scan instructions](docs/SCAN-ALIGNMENT.md). Print and scan a fresh reference
to verify physical accuracy; software checks do not establish cutter repeatability.

The operator's top panel also offers **Stop Stripshot** and **Restart Stripshot**.
Restart preserves the runtime printing mode and saved settings, then reloads the
page. Stop closes the booth; the desktop icon starts it again. Both require
confirmation and no active/held session. See [application controls](docs/APPLICATION-CONTROLS.md).

The host DS40 queue and available media/cutting options have been identified;
[physical qualification](docs/PRINT-QUALIFICATION.md) remains pending explicit authorization. No print
or PR merge is authorized by this development handoff.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Tests cover exact batches, uploads/layout, simulated paired capture, repeated
batches, intent durability, uncertain-shutter holds, restart without extra shutters,
exact-file recovery, preview recovery, MPO decoding, borrowed buffer lifetime,
scan cancellation, and duplicate-print protections. They do not qualify hardware.

## Historical DS40 centering

New sessions use [whole-strip alignment](docs/STRIP-ALIGNMENT.md). The offsets
below remain in historical settings and frozen legacy batches; they no longer
shift new photos separately.

The operator accepted the corrected synthetic target on the tested DNP_DS40.
Use `config.ds40.software.example.json` for its per-strip offsets and tested
media/orientation options; fill in the camera serials and data directory.
Printing is still disabled. Generic configurations default to zero offsets.

For the qualification launcher, add `--ds40-calibration` to use the accepted
profile for new dry-run batches (including when reusing an evidence directory):

```bash
bash test-two-cameras --data-dir /tmp/stripshot-two-cameras-hgc2l_yp --ds40-calibration
```

This flag applies for that launch; include it again on subsequent launches for
new batches. Existing held batches retain their own frozen settings, even if the
profile or configuration changes. Old manifests without offsets render as before.
Do not run this alongside another camera-owning process.

The correction moves photos by +20, +15, +6, -2 pixels, clips photographs within
each strip and adds white at the exposed edge. PNGs are placed afterward using
their own scale/offset settings, so calibration cannot crop any PNG edge. Uploaded
art and original photos remain untouched. The dashboard preview shows the same
corrected sheet that the print path would use. Photo order remains A1,B1,A2,B2
down strip 1, A3,B3,A4,B4 down strip 2, and so on, as the operator requested.

Software-mode print gates and durable print-intent protection remain intact.
A production sheet has been rendered from existing originals without new
captures; the operator accepted its physical output as job DNP_DS40-13. No unattended readiness claim.

The formerly unconditional software print gate now permits explicit qualified
opt-in; the kiosk guide describes the exact flags and recovery constraints.
The default examples and qualification launcher still do not print.

## Photo margins and continuous operation

The operator can save side/top/bottom margins, photo gaps (millimeters) and photo
size (50–100%) for future batches. Settings persist across restarts and active
batches retain their frozen values. See [layout and uptime](docs/LAYOUT-AND-UPTIME.md).
Kiosk startup inhibits OS idle/sleep for the process lifetime; application sessions
have no scheduled expiration. Hardware faults/resource exhaustion still hold for
operator intervention. The integrated physical Space-to-print run is now confirmed.

### Wedding setup and camera recovery

Guest/monitor branding, independently selectable strip positions, serial-verified
reconnect, and nonblocking dashboard polling are described in
[the update notes](docs/WEDDING-RECOVERY-UPDATE.md). Preferred alternating A/B order
remains the default; duplicate/omitted selections are rejected.

[Live preview speed](docs/PREVIEW-SPEED.md) can now be saved in the operator dashboard
(1–30 FPS target for both cameras, with actual FPS shown). Start with 5 FPS; hardware
may deliver less than the requested rate. Change only between batches.

[Operator preview and slideshow](docs/OPERATOR-PREVIEW-AND-SLIDESHOW.md) documents the
paper-free rerender button, visible strip calibration, configurable slideshow with
arrow keys/shuffle, and session-aware monitor messages with a real photo countdown.

The operator page shows the saved-photo folder and a read-only photo/sheet browser.
[Calibration and live view](docs/CALIBRATION-AND-LIVE-VIEW.md) describes caliper controls, saved translation offsets and automatic display recovery.

The operator Output panel displays the DS40’s last reported remaining print count,
media, percentage and report time. Supply reads require `cups-ipp-utils` and never
submit a print job. See [printer status details](docs/CALIBRATION-AND-LIVE-VIEW.md#ds40-remaining-prints).

[Desktop startup and page links](docs/DESKTOP-START.md) describes the desktop launcher,
operator navigation and the fresh local photo collection.


### Current Operator controls

- [Printer quality](docs/PRINTER-QUALITY.md): saved DS40 brightness, contrast,
  saturation and channel tone, with a quality-only baseline.
- [Guest screen text and countdown routing](docs/SCREEN-TEXT.md): per-message
  wording/style, and a choice of Camera A or B for 3, 2, 1.
- [Photo and sheet review](docs/PHOTO-REVIEW.md): bounded thumbnails, keyboard
  review, cached slideshow windows and full-resolution access.
- [Measured white-edge refinement](docs/STRIP-ALIGNMENT.md#final-adjustment-from-measured-white-edges):
  a review-only proposal into the same common strip alignment, without cropping.
- [Preview speed](docs/PREVIEW-SPEED.md): up to 30 requested FPS; existing choice
  preserved and actual camera-frame FPS shown.
