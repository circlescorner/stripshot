# Safe migration from /tmp before unattended deployment

This is a planned maintenance procedure, not an executed migration. The current
launcher and recovery evidence remain at their existing paths. Do not reboot or
allow /tmp cleanup before preserving the evidence.

1. Block guest starts, inspect the operator page, and choose a maintenance window.
   Prefer no current batch. If a held/uncertain batch exists, preserve it exactly;
   do not abandon or acknowledge merely to make migration easier.
2. Ctrl+C the existing START-KIOSK.sh process and wait for coordinator and owning
   workers to exit. A timed-out or unconfirmed native cleanup is not proof of exit.
   Verify the process is gone. Disable any external auto-restart during maintenance.
3. Acquire and hold the existing data directory's `stripshot.lock` exclusively
   using the same flock protocol as storage.ProcessLock. Failure means another
   owner exists: stop here. Keep that lock through copying and config handover.
4. Choose a new permanent local directory (for example a dedicated Stripshot-data
   directory under Documents), with adequate free space and owner-only permissions.
   It must not already contain a different appliance state. Copy the entire stopped
   data tree to a new staging directory: state.json, all batches/manifests/JPEGs/
   hashes/sheets/overlays, operator-layout.json if present, and evidence reports.
   Exclude only the transient lock file; create a new lock at destination. Also
   preserve the local launch config and existing delivery/evidence documents.
5. Compare a complete relative file list, sizes and SHA-256 for source and staged
   files (excluding the lock). Parse state and manifests without rewriting them;
   verify saved original hashes against the copied originals. Flush files and
   directories to disk, then atomically rename staging to the permanent directory.
   Keep a separate backup on durable storage. Do not delete the /tmp source.
6. Back up config.kiosk.local.json, then atomically change only data_dir to the new
   absolute directory. Preserve camera serial bindings, printer opt-in behavior,
   artwork, margins, offsets, photo order and every current/last batch record.
   Make the old launch configuration clearly archival so it cannot start a second
   owner against the old data directory after the source lock is released.
7. Start exactly one launcher from the new configuration, initially without
   --live-printing. Inspect current/last batch identity, held/uncertain state,
   saved layout, artwork and previews. Do not press Go, resume, retry or print just
   to validate migration. A held native operation requires its normal evidence review.
8. Stop cleanly. Once the read-only checks pass, the next ordinary operator startup
   may use the already authorized --live-printing flag. Preserve both source and
   backup until the deployment has been accepted.

Never copy live state, merge state files, or reset the binding to bypass a mismatch.
Do not let the old and new data directories become concurrent independent owners.
This migration does not establish abrupt power-loss or long-duration qualification.
