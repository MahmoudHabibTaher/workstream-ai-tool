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

## D005 (2026-11-06, VS-02): --show refuses a path outside the diffstat; --file stays as it is

Acceptance 3 says "as --file is", but `ws review --file <path>` doesn't refuse an unknown path today. It runs `git diff` and returns empty hunks. I made `--show` refuse with exit 1 and left `--file` alone, so plain review and `--file` behave as before. Rejected: also making `--file` refuse, which would change existing behaviour that the web UI calls. **Open.** Should `--file` refuse the same way? **Closed.**

## D006 (2026-11-06, VS-02): binary means a NUL in the first 8000 bytes, or not UTF-8

Git uses the NUL test, and JSON text can't carry bytes that aren't UTF-8, so both count as binary. The check is per side, so a file can be binary on one side only. Rejected: taking `binary` from numstat's `-`, which covers both sides at once. **Closed.**

## D007 (2026-11-06, VS-02): every git call in review.py runs with GIT_OPTIONAL_LOCKS=0

I set it in the shared `_git` helper as well as in the new bytes helper `_git_read`, so `--show`'s range and diffstat lookups get it too. The output of plain review, `--file`, `--checks` and `--queue` is unchanged. Rejected: a separate env for `--show` only, which would have meant a second copy of the range and diffstat calls. **Closed.**

## D008 (2026-11-06, VS-02): a git failure in --show is an error exit, not an `error` key

The `{path, side, rev, text, binary}` shape has no place for partial data, so a failure from `build_review` or from git raises WsError. Rejected: adding an `error` key to the schema. **Closed.**

## D009 (2026-11-06, VS-03): `--show` is left out of cli.ts until VS-06

D-CLI lists `--show` among `loadReview`'s options. VS-02 adds `--show` and isn't on this branch, so an argv using it would fail acceptance 4's real-CLI check here. VS-06 depends on VS-02, so it should add `loadShow` along with its line in `test_every_argv_cli_ts_builds`. Rejected: building the argv now and skipping its check when the CLI lacks the flag, which would hide a real mismatch. **Open.**

## D010 (2026-11-06, VS-03): `@types/node` is a fifth dev dependency, pinned to Node 20

`cli.ts` uses `node:child_process`, and `tsc` can't type it without node types. D001 lists four dev dependencies. I pinned `@types/node@^20`, the Node that the `^1.100.0` engine floor ships with, as T10 does for `@types/vscode`. It is dev-only, so the extension still has no runtime dependencies. Rejected: declaring the module types by hand. **Open.**

## D011 (2026-11-06, VS-03): TypeScript 7.0.2 emits CommonJS

`npm install` resolved `typescript@^7.0.2`, and it accepts all three T9 options. `module: nodenext` with no `"type"` in package.json emits CommonJS, the module format every VS Code from 1.100 loads. Node then reparses the `.ts` tests as ESM, so the test command adds `--disable-warning=MODULE_TYPELESS_PACKAGE_JSON`. Rejected: `"type": "module"`, which would need ESM extension support at the engine floor. **Closed.**

## D012 (2026-11-06, VS-03): the startup logic is `src/logic/start.ts`, and activate returns a small test API

`start(cli, folders)` resolves roots, then loads snapshots, and returns the one message to show. `activate` returns `{ready, ran, shown}` so the integration test can see every argv run and every message shown. VS-04 can add the views behind the same state. `resolveRoots` skips folders that aren't projects and reports a problem only when none is one. Rejected: stubbing `window.showErrorMessage` inside the extension host. **Closed.**
