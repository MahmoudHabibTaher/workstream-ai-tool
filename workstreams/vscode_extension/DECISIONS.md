# Decisions: VS Code extension

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-06, user): scope approved

The owner chose native VS Code UI over a webview (decision 0016), with the ws CLI as the only source of facts and writes, not ws serve.
The owner removed Cursor from scope: M9 is proven in VS Code only, and M10 targets IntelliJ.
The owner chose an integrated terminal for Run, Coordinate, Close and Abandon, with chat windows as a later goal; the launcher is built to take a second target, but M9 ships the terminal only, with the clipboard when no agent command is set.
Planning chose: a local .vsix, no Marketplace; dev-only npm dependencies (typescript, @types/vscode, @vscode/test-electron, @vscode/vsce) and no runtime ones; integration tests against the installed VS Code with no download; the extension disabled in untrusted workspaces. **Closed.**

## D002 (2026-11-06, VS-01): sync stays outside the refusal half of item 2

`ws act sync` on a row that isn't progress-stale isn't refused. It returns `no change` and doesn't commit, and it did that before this task too. So "act refuses exactly what actions leave out" holds for pause and resume. For sync it holds in effect: act writes nothing that `actions` doesn't offer, but it reports `no change` instead of refusing. The test asserts this.
Rejected: making act refuse a sync that isn't stale. That would add a refusal, which is a behaviour change outside this task. **Closed.**

## D003 (2026-11-06, VS-01): unclaim is not a row action

`ACTION_STATUSES` keeps `unclaim` (any status), but rows offer only `ROW_ACTIONS = ("pause", "resume")`, plus `sync` when the row is stale. Unclaim belongs to a task, and health findings already offer it.
Rejected: listing unclaim on every row, which act would refuse for most tasks. **Closed.**

## D004 (2026-11-06, VS-01): serve looks up git's paths once

`serve.Watcher` caches `snapshot.git_refresh(root)` at startup, as it already did for `git_paths`. It then calls `snapshot.refresh_paths(project, rows, git)` on every scan, so the list is still defined in one place. The snapshot runs git_refresh each time it is built.
Rejected: running git twice on every 50 ms to 1 s scan. **Closed.**
