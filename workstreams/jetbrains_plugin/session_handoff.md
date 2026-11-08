# Session handoff

**State:** 5/7 done on `main` at `a5e82d8`, as of 2026-11-08.

**Just landed:** JB-05 (`a5e82d8f01`)

**Open decisions:**
- D014: the Terminal tab is opened with the public `createNewSession(runner, TerminalTabState)`, not the five-argument overload plan T7 names (waiting: JB-06, JB-07)

**Next:** `ws claim --commit JB-06` (phase 3).

**Gotchas:**
- JB-05: - Expanding a branch task runs `ws review --checks`, and that call runs the gates. The Review tree caches each task's review per reload (`Workstreams.review`), as VS Code's store does. A branch commit that touches no `refresh` path won't show until Refresh.
- The plugin has one root per project, so the Review tab has no per-root level, unlike VS Code's multi-root view.
