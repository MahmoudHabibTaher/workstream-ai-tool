# Session handoff

**State:** 5/6 done on `main` at `90e6917`, as of 2026-11-03.

**Just landed:** WU-05 (`90e691700b`)

**Next:** `ws claim --commit WU-06` (phase 3).

**Gotchas:**
- WU-05: The budget screen re-measures on every change while it's open, which takes about two seconds. `ws audit usage` isn't on it, since it reads agents' transcripts and takes options a page has no place for yet.
