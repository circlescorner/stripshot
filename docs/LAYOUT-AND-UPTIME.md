# Photo margins and continuous operation

Restart the application with the updated START-KIOSK.sh, then reload the operator
page. New local configuration defaults: side/top margins about 3.05 mm, gap
2.03 mm, bottom 15.24 mm, photo size 95%. The existing photo order and accepted
DS40 centering correction are unchanged.

In /operator, use **Photo size & margins**. Side margins are symmetric; top,
bottom and gaps are independent. Scale 50–100% shrinks the photograph within
its slot, preserving the original crop and centering the smaller image. Uploaded
artwork is not resized. The form rejects settings leaving photos smaller than
100 pixels wide/high. Values are rounded to whole pixels at 300 DPI.

**Save for next batch** writes operator-layout.json durably in the data directory.
It overrides the startup layout on subsequent launches. Existing batches keep
their frozen layout; changes never alter recovery, original JPEGs or PNG uploads.
The guest kiosk cannot access this API. The preset button only fills the form;
Save applies it. The local startup configuration already uses that larger preset
unless an operator override has been saved.

There is no application session expiration or programmed idle shutdown. Kiosk
startup now holds a systemd idle/sleep inhibitor until the process exits. On GNOME
it also requests session idle/suspend inhibition. The launcher fails visibly if
systemd inhibition cannot be acquired rather than promising protection it lacks.
These requests are scoped to the running process; no global power preferences
or unrelated services were changed. A short systemd inhibitor acquisition check
succeeded on this host; the full desktop-specific idle behavior still requires
observation during use. Screen wake locks are requested on visible browser pages
and reacquired after visibility changes; availability is shown on the operator
page. The test browser did not grant a screen wake lock.

The kiosk detects server restart and refreshes its token without issuing a shutter.
Operator polling has bounded requests and no accumulating interval backlog.
Camera/CUPS operation timeouts remain intentionally: removing them would leave
stuck operations invisible and could compromise recovery. They do not limit session
length. Faults still require an attendant; uncertain shutters/prints never retry.

Infinity cannot be guaranteed. The computer and cameras need continuous power;
thermal limits, USB faults, full SD cards/disk, paper/ribbon and printer jams still
exist. Files are never deleted automatically. The current evidence directory is
under /tmp; preserve/migrate it to a permanent location before unattended deployment
or reboot cleanup. No long-duration hardware endurance result is claimed.

Photo ordering is now selectable independently for all sixteen positions in this
same form, while preserving the preferred defaults. Every original must appear
exactly once. See WEDDING-RECOVERY-UPDATE.md for persistence, recovery and HTTP
changes, and DATA-MIGRATION.md for the safe maintenance-window migration plan.
