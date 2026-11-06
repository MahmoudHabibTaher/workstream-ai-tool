# Session handoff

**State:** 3/8 done on `main` at `cc78144`, as of 2026-11-06.

**Just landed:** VS-03 (`cc78144372`)

**Open decisions:**
- D009: `--show` is left out of cli.ts until VS-06 (waiting: VS-04, VS-05, VS-06, VS-07, VS-08)
- D010: `@types/node` is a fifth dev dependency, pinned to Node 20 (waiting: VS-04, VS-05, VS-06, VS-07, VS-08)

**Next:** `ws claim --commit VS-04` (phase 2).

**Gotchas:**
- VS-03: - `npm install` warns that `@vscode/vsce-sign` has a postinstall script not covered by `allowScripts`. Packaging worked without it.
- Running the integration tests opens VS Code windows for a few seconds. That's why it stays local, like `test-mod`.
- `make vsix` writes `ui/vscode/workstreams.vsix`, and `*.vsix` is gitignored.

**Note:** post-merge verify skipped: main checkout lacked ui/vscode/node_modules (worktree setup runs only in task worktrees); coordinator ran make test (1078 OK) and make test-vscode (exit 0) on main+task/vs-03 in a scratch worktree after npm ci
