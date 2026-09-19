# Individual PNG width and placement

In Operator, scroll to **Four strips. Four signatures.** Each PNG has:

- **Horizontal scale (%)**: 10–100%, centered on its strip. Height stays unchanged.
- **Horizontal offset (pixels)**: positive moves right, negative moves left.
- A reset button restoring that PNG to 100% width and zero offset in the preview.

The whole PNG must fit. At 100% width, its offset must be zero. At 90% width,
there are 30 pixels of room on each side. The allowed offset range updates as you
edit width; settings that would crop any edge are rejected by both UI and backend.
No automatic crop, enlargement, edge filling, or silent adjustment is performed.

Click **Save PNG adjustments**, then use **Render dry run in a new window** to see
the finished sheet with the last completed photos. Thumbnails preview unsaved PNG
edits; the dry run uses saved settings. Reset also requires Save to take effect.
New PNG uploads retain the strip's saved width and offset.

Photo calibration applies before PNG composition. Its existing horizontal and
vertical offsets therefore move photos only; PNG edges are always preserved.
The original uploaded files and all existing finished sheets remain unchanged.

Settings survive restart in `operator-overlays.json`. New batches freeze all four
PNG settings alongside their artwork copies. Older manifests without PNG settings
use full width and zero PNG offset. Dry runs record their chosen settings in their
own manifests without changing the completed batch. A backend restart is needed
to load this update, followed by reloading the operator page.

## Verification

134 Python tests and all five Node regression suites passed. Coverage includes
independent PNG placement, exact boundary validation, transparency, source-file
preservation, calibration extremes on all artwork edges, persistence, frozen
batches, old manifests, dry-run rendering, authentication and failed saves.

An isolated browser preview with no camera workers verified independent edits,
Save, reload persistence, rejection of a cropping offset, and a completed dry-run
sheet. Its browser console had no errors and the preview server was stopped.
No physical capture or print was performed for this update. The live kiosk has
not yet been restarted to load this backend change.
