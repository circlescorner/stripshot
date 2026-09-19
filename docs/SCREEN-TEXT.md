# Guest screen text and countdown placement

Operator → **Live view & kiosk text** has one editor for every guest-screen
message. Select the text to edit, then change its wording, font, size, regular/bold
weight, italic style, text/background color, alignment, spacing and line height.
A local sample shows the selected style. Size is the desktop pixel size and adapts
down on narrow screens. Fonts use the listed local/system families with fallbacks;
no external fonts or executable HTML are loaded.

The selector includes live-view headings, loading, reconnecting, preview errors,
paused/capturing/rendering states, countdown, camera label and full-screen button;
it also includes kiosk headings, button/hint, progress, ready, loading, capture,
render, submitted, paused, uncertain and disconnected messages. Leave wording
blank to hide it. Only the placeholders shown for that item are accepted:
`{camera}`, `{count}`, or `{round}`. They are plain text, never HTML.

Choose **Countdown appears on Camera A page** or **Camera B page**. Only the
chosen page replaces live view during 3, 2, 1. The other page continues showing
fresh preview frames while they are available. Actual camera exposure can still
interrupt preview. Screen routing does not change camera identity, captures or
photo order.

**Save screen text & countdown page** stores `operator-screens.json` and updates
open guest screens within a few seconds. It performs no capture, print, restart
or alignment change. Values survive restart. Camera A was explicitly requested
for this deployment; the software's compatibility default remains Camera B until
saved. Existing live pages need one reload after this software update to load the
new scripts; subsequent text changes update automatically.
