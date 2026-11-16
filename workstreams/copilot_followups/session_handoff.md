# Session handoff

**State:** 5/5 done on `main` at `eec1de6`, as of 2026-11-09.

**Just landed:** CF-05 (`eec1de6b64`)

**Text to apply:**
- CF-04: .claude/agents/ws-worker.md (evidence/CF-04.md)

**Next:** The queue is finished; `ws close` closes the workstream.

**Gotchas:**
- CF-05: - The Copilot capture entry received exactly one payload (the `edit`), though the agent also called `grep`. So on Copilot CLI 1.0.108 the matcher filtered as written, which contradicts the rerun's "fired on every tool call" on 1.0.105. One run can't say whether the CLI changed or the earlier count was wrong. 0008 says this.
- Both agents, once denied, declined to get around the hook from the shell. Neither was pressed to.
- `ws settle` keeps listing CF-04's text to apply as pending, though `.claude/agents/ws-worker.md` holds it. `evidence.parse` keeps the ``` fences inside the entry's text, so `handoff._is_applied` never matches a fenced block.
