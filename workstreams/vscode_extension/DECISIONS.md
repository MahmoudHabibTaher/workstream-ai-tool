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

## D013 (2026-11-06, VS-04): only the Registry view is contributed now

D-VIEWS puts four tree views in one container. This task contributes the container and Registry. Review queue, Health and Budget belong to VS-06 and VS-07, which bring their data. Rejected: empty placeholder views, which would draw nothing and would need menus that have no commands yet. **Closed.**

## D014 (2026-11-06, VS-04): a workstream's own snapshot is read when it is first needed

The top level comes from `ws snapshot`. A workstream's wave, tasks and paths come from `ws snapshot -w <id>`. The extension runs that only when the node is expanded, or for the status bar's active workstream. It caches the result until the next reload. VS Code asks again for the expanded nodes after each reload. Rejected: reading every workstream on every reload, which would mean 11 CLI runs per burst on this repo. **Closed.**

## D015 (2026-11-06, VS-04): cli.ts runs ws with `GIT_OPTIONAL_LOCKS=0`

The snapshot runs `git status`, which can rewrite `.git/index`. That file is one of the `refresh` paths, so each reload could trigger the next. `ws serve` already sets this variable for the same reason. `execRun` now sets it too, and a logic test checks it. Rejected: leaving `.git/index` unwatched, which would miss staging. **Closed.**

## D016 (2026-11-06, VS-04): Documents is the last child of each workstream

A workstream opens to its wave line, then its phases, then a Documents node holding Plan, Progress, Decisions and Handoff. Only the documents the snapshot's `paths` lists are shown. Each opens with `markdown.showPreview`. Rejected: putting the four documents beside the phases, which mixes them in with the tasks. **Closed.**

## D017 (2026-11-06, VS-04): the status bar's "active workstream" is the first `active` row

The extension takes the first `active` registry row of the first root that has one. With none, the status bar is hidden. Rejected: following the editor's current file, which the snapshot gives no mapping for. **Open.** Settle this if several workstreams are often active at once. **Closed.**

## D018 (2026-11-06, VS-04): activate's test API grew

On top of D012's `{ready, ran, shown}`, activate now also returns:
- `reloads`: one reason per reload, `watch` or `button`;
- `store`, `tree` and `statusBar`;
- `settled()`, which resolves once pending reloads have finished.

The integration test reads the tree through the same provider methods that VS Code calls. Rejected: reading the rendered tree through the UI, which the extension API doesn't expose. **Closed.**

## D019 (2026-11-06, VS-04): watchers are rebuilt when a `refresh` path appears

A watcher on a path that doesn't exist yet may never fire, `.git/worktrees` for example. The set is keyed on each path's existence as well as the list, so it is rebuilt when one appears. Rejected: rebuilding every watcher on every reload. **Closed.**

## D020 (2026-11-06, VS-05): the modal is VS Code's native modal, so the stale note is decided when it opens

`showWarningMessage(..., { modal: true, detail })` can't be redrawn while it is open, unlike the web UI's overlay. The note compares the node's pinned revisions with the latest snapshot the store holds at the moment the box opens. A commit made while the box is open is caught by act's refusal, not by the note (acceptance 2). Rejected: a webview dialog, which D001 rules out. **Closed.**

## D021 (2026-11-06, VS-05): activate's test API grew again: `ui`, `asked`, `launched`, and a reload reason `act`

On top of D018: `ui` holds the confirm and reason prompts, which the test replaces because a modal and an input box can't be answered through the extension API. `asked` records each confirm text, and `launched` records each launch with its terminal. After each `ws act`, the extension reloads with the reason `act`. Rejected: driving the real modal, which has no API. **Closed.**

## D022 (2026-11-06, VS-05): launches show on open workstreams only, as in the web UI

Run, Coordinate, Close and Abandon have no `actions` in the snapshot. Like `lanes.js`, they are offered on rows that aren't done or abandoned (`launches` in `src/logic/actions.ts`). That is a display filter, the same one the web UI uses, not a write rule: the agent decides what happens next. Rejected: asking for launch offers in the snapshot, which is a Python change and outside this task's files. **Open.** Settle this if the snapshot should own launch offers too. **Closed.**

## D023 (2026-11-06, VS-05): the modal shows the web UI's commit line, without act's ` (ws act)` suffix

The modal names `alpha: pause` on `main`, as `commitLine` does in `logic.js`. act's full subject is `alpha: pause (ws act)`. Rejected: copying act's message format into TypeScript, which would be a second copy of a CLI rule. **Closed.**

## D024 (2026-11-06, VS-06): a branch task's evidence opens read-only from `--checks`; a landed task's opens as the file

The integration checkout has no evidence file yet for work still on a branch (`review` gives `evidence: null`), so a branch's evidence opens as a `ws-review:` document. It serves `checks.evidenceText`, which is the same text the gates judged: the branch's copy first, then main's. A landed task's opens as the real file at the `evidence` path. Rejected: always opening the on-disk path, which is missing or stale for branch work. Also rejected: `--show` on the evidence path, which needs the workstream folder's relative path and isn't there when the evidence isn't in the diffstat. **Closed.**

## D025 (2026-11-06, VS-06): D009 is settled by this task

`loadShow` builds `['review', task, '-w', wsId, '--show', path, '--side', side]`. That line is in `test_every_argv_cli_ts_builds`, and the real CLI accepts it for both sides. D009 can close. Rejected: keeping `--show` out of cli.ts and calling it from the view, which would put a second process call outside cli.ts. **Closed.**

## D026 (2026-11-06, VS-06): a file loads both sides before the diff opens, and each `ws-review:` URI names its revision

The extension needs both sides first to tell whether either is binary, which opens nothing. It hands the texts to the content provider and opens `vscode.diff` on URIs whose query carries root, workstream, task, side and the rev `--show` returned. A cached text therefore never stands for a later revision. Rejected: letting the provider fetch lazily, which can't stop a binary diff from opening. **Closed.**

## D027 (2026-11-06, VS-06): activate's test API grew `review` and `opened`

On top of D021: `review` is the Review tree, and `opened` records what each file or evidence click opened (`diff`, `binary`, `failed` or `evidence`). Rejected: reading only the tab groups, which can't show that a binary click opened nothing on purpose. **Closed.**

## D028 (2026-11-06, VS-06): the Review tree groups by `state`, even though the CLI already sorts that way

`queueNodes` splits the queue into **On a branch** and **Landed**, keeping the CLI's order inside each. It leaves out an empty group and says "Nothing to review." when the queue is empty. This is a display arrangement: the order within each group is still the CLI's. Rejected: a flat list, which doesn't show where branch work ends. **Closed.**
