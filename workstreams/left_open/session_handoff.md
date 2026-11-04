# Session handoff

**State:** 13/14 done on `main` at `bdae70d`, as of 2026-11-04.

**Just landed:** LO-14 (`bdae70dbf5`)

**Next:** `ws claim --commit LO-09` (phase 6).

**Gotchas:**
- LO-14: - `--requires` can raise `mode` to foreground without `--mode` being given. The line names only the fields given, as the task asks, so that raise stays unreported.
