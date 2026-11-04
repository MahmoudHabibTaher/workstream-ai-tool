# Session handoff

**State:** 9/15 done on `main` at `cebd140`, as of 2026-11-04.

**Just landed:** RF-09 (`cebd140c03`)

**Next:** `ws claim --commit RF-10` (phase 3).

**Gotchas:**
- RF-09: - The skills and protocol text still show plain `ws decide "..." --why "..."` (for example the ws-coordinate line quoted in `docs/rule-map.md`), and the plain form still prints `; commit it`. They were not in this task's files, so they don't mention `--commit`.
- `check_checkout` only refuses dirty tracking paths of this workstream and the registry, so another workstream's uncommitted tracking files don't stop `--commit`. They stay out of the commit, because it uses `--only`. `ws claim --commit` behaves the same way.
