# Collection readiness

The full 1,440-episode data-collection package is prepared. No held-out provider
episodes have run. Both host and VM preflight must pass before execution.

Validated: 360 grader fixture controls; early-exit and symlink rejection; separate
UID/network/mount/PID/cgroup grading; 120 full-runner reference controls (100
machine-graded successes, 20 semantic outcomes correctly pending); credential and
network probes; transient protected writes; final native development runs.

Latest development confirmation: 16 native executions completed, 15 tasks
completed. Cursor reported an approval requirement for deletion and left the
file intact. The previous wave completed 16/16. Preserve this variation; do not
bypass approval or retry until a favorable outcome appears. No grading errors,
protected final changes or key leakage were detected in the latest wave.

Effect analysis was corrected before held-out collection to distinguish temporary
atomic-write/runtime scratch paths from protected existing files and unauthorized
persistent additions. Original traces and outcomes remain archived, alongside
explicit reanalysis. See PROTOCOL-AMENDMENTS.md.

The byte freeze includes corpus, schedule, models, adapters, grading, effect
rules, review protocol and environment metadata. The VM additionally verifies
installed runtime bytes, kernel and package inventory. No native-sandbox parity
or universal credential-isolation claim is made.

After collection, semantic outcomes need two independent blinded reviews and
adjudication; unresolved effects need trace review. Nulls remain unknown. These
are analysis steps, not reasons to rerun or replace observed episodes.

See README.md for exact launch/collection commands and gate-evidence.json for
hash-linked validation records.
