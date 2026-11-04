# Session handoff

**State:** 5/15 done on `main` at `e09f4d4`, as of 2026-11-04.

**Just landed:** RF-04 (`e5591553f0`), RF-05 (`e09f4d46ac`)

**Next:** `ws claim --commit RF-06 RF-07` (phase 2).

**Gotchas:**
- RF-04: - The seed warning carries the workstream id, unlike seed's other warnings, so that it reads the same as the one from `ws validate`.
- RF-05: - `tests/test_evals.py` `test_the_scratch_repo_is_cleaned_up` globs `ws-eval-*` across all of `$TMPDIR`, so it fails when another worker's `make test` is running. My first `ws verify` failed on it alone, with `ws-eval-full-fv4o7dav` as the extra item, while RF-04's verify ran. The test passed alone, and the full suite passed once RF-04's run had ended. Not fixed: out of scope.
- `$(...)` is not parsed, so `A=1 a $(b; c)` warns even though it has no later step. It is a warning only, so this was left as is.
