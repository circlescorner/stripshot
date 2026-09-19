# Desktop startup and page links

Double-click the Stripshot desktop icon. A terminal asks for an operator password
of at least 12 characters, then starts the existing kiosk launcher with its sleep
inhibitor. Once the server responds, it opens the operator page plus separate guest,
Camera A and Camera B windows. Sign in to the operator page as `operator` with the
password entered in the terminal. Keep that terminal open while the booth runs.
Use Ctrl+C there for a controlled stop.

Move the guest/camera windows to the intended monitors and use their fullscreen
controls or F11. Firefox uses a separate guest profile; operator authentication
stays in the normal browser. Slideshow and saved photos are linked from the
operator page and are not opened over the camera displays automatically.

A second click while starting reports the existing startup. If the kiosk is already
running, the icon only opens its operator page. It never starts a second owner,
restarts the existing process, resumes an interrupted capture, or submits a print.
An occupied port or missing photo folder stops startup with a visible error.

The operator page's top navigation links to Operator, Guest kiosk, Camera A,
Camera B, Slideshow, and Saved photos & sheets. Prepared calibration sheets and
rendered dry-run previews retain their existing context-specific links.

The underlying command is:

```bash
/path/to/python desktop_launch.py --config /path/to/config.json
```

The local desktop installation uses the existing package's `START-DESKTOP.sh`.
It starts with printing disabled. Explicit live-print opt-in remains available
through the existing `--live-printing` flag; the desktop icon does not include it.
No photo occurs until an operator/guest starts a session with Go or Space.

## Fresh collection on this machine

At the user's request, the local configuration now uses `/home/m/Pictures/Stripshot`.
It starts with no previous batches. Earlier data and evidence were not deleted or
imported. New originals and finished sheets appear in its `batches` subfolder.
Last recorded calibration is retained: X `[26,16,6,-2]`, Y `2`. Existing local
startup configuration (including layout defaults and countdown) is otherwise kept.
Later layout edits and uploaded artwork from the missing temporary folder could
not be recovered. Review the layout and upload the four original border PNGs again;
no demo artwork has been substituted. No storage migration or retention system was added.

Verification: 122 Python tests passed, including all main page routes, duplicate
startup, occupied-port/missing-folder refusal, deferred browser opening and guest
profile separation. The navigation was inspected in an isolated read-only browser
preview; that preview was stopped. The desktop entry passes desktop-file-validate
and is executable/trusted. Real-camera startup was not exercised; no capture or
print was made.

## Live-view timer fix

If a camera page was opened before the September 19 timer fix, reload that window
with Ctrl+R. The corrected static script is served by the existing kiosk on 8090;
keep its terminal running. Both live camera pages were verified displaying refreshed
frames after reload, without restarting or reconnecting either camera.

## Operator printing switch

In the operator Output panel, choose **Enable live printing** or **Use dry run**
between sessions. Live mode sends one sheet for each new completed session; dry
run saves originals and the finished sheet without submitting a printer job.
Changing modes itself never captures, prints, or reprints old sessions. The current
mode appears in the Output panel, top badge, and guest dry-run indicator.

Only the authenticated operator can change this setting. Active/held batches block
changes; demo mode and unqualified printer profiles cannot enable printing. Saved
calibration stays intact. Existing frozen-batch and uncertain-print protections
remain in force. The choice lasts for the current kiosk process; the desktop
launcher still starts in dry run. Explicit --live-printing startup remains supported.

Installing this backend update requires one controlled kiosk restart, followed by
a page reload. Subsequent printing mode changes need no restart or camera reconnect.
The mode control was tested with isolated fake cameras and mocked printing; no
hardware shutter or print was used.
