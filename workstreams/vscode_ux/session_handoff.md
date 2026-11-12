# Session handoff

**State:** 5/7 done on `main` at `dd12052`, as of 2026-11-12.

**Just landed:** VX-05 (`dd12052572`)

**Open decisions:**
- D020: the launch menu still uses the D022 status rule (waiting: VX-06, VX-07)

**Next:** `ws claim --commit VX-06` (phase 3).

**Gotchas:**
- VX-05: - The sample project's `ws new` docs keep their double-brace placeholders, so `validate` blocks every launch kind there. `launches()` fills them and commits before the non-blocked cases, which runs after the status bar assertions that count those errors.
- The plan's outcome names a task pin (`run-task`). VX-05's acceptance doesn't, and the flow offers only the four row kinds. `ws launch check|argv` already accept `--task`.
- VX-06 adds the chat targets to `TARGETS`. Each needs `label` and `needsAgent: false`, and the flow offers them with no other change.
