# PNG artwork and strip alignment

Upload an independent 600 × 1800 transparent PNG for each strip under **PNG artwork**.
The entire PNG is composed over the photos before physical alignment is applied.
New artwork keeps that strip's saved alignment.

There is now one fit for photos and PNG together. See
[Strip alignment](STRIP-ALIGNMENT.md) for the current controls and
[Scan alignment](SCAN-ALIGNMENT.md) for the separate flatbed-scan workflow.
The old independent PNG-fit and photo-centering controls are superseded.

Width and height can be 10–100%. Positive offsets move right/down; negative move
left/up. The complete design must fit inside its nominal strip. At 100% width,
only zero horizontal offset fits; at 90%, -30 to +30 pixels fit. Out-of-bounds
placements are rejected, never silently cropped. Uploads remain unchanged.

**Advanced: manual strip alignment** edits the scan settings directly. Save, then
use **Preview with saved photos** to inspect the whole sheet without capture or
print. New batches freeze their chosen settings; older unfinished batches retain
the rendering rules saved when they started. Existing finished sheets are untouched.
