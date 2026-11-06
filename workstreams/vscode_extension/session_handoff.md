# Session handoff

**State:** 2/8 done on `main` at `8443524`, as of 2026-11-06.

**Just landed:** VS-02 (`8443524666`)

**Still in progress:** VS-03 (coordinator)

**Next:** Nothing is ready: see the blocked tasks below, or anything still in progress.

**Gotchas:**
- VS-02: - The ws-review skill (src/workstream/assets/skills/ws-review/SKILL.md) and README.md don't mention `--show` yet. Both are outside this task's files.
- `_range_of` already swaps a branch's `from` for merge-base(integration, branch), so `from` is rarely main's tip in practice. `side_rev` still takes merge-base(from, to), which matches the three-dot diff whatever `from` is.
