# Guest kiosk and qualified automatic printing

The operator accepted the actual corrected photo strips from job DNP_DS40-13.
The integrated path is now available with explicit live-print opt-in. Defaults
remain dry-run. No autonomous shutter happens at startup or restart.

## Start the application

Copy config.ds40.software.example.json to your local configuration, fill in the
already discovered A/B serials, preserve the data directory used for recovery,
and use port 8090 for the commands below. Stop any old camera-owning application
before starting this one. Keep the existing GVFS camera monitor mask.

```bash
bash start-kiosk --config config.json --ds40-profile
```

This starts a dry-run kiosk. It prompts privately for an operator password of at
least 12 characters, unless STRIPSHOT_OPERATOR_PASSWORD is already set. Passwords
are not written into camera configuration, logs or batch manifests.

For an explicitly intended live session, start with:

```bash
bash start-kiosk --config config.json --ds40-profile --live-printing
```

The live flag enables exactly one CUPS submission per completed new batch using
the accepted queue, media options and +20,+15,+6,-2 pixel strip offsets. It does
not print old completed batches or change the frozen settings of a held batch.
Demo cameras cannot print, even with this flag. Direct configuration opt-in uses
printer.enabled=true and printer.software_print_authorized=true, and must match
the accepted DS40 queue/options/offsets exactly. The flag is not persisted.

The default interpreter is .venv/bin/python; STRIPSHOT_PYTHON can select an
existing environment with the requirements installed. Normal serving uses Waitress.
The qualification-only test-two-cameras launcher stays dry-run.

## Guest and operator screens

```bash
bash open-kiosk http://127.0.0.1:8090/kiosk
```

The guest page has one Go button. Press Space while this browser window is
focused, or click Go. A held key, key repeat, modified Space, editable controls,
and presses during an active batch do not start another sequence. The button
is disabled while disconnected or paused. No repeat is sent after an uncertain
HTTP request. The keyboard binding is window-local, not a global OS shortcut.

Open http://127.0.0.1:8090/operator in a **separate operator browser profile**.
Sign in as `operator` with the startup password. This page retains PNG uploads,
reset, status and recovery. Guest tokens cannot authorize these actions, even
if their endpoints are manually requested. Detailed state and originals are not
exposed by the kiosk status endpoint. Camera monitor pages remain at /view/A
and /view/B. Put them on the preview monitors, keeping keyboard focus on the
kiosk window. The operator page also supports Space, except while editing inputs.

A healthy batch takes eight photos per camera, downloads exact originals,
renders the four independently overlaid/calibrated strips in the existing order,
and submits one print job. The page then becomes ready for the next group.
CUPS acceptance is not proof of physical completion: a printer jam may still
need an attendant. Guests see a simple attendant message on engine faults;
uncertain shutters and submissions retain the existing no-retry recovery holds.

## Supervised final hardware check

The component captures and actual photo printing have passed separately. The
combined kiosk-triggered physical path has now been confirmed by the operator
(batch-3d64d259b8fb4e778541380db1fd34d9, DNP_DS40-14). Do not repeat it merely
to re-establish the same result. For future intentionally requested runs: With live printing
explicitly enabled, press Space once and confirm sixteen originals, one CUPS job,
four centered strips, visible previews and return to ready. Do not repeat the
long historical-card inventory. Preserve the batch manifest and job ID.

## Deployment boundary

open-kiosk uses a separate persistent browser profile and fullscreen kiosk mode.
Operator authentication is enforced by the server, not just hidden buttons.
This does not block OS shortcuts, switching applications, closing the browser,
or a person who can use the logged-in desktop account. A dedicated restricted
Ubuntu kiosk session, secured physical keyboard/ports and supervised recovery
are still deployment work. No desktop policies or login services were changed.
Do not claim unattended readiness or enable automatic boot/restart yet.

Margin/scale settings and process-scoped keep-awake behavior are described in
LAYOUT-AND-UPTIME.md. The application has no session expiration.

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
