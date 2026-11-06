# Session handoff

**State:** 1/8 done on `main` at `1ef4ed0`, as of 2026-11-06.

**Just landed:** VS-01 (`1ef4ed0eac`)

**Still in progress:** VS-02 (coordinator), VS-03 (coordinator)

**Next:** Nothing is ready: see the blocked tasks below, or anything still in progress.

**Gotchas:**
- VS-01: - The server now walks each whole workstream folder and `worktrees/` recursively. Before, it walked only `evidence/` and `refs/heads`. A scan stats a little more, but the folders are small.
- `src/workstream/assets/web/logic.js` (`statusActions`) and the pane still hold their own copy of the status rule. Moving them onto `actions` is out of scope here.
