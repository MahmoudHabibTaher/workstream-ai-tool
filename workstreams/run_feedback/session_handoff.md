# Session handoff

**State:** 3/15 done on `main` at `baf1941`, as of 2026-11-04.

**Just landed:** RF-01 (`6d84e11c2c`), RF-02 (`0b15f167b9`), RF-03 (`baf1941d6a`)

**Next:** `ws claim --commit RF-04 RF-05` (phase 1).

**Gotchas:**
- RF-01: - `tests.test_evals.ScenarioTests.test_the_scratch_repo_is_cleaned_up` fails when another worker's suite runs at the same time. It compares `ws-eval-*` in the shared `TMPDIR` before and after, and sees the other run's scratch repos. It failed my first `ws verify` (`AssertionError: Items in the second set but not the first: ...ws-eval-scope-qbp6h5fk`) and failed again run alone while RF-03's verify was running. It passed with a private temp directory, so the passing record came from `TMPDIR=<private dir> ws verify RF-01 -w run_feedback`. The whole suite ran; only the temp directory differed. Not fixed here: out of this task's scope. Parallel workers will keep hitting it until that test or `ws verify` isolates `TMPDIR`.
- Finding a sentence end is a plain punctuation check, so an abbreviation such as `e.g. ` counts as a sentence end and a cut can stop there.
- A cut can fall inside a fenced code block and leave it unclosed, and a column-0 `- ` line inside a fence is read as a new bullet. Bullets are split without looking at fences.
- RF-02: `tests.test_evals.ScenarioTests.test_the_scratch_repo_is_cleaned_up` fails when another `ws verify` runs at the same time. It compares `ws-eval-*` in the shared TMPDIR before and after, so another run's scratch repo counts as a leak. My first `ws verify` failed this way (`ws-eval-verify-_sfjipf0`) while RF-01 and RF-03 were verifying. The recorded pass was run with TMPDIR set to a private folder, at the same commit (4ab1af63fcd1); the test code was not changed. Concurrent background workers will keep hitting this.
- RF-03: - **`verify.code_tree` can miss a same-size edit (existing bug, not fixed here).** It copies the real index to a throwaway one to keep the stat cache. The copy gets a new mtime, which defeats git's racy-entry check. A file edited to the same size within the same second as its index entry hashes correctly while the copy is in that second, then reads as unchanged once the copy is newer. So one tree can give two hashes.
  - Seen once while writing these tests: `ws verify` failed with "the commands changed the code they checked" although the command was `true`. That test changed `guide.md` from `old\n` to `new\n`. Three later runs of the same module passed.
  - Reproduced outside the repo with git 2.56.0, using `cp` of the index, `add -A` and `write-tree`, 1.2s apart. Same-size edit: trees differed in 5 of 5 runs. Different-size edit: trees matched in 5 of 5 runs.
  - The same path could also make the later hash match the pre-edit tree, which matters to the "the verified code is what would land" gate. I didn't test that gate directly. A real edit is unlikely to hit this, but fast tests can, so other tests may flake the same way.
  - `tests/test_gates.py` avoids it by making its doc edit a different size (`EDITED`).
