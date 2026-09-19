# Stop and restart from Operator

The controls are at the top of Operator, beneath the page links.

- **Stop Stripshot** closes the booth and cameras cleanly. The page shows the booth
  is offline. Start it again with the existing desktop icon.
- **Restart Stripshot** closes and reopens the application, preserving the current
  live/dry printing mode, saved photos, PNG alignment, layout and calibration. The
  operator page reloads automatically to get fresh controls and request tokens.
  Existing guest/monitor windows reconnect; restart does not open duplicate windows.

Each action asks for confirmation. Controls are available between sessions, with
no active or held batch or outstanding capture. They also work from an error state
when no batch is held. They do not take photographs, submit a print, retry a held
batch, or change the startup configuration. Stopping the application does not
cancel a print job already accepted by CUPS.

Requests require operator authentication and its CSRF token. The coordinator
blocks new captures before acknowledging. Cleanup runs while the HTTP server and data lock remain available. Operator shows
which camera or coordinator operation is preventing shutdown. If a blocked call
returns, shutdown continues; unconfirmed USB release prevents replacement. The
server closes only after successful cleanup, and Restart uses `exec` to replace
the same process, retaining the data lock until exec. Settings-restoration warnings
are distinguished from failed USB release. See [USB recovery](USB-RECOVERY.md) for
incident evidence, terminal guidance and remaining physical validation. An uncertain browser request is never automatically repeated.

Tests cover authorization, active/held-state rejection, no shutter side effects,
printing-mode preservation, cleanup failure and browser recovery. A real isolated
demo process was restarted with the same PID and preserved data/settings, then
stopped with exit code 0. Browser checks verified both buttons and automatic page
recovery after restart, then the offline message after Stop. These tests did not
use the physical cameras or printer.
