# Session handoff

**State:** 12/16 done on `main` at `17eba41`, as of 2026-11-04.

**Just landed:** RF-11 (`17eba41aa8`)

**Next:** `ws claim --commit RF-12` (phase 3).

**Gotchas:**
- RF-11: - A bare `ws update --commit <id>` now takes the id as the hash, then argparse refuses the missing id. Only that order is affected.
- The test imports `fill_in` from `tests/test_protocol.py`, so running `tests.test_tasks` also loads that module.
- `--acceptance` checks the decision in the current checkout's `DECISIONS.md` and writes the current checkout's queue, like the rest of `ws update`. From a worktree without `--commit` it would change that worktree's copy, which the brief doesn't read. With `--commit` the integration-branch check refuses it.
- A second correction names only the later decision, because the whole text is replaced. The earlier one stays in git history and the decision log.
