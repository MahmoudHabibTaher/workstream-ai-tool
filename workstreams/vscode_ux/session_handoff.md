# Session handoff

**State:** 4/7 done on `main` at `10884fc`, as of 2026-11-12.

**Just landed:** VX-04 (`10884fcf5d`)

**Next:** `ws claim --commit VX-05` (phase 3).

**Gotchas:**
- VX-04: - The root snapshot now gives each row a `launches` list (jetbrains_plugin D001/D002). `launches()` in `logic/actions.ts` still uses the status rule from vscode_extension D022. VX-05's launch flow is the natural place to switch to the snapshot's `launches`. That would change the `launch` menu regex that `tests/test_vscode_files.py` pins, if it goes per kind.
- The Health view's welcome shows only with no project. With a project, `healthNodes` already draws "Nothing to report."
