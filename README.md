# stripshot

Minimal unattended dual-camera photo-strip appliance for the wedding booth.

## Locked scope

`stripshot` does only this:

1. Keep a persistent USB/PTP connection to two Nikon D3300 cameras.
2. Observe new files written to each camera's SD card by the physical intervalometers.
3. Wait for exactly 8 new images from Camera A and 8 from Camera B.
4. Freeze those 16 camera file identities.
5. Download the 16 JPEGs only after the batch is complete.
6. Build four 2x6 strips:
   - Strip 1: A1, B1, A2, B2
   - Strip 2: A3, B3, A4, B4
   - Strip 3: A5, B5, A6, B6
   - Strip 4: A7, B7, A8, B8
7. Apply one independent PNG overlay to each strip.
8. Assemble the four strips into one 6x8 print sheet.
9. Submit exactly one DNP DS40 print job.
10. Begin watching for the next 8+8 batch.

HDMI live view is external to the software. The cameras feed monitors directly over HDMI. `stripshot` must not request preview frames or manage live view.

## Deliberately out of scope

- Software shutter control
- Countdown/session UX
- Guest web UI
- DSLR exposure-setting orchestration
- Retake workflow
- Browser-controlled capture
- Live-view streaming

## Operator UI

The web UI is administrative only. It will show camera/print status, the current 8+8 counter, overlay previews/uploads, the last completed batch, and a **Reset next 16** action. Resetting establishes a new baseline and does not delete camera files.

## Camera keep-awake strategy

The preferred design is one persistent libgphoto2/PTP connection per camera. We first qualify that this allows the physical accessory-port intervalometers to keep taking photographs while HDMI live view stays active. No software keep-awake action that can affect shooting will be added unless the real hardware demonstrates that it is necessary.

## First qualification

Run `tools/qualify-usb-events` with both D3300s connected by USB and HDMI live view already active. The tool does not issue any capture command, change camera settings, or download/delete files. It holds a `gphoto2 --wait-event` session open against each camera and records what the cameras report while the intervalometers create one 8+8 sequence.
