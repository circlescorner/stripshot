# September 19 operator update verification

Implemented storage naming/organization and optional additional copies, manual
retention review with no deletion, stopped main-data migration, explicit calibration
sheet printing with durable intent, caliper correction proposals and separate apply,
and automatic browser frame/session recovery.

Validation:
- Full Python suite: 112 tests passed in 72.326 seconds.
- Final focused storage/calibration suite: 10 tests passed in 0.945 seconds,
  including the later inconsistent-ancestral-alias fail-closed regression.
- Four Node suites passed: keyboard guard, display/slideshow, resilient loop, and
  monitor recovery integration (stalled fetch/decode, failed requests, stale results,
  visibility/pageshow recovery and URL cleanup).
- Fresh operator-page browser inspection: storage/calibration sections and existing
  controls visible; accepted defaults load; no JavaScript errors.
- Mixed cached-template/new-script behavior was observed on a long-running test
  process, reinforcing the required controlled restart plus page reload on deployment.
- Temporary render-only servers at 8095 and 8096 stopped and confirmed unreachable.
  Existing 8090 live kiosk and 8092 simulated service were left running.

No physical shutter, print, camera-worker restart, live data migration, SD deletion,
or merge was performed. Existing accepted hardware evidence is preserved.

The permanent destination is not yet selected. Main migration must wait for a
verified stopped owner. Retention controls record reviews; they do not delete data.
New custom calibration, abrupt native failure, endurance and OS lockdown remain
unqualified. See STORAGE-CALIBRATION-RECOVERY.md and DATA-MIGRATION.md.
