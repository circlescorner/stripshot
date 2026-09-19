# One alignment for the finished strip

Photos and PNG artwork belong to one design. Stripshot now composes them on a
600 × 1800 canvas, then fits that complete design to the measured paper edges.
Every strip has its own width, height and X/Y offset. There is no second photo
centering correction on new sessions or finished-sheet previews.

Keep the saved **Photo layout** margins, gaps, photo size and order unless you
want to change the design inside the strip. These values work before paper
alignment. They are not printer calibration. The **Whole design distance from
cut edge** is the separate physical clearance around the finished composition.

Use **Strip alignment — photos + PNG** to calculate that fit from four separate
flatbed scans of a numbered reference. Existing accepted scans and their applied
values remain usable: the reference marks measured the same printer/cutter
geometry. No re-upload or resetting of layout margins is required. See
[the scan workflow](SCAN-ALIGNMENT.md). A fresh printed reference and rescan are
still needed to verify physical accuracy; software checks do not establish it.

**Advanced: manual strip alignment** edits the same saved values. It is an
override, not an additional adjustment. Keep it closed for normal scan alignment.
The old photo-centering form, caliper workflow, reset buttons and margin/offset
presets have been removed from Operator. Uncertain reference prints can still
be acknowledged after checking the printer, without submitting another job.

Use **Preview with saved photos** after saving changes. It renders the last
completed originals with the current layout, PNGs and common alignment, without
capturing or printing. This works even when live printing is enabled.

## Compatibility and preservation

- `operator-overlays.json` and the existing settings API remain the one source of
  alignment values; their historical names are retained to avoid migration or
  duplicated settings. Uploaded PNGs and layout settings are not rewritten.
- New batch and dry-run manifests record `alignment_mode: whole_strip` and freeze
  all four settings. Rendering composes photos and PNG first, then resizes and
  places the entire result once, against white backing. It rejects placements
  outside the nominal strip; it never clips PNG artwork.
- Existing manifests without `alignment_mode` retain the legacy rendering path,
  including their frozen photo offsets and independent PNG fit. Already finished
  sheets, held batches, original JPEGs and all scan evidence are preserved.
- The old `operator-calibration.json` and printer profile remain intact for
  compatibility and historical recovery. Their photo offsets do not move new
  whole-strip compositions. Existing printer authorization, media, queue,
  one-attempt submission and runtime live/dry-run choice are unchanged.

Regression tests compare every output pixel to an independently resized original
composition, cover all PNG edges and transparent artwork, ignore legacy photo
offsets in the new path, handle strips without artwork, preserve frozen legacy
batches and verify dry-run provenance. No physical camera capture or print is
part of this validation.

## Final adjustment from measured white edges

Inside Advanced: manual strip alignment, open **Fill measured white edges on a
finished strip**. Use a strip printed with the currently saved settings. Measure
left, right, top and bottom from paper edge to the outside of the complete design,
in millimeters. Enter zero to leave an edge alone, confirm the sheet uses the
current alignment, then calculate. This is a review-only proposal.

The proposal expands the common composition toward each measured edge, changing
width/height and shifting its center only by the difference between opposing
measurements. It edits the existing canonical fit; there is no extra rendering
transform or separately persisted correction. **Use proposal in manual fields
below** copies it into the existing form. Review, then **Save strip alignment**
and use the paper-free preview. No values are automatically applied.

Expansion is capped at the nominal strip canvas to retain every PNG edge. Any
unfillable amount is reported rather than cropped. A white area inside artwork
or photo-layout margins is a design issue, not an external paper edge; this tool
cannot remove it. Values use nominal 300 DPI, so cutter offsets, paper geometry
and physical scaling may leave residual borders. A fresh attended print/scan
check is still necessary before claiming borderless physical output.
