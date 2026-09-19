# Printer quality in Operator

The existing Printer settings panel brings together live/dry-run mode, remaining
prints, queue status and a Photo print quality menu. The installed queue was read
using `lpoptions -p DNP_DS40 -l`, `lpoptions -p DNP_DS40`, and its CUPS-served PPD.
It identifies **Dai Nippon Printing DS40 — CUPS+Gutenprint 5.3.4**.

Six supported controls are exposed: brightness, contrast, saturation and cyan,
magenta and yellow channel gamma. Each offers a conservative discrete 0.5–1.5
range in 0.1 steps. The driver's `None` choice is its 1.0 baseline. These are
printer-only adjustments: originals, rendered PNGs and screen previews stay
unchanged. No sharpening control was advertised by this installed driver.
There is no second application-side color-processing stage.

The menu shows saved values. Editing or choosing **Use baseline values** changes
only the form; **Save print quality** persists to `operator-printer-quality.json`.
Save is allowed only between sessions and never enables printing, captures a
photo, submits a job or reprints an old session. Baseline restores these quality
values only. Neutral values are a known starting point, not a universal best
setting. A physical comparison requires a separately requested print.

`printer.options` must still exactly match `DS40_OPTIONS`. Queue authorization,
demo restriction, calibration authorization, live/dry gate, one copy, one-attempt
intent and uncertain-job handling remain enforced. Quality lives in a separate,
strictly validated dictionary; arbitrary options and custom driver expressions
are rejected. The installed driver's supported values are checked before saving
and again before submitting a batch that carries quality settings. Fixed neutral
fine adjustments and the existing Photo/default color pipeline are pinned to
avoid silently stacking queue defaults with the selected adjustments.

New sessions and calibration intents freeze their quality values. Existing and
held batches without the field retain their old printer arguments; saving a
quality change cannot rewrite them. Media size, four-strip cutting, resolution,
orientation, scaling, PNGs, layout and common strip alignment remain unchanged.
