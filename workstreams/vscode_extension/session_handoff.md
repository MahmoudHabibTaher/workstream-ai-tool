# Session handoff

**State:** 8/8 done on `main` at `835853b`, as of 2026-11-06.

**Just landed:** VS-08 (`835853babd`)

**Open decisions:**
- D009: `--show` is left out of cli.ts until VS-06 (no task waiting)
- D010: `@types/node` is a fifth dev dependency, pinned to Node 20 (no task waiting)
- D029: a workstream's tasks file is the first path its own snapshot's `watch` lists that the root snapshot's doesn't (no task waiting)

**Next:** The queue is finished; `ws close` closes the workstream.

**Gotchas:**
- VS-08: - `ws settle`'s post-merge verify runs in the main checkout, where `[worktree] setup` (`npm ci`) never runs. VS-03's settle failed with `tsc: command not found` until `npm ci` was run in the main checkout's `ui/vscode`. Settle could run the setup commands before a post-merge verify.
- Run's clipboard fallback is easy to read as a failure: the owner expected a terminal. The guide now says to set `workstreams.agentCommand` first.
- `docs/plan.md`'s milestone table still says M9 "Works in VS Code and Cursor"; the plan is kept as written, and the status row says Cursor wasn't tried.
