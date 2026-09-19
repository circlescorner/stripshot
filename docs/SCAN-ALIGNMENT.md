# Scan to align PNG borders

Use **Operator → Scan to align PNG borders** to measure where each PNG should sit
relative to the paper's cut edges. Photo layout and photo calibration are unchanged.

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
5. Leave **Minimum border clearance** at 0.5 mm initially, then click **Calculate
   alignment from scans**. The review shows scanned and predicted margins. Nothing
   is applied yet. If available print area limits the fit, equal margins may be
   larger than the requested clearance.
6. Check the four paper outlines, tick the review checkbox, and click **Apply this
   PNG alignment**. Each PNG's width, height and X/Y position are saved together.
   The entire PNG is resized, never cropped. Uploaded artwork remains unchanged.
7. Prepare, print and scan a **fresh reference** to verify the result. Its faint
   green outline represents the saved PNG extent. The next review's scanned
   margins show the result of the previous correction.

This measures the complete PNG canvas against the cut paper, not individual
features inside the design. Millimeter margins assume the nominal 300-DPI output.
Accuracy is limited by scanning, edge detection and printer/cutter repeatability;
a successful software analysis is not a guarantee of a perfect physical print.
No real scanner or printer has yet been used to qualify this feature.

Preparing, uploading, calculating and applying do not print or take photographs.
Physical reference printing uses the existing one-attempt ledger and explicit
confirmation. Uncertain jobs are never automatically retried. Apply is allowed
only between sessions, refuses stale scans/settings/printer configuration, and
does not modify existing finished sheets, original photos, or held batches.

Scans, annotated previews and measured bounds are retained with their calibration
target. Replacing an upload retains the old evidence and invalidates the previous
proposal. Applied settings persist in `operator-overlays.json`; each new batch
freezes them. Existing settings without vertical fields retain 100% height and
zero vertical offset. The manual PNG cards expose **Vertical fit** for reviewing
or editing these settings, and enforce the same no-crop bounds.

## Implementation and checks

Numbered references use unique marker IDs from OpenCV's 5×5 dictionary. Known marker
corners establish an affine mapping from the scan to the original strip coordinates;
the detected paper outline determines a conservative safe rectangle. PNG placement
fits symmetrically inside both that rectangle and its nominal sheet strip. The
detector rejects missing/mismatched marks, low resolution, mirroring, excessive
stretch/shear, inconsistent reference fits, missing edges and excessive cut skew.
See [OpenCV's ArUco detection documentation](https://docs.opencv.org/4.13.0/d5/dae/tutorial_aruco_detection.html).

Requires `opencv-python-headless` and its NumPy dependency in the application's
Python environment (`pip install -r requirements.txt`). There is no scanner device
driver integration: use the scanner's normal software and upload the resulting file.

145 Python tests and all five Node suites passed. New tests recover known print
displacements from rotated, 300/600-DPI synthetic scans, preserve full PNG area,
and reject wrong targets, cropped images, stale proposals, changed settings and
active sessions. An isolated browser check uploaded all four synthetic scans,
calculated and reviewed the correction, and applied it without console errors.
No physical capture, print, or real-data alignment changes were made during testing.
