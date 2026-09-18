# Stripshot

A small, unattended photo-strip appliance for two Nikon D3300 cameras and one
DNP DS40. Intervalometers take the photographs; the cameras feed their HDMI
monitors directly. Stripshot observes new SD-card JPEGs, waits for **8 from A and
8 from B**, downloads those exact files, renders four strips, and submits one sheet.

There are no software shutter commands, camera-setting writes, preview requests,
SD-card deletions, guest sessions, or countdowns.

## Run the demo

Python 3.10 or later on Linux:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py --config config.demo.json
```

Open **http://127.0.0.1:8080** and click **Simulate 8 + 8 photos**. The demo creates
JPEGs on two local simulated cards, sends them through the same batch/render
pipeline, and shows the finished sheet. It cannot enable physical printing.
Demo state lives in `demo-data/`, completely separate from live state.

The dashboard includes camera counts/status, four overlay previews/uploads,
**Reset next 16**, the last sheet, and CUPS queue status. It uses local assets only.
An empty overlay slot displays a layout illustration; no artwork is applied to
the actual output until a PNG is uploaded.

## Install on the W541

From the repository directory:

```bash
sudo apt update
sudo apt install python3-venv python3-gphoto2 gphoto2 cups-client
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
cp config.example.json config.json
```

The system-site-packages flag exposes Ubuntu's libgphoto2 Python binding inside
the virtual environment. The DS40's CUPS queue and appropriate printer driver
must already be installed. Stripshot does not install or change the driver.

### 1. Qualify USB and HDMI together

Stop any other camera software or automatic photo importer. Insert both SD cards,
connect the intervalometers, connect USB and HDMI, and enable HDMI live view.
With Stripshot stopped:

```bash
bash tools/qualify-usb-events
```

Trigger one physical 8+8 sequence during its 60-second observation window. Confirm
both cameras take all eight photographs and HDMI remains usable. The script only
observes events. It does not download, delete, set configuration, or trigger a shot.

**Hardware qualification is still required.** The code cannot establish that a
D3300 supports the desired HDMI/accessory-port behavior while PTP stays open.
Holding USB open is a strategy to test, not a guarantee of HDMI keep-awake.

### 2. Assign stable camera identities

With other observers stopped:

```bash
.venv/bin/python app.py --discover
```

Copy the two serial numbers into `cameras.A.serial` and `cameras.B.serial` in
`config.json`. Camera identity is checked again when each persistent worker opens
its connection. USB port numbering may change without swapping A and B.
Discovery reads configuration; it never writes it. If a camera cannot provide a
serial number, startup fails instead of guessing which camera it is.

### 3. Run a live-camera dry run

Keep `printer.enabled` set to `false`:

```bash
.venv/bin/python app.py --config config.json
```

Wait for **Ready for the moment** before taking photos. Existing files on the
first startup become the baseline; they are not printed. Trigger the intervalometers
once. Verify the counters, the completed preview, and all sixteen originals under
`data/batches/<batch-id>/`.

`camera_mode: "events"` uses persistent libgphoto2 file-added events. If the hardware
qualification shows missing events, set `camera_mode: "poll"` and restart. Poll mode
reads recursive SD file lists at `poll_seconds` intervals while keeping the same
camera connection open. It is intentionally slower and must also be qualified.
There is no automatic mode switch or repeated USB reconnect loop.

### 4. Qualify the printer, then enable printing

```bash
lpstat -p -d
lpoptions -p YOUR_DS40_QUEUE -l
```

Set `printer.queue` to the actual queue name. Set `printer.options` to the exact
media, orientation, and cutting option names/values reported by your installed
driver. For example, each `"OptionName": "Value"` becomes `-o OptionName=Value`.
No guessed DS40 option names are shipped. Leave printing disabled until the queue
is configured. Restart the app after editing configuration.

The render is **2400 × 1800 pixels at 300 DPI**, landscape 8 × 6 inches, with four
600 × 1800 strips side by side. Physically this is one 6 × 8 sheet. Verify rotation,
scale, border handling, color and 2-inch cutting on a real sheet with your driver.
Then set `printer.enabled` to `true` and restart for unattended operation.

Every job uses an explicit queue, one copy, and a batch-specific title. A dashboard
status of **submitted** only means `lp` returned a CUPS job ID; it does not claim that
paper has emerged. Driver/spooler behavior is outside Stripshot's at-most-once
submission guarantee.

## Layout and overlays

| Strip | Photo order, top to bottom |
| --- | --- |
| 1 | A1, B1, A2, B2 |
| 2 | A3, B3, A4, B4 |
| 3 | A5, B5, A6, B6 |
| 4 | A7, B7, A8, B8 |

Upload four independent **600 × 1800 PNGs** with transparent photograph areas.
Opaque PNGs and other dimensions are rejected. Bake text into the PNG. Photos
are EXIF-oriented and center-cropped to their slots, then artwork is composited
over them. White margins and an empty footer remain when no overlay is supplied.

The `layout` configuration is in pixels: `margin` is left/right padding, `gap`
separates the four photos, and `top`/`bottom` reserve vertical space. Defaults are
24, 18, 24 and 180. Changes take effect after restart. Each batch snapshots its
overlays, layout, and printer settings so preparation retries keep the same output.

## Recovery and operation

- **Partial batch:** counts and exact file identities survive restart. New files
  taken while the application was stopped are reconciled on startup. Duplicate
  events are ignored. Extra arrivals are retained for the following batch.
- **Reset next 16:** while watching, establishes fresh snapshots of both cameras
  and clears pending counts. Do this between intervalometer sequences. No files
  are deleted. Reset is unavailable during batch processing.
- **Downloads/render failure:** no print has been attempted. Inspect the error;
  retry preparation where possible, or correct the problem and restart. Originals
  must remain on both cards for recovery.
- **Uncertain print:** a durable print-intent record is written before invoking
  `lp`. Timeout, ambiguous output, or restart after that point holds the batch.
  Inspect CUPS and the physical printer, then acknowledge in the dashboard to
  continue **without resubmitting that batch**. There is no automatic reprint.
- **Camera disconnect:** the application pauses; correct the connection and
  restart. It does not repeatedly seize/release USB or silently switch cameras.
- **Card replacement/format:** stop the application between batches. Archive the
  old data directory and configure a new one. Saved pending files missing from an
  SD card, a completely changed baseline, corrupt state, or mismatched camera
  bindings stop startup. Do not delete `state.json` to clear a print error.
- **Disk space:** originals, sheets, artwork snapshots and manifests are kept.
  Archive completed batches between events. No automatic deletion is implemented.

`state.json` is the source of truth and is replaced atomically with file and
directory fsync. Batch directories include a human-readable manifest. A process
lock prevents two instances from sharing the same data directory. Run only one
live instance against the cameras and printer.

## Start at login

The supplied systemd **user** unit assumes the repository is `~/stripshot`:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/stripshot.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now stripshot
journalctl --user -u stripshot -f
```

