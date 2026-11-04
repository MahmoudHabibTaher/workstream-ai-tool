# Session handoff

**State:** 8/15 done on `main` at `cf6cca8`, as of 2026-11-04.

**Just landed:** RF-08 (`cf6cca8998`)

**Next:** `ws claim --commit RF-09` (phase 2).

**Gotchas:**
- RF-08: - `ws next` still uses `graph.actionable` alone (`src/workstream/cli.py`, `cmd_next`), so it can name a held-back task, which `ws claim --commit` then refuses. Not in D-WAVE, so left alone.
- Plain `ws claim` without `--commit` skips `batch_problems`, as it already did, so it doesn't refuse the overlap.
- D-WAVE's rule is applied literally: a task hand-marked blocked that also has `blockedBy` on a todo task sharing its file holds that todo task back, and neither can move until someone acts. The wave reports it as stuck or held back, so it is visible. `validate` doesn't warn about that pair, because it skips overlaps along a `blockedBy` chain.
- Validate's overlap warning now fires for cross-phase overlaps between open tasks, so existing queues may show more warnings. That is the decision's intent, and they stay warnings.
- `ui/mod` (the Claude Code pane) doesn't show heldBack. Its types name only what it reads, and it wasn't in this task's list.
