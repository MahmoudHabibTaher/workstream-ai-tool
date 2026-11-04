# Session handoff

**State:** 10/16 done on `main` at `0d1eb6b`, as of 2026-11-04.

**Just landed:** RF-16 (`0d1eb6bb88`)

**Still in progress:** RF-10 (coordinator)

**Next:** Nothing is ready: see the blocked tasks below, or anything still in progress.

**Gotchas:**
- RF-16: - This raises the limit and doesn't stop the growth: RF-15's "Builds on" section still repeats every earlier task's gotchas, and `project_rows`' docstring still says a brief over the limit is a task that should be split.
- `tests/test_e2e.py` still asserts a sample brief is under 2500, which is stricter than the new limit. It passes and was left alone.
- `ws worktree create` refuses a foreground task, and the brief's `git switch` would move the main checkout off the integration branch. This task was instead worked in a plain `git worktree add` checkout at `.workstream/worktrees/rf-16`, so `main` stayed checked out.
- D013 ends `**Closed.** **Closed.**`, because `ws decide` adds the mark and the `--why` text already had it. Decisions are append-only, so it stays.
- The verify ran with a private `TMPDIR`, because of the shared-`TMPDIR` test failure earlier tasks reported.
