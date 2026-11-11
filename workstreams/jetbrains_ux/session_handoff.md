# Session handoff

**State:** 4/10 done on `main` at `a04eb10`, as of 2026-11-11.

**Just landed:** JX-04 (`a04eb10d31`)

**Next:** `ws claim --commit JX-05` (phase 2).

**Gotchas:**
- JX-04: - The ws-run skill doesn't describe running a single pinned task. The run-task prompt relies on the agent reading "run only task X". A later task could add a line to `src/workstream/assets/skills/ws-run/SKILL.md`.
- For claude-code the prompt is a bare last argument. An edited `--prompt` that starts with `-` would be read as a flag. No prompt from `LAUNCH_PROMPTS` does that.
- `tests/test_jetbrains_files.py:164` splits prompts only on `{ws}`, so the run-task pieces keep the literal `{task}`. The check still works (no Kotlin holds them), but splitting on `{task}` as well would make it tighter.
- JX-05: when Cli.kt calls `ws launch argv`/`agents`, add them to `tests/test_jetbrains_files.py`'s argv list (T8).
