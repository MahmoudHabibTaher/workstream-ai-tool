# Session handoff

**State:** 6/14 done on `main` at `1842b2a`, as of 2026-11-04.

**Just landed:** LO-05 (`988d062018`), LO-06 (`1842b2a1b2`)

**Next:** `ws claim --commit LO-07 LO-12` (phase 4).

**Gotchas:**
- LO-05: - `src/workstream/assets/skills/ws-run/SKILL.md:25` and its copy at `.claude/skills/ws-run/SKILL.md:25` still say a foreground task should "return to the integration branch, then settle it". That now contradicts the brief. Neither file is in this task's scope, and a background worker can't edit `.claude/`. Suggested text: "**Foreground tasks** run in this session, one at a time, after the batch: claim it alone, follow its brief yourself, and land it with the `ws --root` command the brief gives."
- `docs/rule-map.md:81` quotes that rule as "Foreground tasks run alone in the main session". It may want the same review.
- `src/workstream/assets/PROTOCOL.md:17` tells every worker "Don't merge, and don't switch to the integration branch", while a foreground brief's step 5 tells it to land the task. The step never switches a branch, but settle does merge, so the two read as a conflict for a foreground worker. The conflict predates this task.
- `ws verify` ran long enough for the shell to move it to the background at 180s. It finished and recorded normally, in 299.7s for tests.
- LO-06: - `ws wave` has no JSON output, so `heldBack` is checked through `graph.compute_wave` and the CLI's "held back" lines.
