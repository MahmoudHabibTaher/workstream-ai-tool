# Session handoff

**State:** 6/8 done on `main` at `71d4572`, as of 2026-11-06.

**Just landed:** VS-06 (`71d4572b89`)

**Open decisions:**
- D009: `--show` is left out of cli.ts until VS-06 (waiting: VS-07, VS-08)
- D010: `@types/node` is a fifth dev dependency, pinned to Node 20 (waiting: VS-07, VS-08)

**Next:** `ws claim --commit VS-07` (phase 3).

**Gotchas:**
- VS-06: - The Review tree reloads with the store, which watches the snapshot's `refresh` paths. A commit made on a task branch inside its worktree may not touch any of those paths, so the queue's diffstat for that task can stay stale until Refresh. Refresh is on the Review view's title bar too.
- The ws-review skill and README.md still don't mention `--show` (carried over from VS-02). Both are outside this task's files.
