# Scan to align the finished strip

Use **Operator → Strip alignment — photos + PNG** to measure where each finished strip should sit
relative to the paper's cut edges. Photos and PNG are composed first and fitted
together once. Keep the design margins unchanged. See [how the controls fit
together](STRIP-ALIGNMENT.md).

1. Click **Prepare scan reference — no print**, inspect the preview, then click
   **Print one scan reference sheet**. Confirm the single physical print.
2. Scan the four numbered cut strips **separately**, at **300 or 600 DPI**. Put a
   dark matte sheet behind each strip, leaving visible dark space around all four
   paper edges. Disable scanner auto-crop, resizing and perspective correction.
3. Upload the matching files for strips 1–4. PNG, JPEG and single-page TIFF work.
   Each upload stays local. An ordinary photo strip is not a substitute for the
   marked reference: all four marks must match the current target and strip.
4. Inspect the green outline in each scan preview. It must follow the actual paper
   edge. Wrong strips, cropped scans, poor reference detection, excessive skew and
   unclear paper outlines are rejected instead of producing a guessed correction.
5. Leave **Whole design distance from cut edge** at 0.5 mm initially, then click **Calculate
   alignment from scans**. The review shows scanned and predicted margins. Nothing
   is applied yet. If available print area limits the fit, equal margins may be
   larger than the requested clearance.
6. Check the four paper outlines, tick the review checkbox, and click **Apply to
   photos + PNG**. Each complete strip's width, height and X/Y position are saved together.
   The entire PNG is resized, never cropped. Uploaded artwork remains unchanged.
7. Prepare, print and scan a **fresh reference** to verify the result. Its faint
   green outline represents the saved whole-design extent. The next review's scanned
   margins show the result of the previous correction.

This measures the complete composed canvas against the cut paper, not individual
features inside the design. Millimeter margins assume the nominal 300-DPI output.
Accuracy is limited by scanning, edge detection and printer/cutter repeatability;
a successful software analysis is not a guarantee of a perfect physical print.
A supplied 300-DPI reference scan has been analyzed successfully; a complete
apply/print/rescan cycle has not yet been physically qualified.

Preparing, uploading, calculating and applying do not print or take photographs.
Physical reference printing uses the existing one-attempt ledger and explicit
confirmation. Uncertain jobs are never automatically retried. Apply is allowed
only between sessions, refuses stale scans/settings/printer configuration, and
does not modify existing finished sheets, original photos, or held batches.

Scans, annotated previews and measured bounds are retained with their calibration
target. Replacing an upload retains the old evidence and invalidates the previous
proposal. Applied settings persist in `operator-overlays.json`; each new batch
freezes them. Existing settings without vertical fields retain 100% height and
zero vertical offset. **Advanced: manual strip alignment** edits those same values and enforces the
same no-crop bounds. Saved legacy photo-centering offsets are retained for old
batches only; they are not added to the new common fit.

## Implementation and checks

Numbered references use unique marker IDs from OpenCV's 5×5 dictionary. Known marker
corners establish an affine mapping from the scan to the original strip coordinates;
the detected paper outline determines a conservative safe rectangle. Whole-strip placement
fits symmetrically inside both that rectangle and its nominal sheet strip. The
detector rejects missing/mismatched marks, low resolution, mirroring, excessive
stretch/shear, inconsistent reference fits, missing edges and excessive cut skew.
See [OpenCV's ArUco detection documentation](https://docs.opencv.org/4.13.0/d5/dae/tutorial_aruco_detection.html).

Requires `opencv-python-headless` and its NumPy dependency in the application's
Python environment (`pip install -r requirements.txt`). There is no scanner device
driver integration: use the scanner's normal software and upload the resulting file.

Tests recover known print displacements from rotated 300/600-DPI scans and reject
wrong targets, cropped images, stale proposals, changed settings and active
sessions. Rendering regression coverage verifies the combined photos and PNG move
as one piece. Hardware print/scan verification remains a separate step.

## Bright backing and misleading crop errors

A supplied scan included all four cut edges on yellow backing. The old grayscale
threshold merged that bright backing with the paper and incorrectly reported a
cropped edge. Detection now requires brightness in every RGB channel so saturated
backing is separated from white paper. The supplied original passes marker-fit,
rectangle, size and skew checks; its annotated outline follows all four paper
edges. Synthetic rotated yellow, cyan and magenta backing scans also recover
known offsets. White backing and actual cropping still fail with wording that
explains both possibilities. Dark matte backing remains the preferred setup.

The original supplied scan was subsequently accepted by the running booth without
editing its image. All four accepted scans and the operator-applied fit remain
available for whole-strip alignment; no second correction is stacked on them.
