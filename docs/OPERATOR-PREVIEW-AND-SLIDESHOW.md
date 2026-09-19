# Dry runs, calibration, slideshow and session displays

Restart the existing launcher at an idle point, then reload the operator and both
camera pages. All existing FPS, margin, scale, gap, photo-order and overlay controls
remain visible. Nothing was hidden behind an advanced section.

## Paper-free finished preview

Save your desired overlays/layout/calibration, then click **Render dry run in a new
window** under Calibration. This reuses the **last completed batch's sixteen local
originals**. It takes no photos and never creates a printer job, even with live
printing enabled. It shows the complete 2400×1800 sheet with your currently saved
artwork and settings, and provides a full-resolution link. If the browser blocks the
new window, use **Open finished preview** after rendering. Browsers may choose a tab
instead of a separate window according to their settings.

The preview is an immutable, separately named entry under data_dir/dry-runs. Source
hashes are checked for software batches; a changed/missing original stops rendering.
Originals, source manifests, last/current batch records and print intents are never
rewritten. A finished source session is required; active sessions must finish first.
This is a rerender, not an unprinted new capture. Normal Space/Go still uses the
launcher's live-print setting.

## Visible calibration

Four independent pixel offsets are now shown in the operator page, bounded to ±60
pixels. Positive moves right; negative moves left. Save applies to future sheets
and dry-run renders. Each whole photo-plus-overlay strip translates and clips within
its own 600-pixel boundary. The existing accepted offsets +20,+15,+6,−2 are retained
unless explicitly changed; **Load accepted offsets** fills the inputs and requires
Save. Calibration is stored atomically in operator-calibration.json and overrides
startup calibration after loading the DS40 profile.

Custom offsets are an explicit operator override, not a new hardware qualification.
The saved/frozen printer settings record that override. Live printing still requires
its startup opt-in and the original queue/options profile. CUPS intent protection,
single submission, and the prohibition on retrying uncertain jobs are unchanged.
An active batch retains its frozen printer settings and offsets. Existing margins,
scale, order, artwork and FPS settings are not reset by calibration saves.

## Slideshow

Open `/slideshow` from the operator page, ideally on its own monitor/window.
Use left/right arrow keys or Previous/Next; Pause/Play and Full screen are available.
The operator sets 1–120 seconds per image, toggles **Shuffle all**, and chooses:
all completed batches' individual photos (default), latest completed batch's photos,
or finished four-strip sheets. Shuffle visits all selected images once before
wrapping, retains its order for backward navigation, and rebuilds when the catalog
or toggle changes. Timing changes reach open slideshows within about five seconds;
new completed batches appear after the local catalog refresh (about 10–15 seconds).

Only completed local manifests are indexed; active/abandoned batches are excluded.
No SD-card scan or camera access occurs. Display-size JPEG derivatives are cached
under gallery-cache; originals remain intact. Settings persist in operator-slideshow.json.
The display page/images are available without operator login on the loopback server;
changing settings still requires operator authentication and CSRF protection.

## Session-aware camera displays and countdown

Outside a session, an unavailable preview retains its operator-check message.
During a session, an unavailable Camera A shows exactly `MalanaphyVick Wedding`.
Camera B displays the real scheduled countdown before each new paired photo,
including over its preview, then uses “Taking photo N of 8…” during capture blackouts.
While preparing a sheet it says “Making your strips…”; held/faulted sessions say
“Session paused — please ask the attendant”. Stale server status produces a reconnect
message rather than an invented countdown.

The operator can save 0–10 whole countdown seconds (0 disables). The kiosk's new
local default is 3 seconds; existing generic configurations/manifests without this
field retain zero. Settings persist in operator-session.json and freeze per batch.
A countdown starts only after the previous round has finished its checks. It cannot
predict native USB duration or promise synchronized shutters. It never retries a
shutter. Explicit safe resume still rejects uncertain intent/returned-path-only records.

## Verification and deployment

New automated checks cover no-capture/no-print dry rerender, hash mismatches,
unchanged originals/manifests, overlay/calibration pixels, frozen settings, operator
access, gallery filtering, countdown-before-shutter behavior, navigation/shuffle,
and one mocked custom-calibration print with the original queue/options gate.
Browser checks on an isolated demo verified visible old/new controls, calibration
save, rendered sheet with overlay/full-resolution link, shuffled slideshow timing,
left/right keys and a genuine scheduled countdown. No physical exposure or print
was performed; the previously successful hardware runs were not repeated.

Settings remain in operator-calibration.json, operator-session.json,
operator-slideshow.json, operator-preview.json and operator-layout.json. Dry runs
remain under dry-runs/, with original sessions under batches/.


September 19 software update: see [calibration and display recovery](CALIBRATION-AND-LIVE-VIEW.md). Existing hardware results are preserved; this update used simulated/mocked verification only and did not repeat physical capture or printing.
