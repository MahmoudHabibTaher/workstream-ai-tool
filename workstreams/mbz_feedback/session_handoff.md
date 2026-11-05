# Session handoff

**State:** 3/10 done on `main` at `74da02c`, as of 2026-11-05.

**Just landed:** MF-03 (`74da02c98d`)

**Next:** `ws claim --commit MF-04` (phase 2).

**Gotchas:**
- MF-03: The `.claude/` copy of `ws-run` keeps the old steps 5 and 6 until MF-10 refreshes it (T2).

`handoff.texts_to_apply` calls `evidence._text_problem`, a private name in another module, because `evidence` wasn't on this task's file list and `evidence.problems` also reports everything else about the file.
