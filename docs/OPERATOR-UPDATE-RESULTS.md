# Saved-photo access and calibration fitting

The storage-management system has been removed. The operator page now shows the
saved-photo folder and one link to browse completed originals and finished sheets.
No migration, destination, backup-job or retention system remains in the application.

Calibration now scales each axis only as needed and crops to fit, preserving the
saved center shifts without added color or blank padding. Width and height scale
independently to avoid unnecessary vertical cropping. Larger than 3% enlargement
was explicitly selected to keep the saved shifts. Existing photos/artwork, stored
calibration settings and already-frozen batches remain unchanged.

Verification:
- Full Python suite: 110 tests passed in 68.525 seconds.
- Final fitting/calibration checks: 9 tests passed in 5.940 seconds, including the
  added horizontal-fit regression that protects bottom artwork from vertical cropping.
- All four Node suites passed.
- Operator page and read-only photo browser checked in an isolated render-only demo;
  no JavaScript errors. The port 8096 demo was stopped and confirmed unreachable.
- Separate preview rendered from existing local originals and current artwork using
  X=[26,16,6,-2], Y=2. Width increases are [8.67%,5.33%,2.00%,0.67%], height 0.22%.
  The year remains visible. Source and overlay SHA-256 hashes stayed unchanged.

No physical capture or print, live-owner restart, data relocation or merge occurred.
This is a rendering verification, not a new physical printer qualification.
A controlled application restart and page reload load the updated package.
