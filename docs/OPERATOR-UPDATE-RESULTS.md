# Saved-photo access and border rollback

The operator page shows the saved-photo folder and a read-only browser for completed
originals and finished sheets. The added migration, backup and retention system was
removed. Existing data and recovery evidence remain in place.

The proposed calibration enlargement/cropping was rejected and removed. Rendering
again translates the original composite with the saved calibration; no new scaling
or edge-color extension is applied. The white-edge issue remains unresolved.
Saved calibration and frozen batches remain unchanged. An unshifted preview was
rendered separately from saved originals at the user's request; it changes no settings.

Verification: 109 Python tests passed in 68.045 seconds. Four Node regression suites
passed. The simple photo browser and operator page were checked in an isolated,
render-only demo; the demo was stopped. Preview source, artwork, manifest and operator
settings hashes were unchanged.

No physical capture or print, live-owner restart, data relocation or merge occurred.
This is software verification, not new physical printer qualification. Native abrupt
failure, endurance, custom calibration and OS kiosk lockdown remain unqualified.
A controlled application restart and page reload are needed to load the updated package.
