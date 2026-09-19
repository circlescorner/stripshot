# Safe permanent-storage migration

The current `/tmp/stripshot-two-cameras-hgc2l_yp/` recovery tree has NOT been migrated.
Do not reboot or allow cleanup before a stopped, verified permanent copy exists.
The operator must choose the permanent path; `/home/m/Pictures/Stripshot` is only a
suggestion. Its parent must exist and the final destination must not yet exist.

1. Deploy the updated package during controlled maintenance. Updating files does
   not replace loaded Python code. Block guest starts; preserve any held or uncertain
   batch exactly. Do not acknowledge/abandon it just to make migration convenient.
2. In the updated operator page, enter the absolute permanent main-storage path and
   schedule migration. This writes only a migration plan, retaining plan history.
   It does not copy or switch live state. Pending status and cancellation are shown.
   Extra-copy destination controls are separate and do not relocate recovery state.
3. Ctrl+C the owning launcher and verify that coordinator/camera workers/process
   have exited. Disable external restart while maintaining the appliance. A timed-out
   native call or unconfirmed cleanup is not proof of exit: do not start a replacement.
4. Restart the normal launcher. Before camera initialization, StorageLease acquires
   and retains source and ancestral flock locks. Lock failure aborts startup.
   It rejects nested/existing destinations, changed parent identity, symlinks and
   nonregular files. The entire stopped tree is copied to a new staging directory;
   only transient root lock, migration plan and redirect are excluded. Original
   state/manifests/artwork/photos/held batches are copied unchanged, with complete
   file-size/SHA-256 comparisons against both stage and source. No files are deleted.
5. Files and directories are flushed. A locked staging inode moves with a Linux
   atomic no-replace rename. An incomplete marker blocks an interrupted destination;
   source redirect is persisted before the destination becomes usable. Both original
   and new locks remain held for the runtime, even when launching directly at the
   permanent path, preventing competing owners with older code using the old lock.
   The launch config is backed up before its data_dir alone is atomically changed.
6. Check the operator's current path, held/completed state and artwork. Do not fire
   shutters or print merely to check migration. Keep the old tree and delivery
   snapshots. Make a separate full stopped recovery backup on durable storage.

If /tmp is removed on a later reboot, a direct permanent-path launch recreates only
an empty locked redirect alias at the old path, never replacement camera state.
If an old alias exists but is inconsistent, or an incomplete migration marker remains,
startup fails closed: preserve source, destination and staging for investigation.
Do not manually erase markers or start either tree independently to bypass the stop.
A failure may leave a full staged/destination copy; it is retained as evidence.

No migration, config-path change, physical capture or print occurred in this update.
