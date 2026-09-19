# DS40 physical qualification status

Four-strip cutting, corrected target centering, and the actual corrected photo
sheet are operator-confirmed. The photo sheet was job DNP_DS40-13. See
CENTERING-CORRECTION.md for measurements and calibrated settings.

The accepted correction is integrated into frozen batch settings. Printing now
supports an explicit qualified opt-in using the tested DS40 profile; defaults
and the qualification launcher remain dry-run. See KIOSK.md for launch commands.
No live kiosk session was started in this development turn.

Next: one supervised Space-triggered batch through the complete hardware path.
Prior camera and printer component tests need no repeats. Preserve the new batch
manifest/job ID and confirm four centered strips, moving previews and ready state.
Uncertain shutter or CUPS outcomes never retry automatically.


September 19 software update: see [storage, calibration and display recovery](STORAGE-CALIBRATION-RECOVERY.md). Existing hardware results are preserved; this update used simulated/mocked verification only and did not repeat physical capture or printing.