Edit the unit's paths if cloned elsewhere. Configure and qualify manually before
enabling the service. It starts when the user manager starts (normally at login).
It deliberately does not restart repeatedly on camera failure. To restart:

```bash
systemctl --user restart stripshot
```

The dashboard binds to loopback by default. For operation from another computer,
use an SSH tunnel (`ssh -L 8080:127.0.0.1:8080 USER@W541`) and browse localhost.
The dashboard is for a trusted operator and has no account/login system; do not
expose it to the public internet. Mutations require a per-process dashboard token.

## Development and verification

```bash
.venv/bin/python -m unittest discover -s tests -v
```

The tests exercise full demo batches, restart behavior, baseline/reset semantics,
polling fallback, overflow, corrupt images/state, image order, independent overlays,
CSRF checks, process locking and uncertain print recovery. They do not substitute
for Nikon/HDMI and DS40 hardware qualification.

`--dev-server` uses Werkzeug instead of Waitress for local development. Normal
startup uses Waitress. No Node build, database, message broker or external web
assets are required.

## Implementation references

- [python-gphoto2](https://github.com/jim-easterbrook/python-gphoto2): persistent
  camera access, `wait_for_event`, file metadata, and `file_get`.
- [CUPS lp documentation](https://www.cups.org/doc/man-lp.html): explicit destination,
  copy count and driver options.

This project intentionally carries no application code from the old photobooth.
