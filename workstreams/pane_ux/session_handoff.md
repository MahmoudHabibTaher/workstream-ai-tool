# Session handoff

**State:** 1/5 done on `main` at `3307469`, as of 2026-11-13.

**Just landed:** PX-01 (`33074690dd`)

**Next:** `ws claim --commit PX-02` (phase 1).

**Gotchas:**
- PX-01: - `ui/mod/types/index.d.ts` was not in the task's files, but `RegistryRow` needed `launches` (and a `Launch` type) for the pane to read it, so I changed that file too.
- The prompt-button test that the plan placed in `detail.test.tsx` actually lived in `ui/mod/tests/health.test.tsx` ("prompt buttons only fill the box…"). It asserted the real prompt texts, so I changed it to stand-in texts instead of deleting it. It still checks that a button fills exactly its launch's prompt and never submits.
- `snapshot.py:39-41`'s comment still says the row kinds are "the same texts as promptText in assets/web/logic.js". That is out of scope here (src/workstream).
