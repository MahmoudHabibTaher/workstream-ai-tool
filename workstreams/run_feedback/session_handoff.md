# Session handoff

**State:** 15/16 done on `main` at `f634d87`, as of 2026-11-04.

**Just landed:** RF-13 (`5a48e4bd36`), RF-14 (`f634d8745c`)

**Next:** `ws claim --commit RF-15` (phase 5).

**Gotchas:**
- RF-13: - `docs/rule-map.md` has no row for the new `ws-run` rule. It isn't in this task's files.
- `.claude/skills/ws-run/SKILL.md` stays stale until RF-15 runs `ws adapt claude-code`, as T2 says.
- A decision the branch lacks can appear twice in a resume brief, under Resuming and under "Decisions that apply". I left that section alone.
- `make test` under `ws verify` took 251.8s, so the 180s shell limit moved it to the background again.
- RF-14: - A record is tied to the code tree, and tracking files aren't in it. An `expect` added to the queue after a passing `ws verify` isn't checked until something verifies again: the gates read the record's `missingOutput` and don't compare it with the queue. Closing this means `gates.py` passing the task to `run_problems`, and that file isn't in this task's list.
- `ws update --verify` can remove a task's last command while an item still has `expect`. `ws validate` reports it, but I didn't add a refusal to `ws update`.
- The type message in `TYPE_DESCRIPTIONS` still says `{text, kind} objects`, because `tests/test_tasks.py:835` pins that wording and the file isn't in this task's list.
- `make test` under `ws verify` took 250.8s, so the 180s shell limit moved it to the background again.
