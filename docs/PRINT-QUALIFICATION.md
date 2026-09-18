# Proposed DS40 physical qualification — NOT AUTHORIZED

One synthetic target, one copy, one submission to `DNP_DS40`. Application printing
remains disabled even if this test is later authorized. No new camera batch needed.

Target: `ds40-qualification.png`, 2400×1800 RGB at 300 DPI, four 600×1800 strips.
Each strip has a unique number, top/bottom labels, the production photo ordering,
edge inset guides, and a one-inch square for scale assessment.

Candidate job options (per-job only, no queue defaults changed):

- PageSize=w432h576-div4
- Resolution=300dpi
- ColorModel=RGB
- StpLaminate=Glossy
- StpiShrinkOutput=Crop
- StpNoCutWaste=False
- orientation-requested=4 (landscape)
- number-up=1; copies=1

The host advertises the page choice. Upstream Gutenprint labels it 2x6*4 and
selects the strip cutter, supporting this candidate, but installed v5.3.4 geometry
and real cutting still need physical verification. Source:
https://raw.githubusercontent.com/echiu64/gutenprint/master/src/main/print-dyesub.c

Before authorization, review the target and ensure the intended DS40 is loaded
with 6x8 media. After authorization, record the exact file hash/options and a
submission intent durably, then issue one job. Record the CUPS job ID. An error,
timeout, or missing ID is uncertain: inspect the queue/output before any further
submission. Never automatically retry. Spool acceptance is not physical success.

Acceptance: exactly four separate approximately 2×6-inch strips, numbered 1–4;
all labels upright, correct top-to-bottom ordering, no blank extra sheet, no
adjacent-strip content, and measured edge loss/cut offsets recorded. Compare the
one-inch square and inset guides with a ruler. Save physical observations and job
ID. If crop or scale is wrong, adjust the proposal and obtain authorization for
another job. A pass does not itself authorize removal of the application gate.
