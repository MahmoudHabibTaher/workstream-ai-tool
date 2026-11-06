# Session handoff

**State:** 4/8 done on `main` at `f3f42f5`, as of 2026-11-06.

**Just landed:** VS-04 (`f3f42f5059`)

**Open decisions:**
- D009: `--show` is left out of cli.ts until VS-06 (waiting: VS-05, VS-06, VS-07, VS-08)
- D010: `@types/node` is a fifth dev dependency, pinned to Node 20 (waiting: VS-05, VS-06, VS-07, VS-08)

**Next:** `ws claim --commit VS-05` (phase 2).

**Gotchas:**
- VS-04: - `make test` took 337 s under `ws verify`. Nearly all of that is the Python suite, not this task's tests.
- `MarkdownString.appendText` turns spaces into `&nbsp;`. A test that looks inside a tooltip's `value` has to allow for that.
- `make test-vscode` builds, then runs only the integration tests. The logic tests run in `make test` through `tests/test_vscode_files.py`.
