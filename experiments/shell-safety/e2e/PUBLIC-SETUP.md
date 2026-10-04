# Source distribution and launch status

This checkout contains the study setup, pinned provider dependencies, case corpora,
rubrics, schedules, preparation tools, and regression tests. The current candidate
is `evaluation/rerun-v3`: 132 cases × 3 repeats × 4 providers = 1,584 episodes.
Earlier bundles are retained for preparation regression tests and provenance.

**The full study is not authorized or started.** The committed authorization record
is disabled. Merging this setup does not authorize execution.

Raw provider traces, archives, credentials, private review mappings, downloaded
runtimes, machine-specific prechecks, environment captures, and operator freeze
records are intentionally excluded. Historical preparation documents describe the
operator's local validation, not readiness of a fresh checkout. Generate fresh
local evidence before creating a new freeze; do not substitute prior readiness
claims for checks on the actual workers. Missing evidence blocks verification.

The publication copy parameterizes credential file paths and reports missing
precheck evidence without crashing. Original locally measured bundles and evidence
remain untouched. The source copy needs its own freeze after preparation.

Host launch scripts that use an external dotenv file require an explicit
`BENCH_CREDENTIALS_FILE` environment variable pointing outside the repository.
Never commit that file or generated review mappings. Pilot launchers execute real
provider jobs; use them only within an explicitly authorized pilot scope.

Run the portable setup checks without credentials or providers:

```sh
cd experiments/shell-safety/e2e/evaluation
python3 -B -m unittest test_rubric_v2 test_effects test_rerun_preparation test_full_preparation test_analysis test_freeze
```

See `evaluation/FULL-RUN-PREPARATION.md` for worker preparation and launch gates,
and `evaluation/RUBRIC-V2.md` for separate additions/deletions, task completion,
and semantic/action review. Unknown action outcomes remain unknown; two independent
blinded reviews and adjudication are required where specified.
