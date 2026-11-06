# VS Code extension: plan

## 1. Context

M9 of `docs/plan.md`, rebuilt on decision 0016 (`docs/decisions/0016-native-ide-ui.md`): native VS Code UI instead of a webview, with every fact and write coming from the `ws` CLI. The web UI (M8) and the Claude Code pane (M7) show what has to appear. This milestone draws the same things with VS Code's own parts.

**Outcome:** a `.vsix` built from `ui/vscode`, installed in the real VS Code 1.139 on this Mac, that shows:
- a project's registry, its waves and tasks, the narrative documents, the review queue and per-task review, health and the context budget;
- reviews in the built-in diff editor, and health findings in the Problems panel;
- a status bar item, and commands for pause, resume, unclaim and sync that go through `ws act`.

A write that's current lands, and a stale one is refused. Run, Coordinate, Close and Abandon start the configured agent in an integrated terminal.

**Out of scope:**
- Cursor. The owner removed it: M9 is VS Code only, and M10 is IntelliJ.
- Chat windows as a launch target. That's the next goal, so the launcher is built to take a second target, but M9 ships the terminal only.
- Publishing to the Marketplace, since the repo stays private and ships a local `.vsix`.
- New kinds of write.
- Changing the web UI or the pane to use the new snapshot facts.
- Restricted (untrusted) workspaces and virtual workspaces.

## 2. Traps

### T1: a third copy of act's status rule
`src/workstream/act.py:36-38` holds `FROM_STATUSES`. `src/workstream/assets/web/logic.js:69` (`statusActions`) copies it, and so does the pane. A TypeScript port would be a third copy. Put the allowed actions in the snapshot instead. `act.py:30` already imports `snapshot`, so snapshot can't import act without a cycle. Move the table into `snapshot.py`, where act reads it.

### T2: the snapshot's `watch` misses most of what changes a view
`snapshot.watch_paths` (`src/workstream/snapshot.py:326`) lists only the registry, the tasks file, the handoff and the progress file. The server watches far more (`src/workstream/serve.py:73-106`): every narrative file, evidence folders, and git's HEAD, index, packed-refs, `refs/heads` and `worktrees`. A watcher built on `watch` would miss a claim, a branch or new evidence. Move that list into `snapshot.py` as data both consumers read, and have `serve.py` use it.

### T3: the snapshot schema is closed
`schema/snapshot.schema.json` has `additionalProperties: false` at several levels (lines 57, 92, 143, 164, 195). New fields fail `tests/test_schema.py` unless the schema gains them.

### T4: a branch review's old side is the merge base, not `from`
`review.review_range` (`src/workstream/review.py:59`) gives `{from: base, to: branch, kind: "branch"}`, and the diff uses three dots (`review.py:69`). `git show <base>:<path>` would show the base's tip, so the diff editor would also show unrelated changes landed on main since the claim. The old side of a branch review is `merge-base(base, branch)`. A merge or commit review's old side is `from`. That logic belongs in Python, beside `diff_spec`.

### T5: `ws` on the PATH runs main's code
A bare `ws` is the editable install of main's checkout, so an extension test in a task's worktree would exercise main's CLI, not the branch's. The CLI path must be a setting, `workstreams.wsCommand` (an argv array, default `["ws"]`). The integration test then points it at `python3 -B -m workstream`, with `PYTHONPATH=<worktree>/src` passed through `extensionTestsEnv`.

### T6: repo text in a `MarkdownString` is markup
Tree labels are plain text, but tooltips and hovers are `MarkdownString`. A title or proof holding `[x](command:...)` or HTML would render. Build every repo-derived string with `appendText`, keep `isTrusted` off and `supportHtml` false, and add command links only from the extension's own constants. This mirrors 0011's no-`innerHTML` rule, and a source test holds it.

### T7: a refresh just before a click
The confirm must pass the `revisions` of the snapshot the person saw: the one held when the modal opened, as in 0011. A watcher-triggered refresh while the modal is open must not swap them. When the drawn revisions differ from the latest, say so in the modal. `ws act` still decides.

### T8: the terminal is a shell
Typing `claude "<prompt>"` with `sendText` depends on the user's shell's quoting, and the Abandon prompt holds `<why>`. Start the agent with `createTerminal({shellPath, shellArgs, cwd: root})`, where argv comes from the `workstreams.agentCommand` array setting with the prompt as the last argument. That way no shell parses the prompt. Abandon asks for the reason in an input box first. With no agent setting, the prompt goes to the clipboard, as in the web UI.

### T9: Node runs TypeScript only if it's erasable
Pure logic is tested with `node --test` straight from `.ts`, since Node 26 strips types. Enums, namespaces and parameter properties break that. Imports need `.ts` extensions, so `tsconfig.json` sets `erasableSyntaxOnly`, `allowImportingTsExtensions` and `rewriteRelativeImportExtensions` (TS ≥ 5.7), and `tsc` emits `.js` for the package. Logic modules never import `vscode`.

### T10: `vsce` refuses `@types/vscode` newer than `engines.vscode`
Pin `@types/vscode` to the engine floor (`1.100.x`), not to latest.

### T11: worktrees start with no `node_modules`
`.workstream/config.toml` has no `[worktree] setup`. Without one, every task after the scaffold starts with nothing to compile. VS-03 adds `setup = ["cd ui/vscode && npm ci"]` (format at `src/workstream/config.py:258`). The first install needs the network.

### T12: the literals test only covers core
`tests/test_no_project_literals.py:13` scans `src/workstream` only, and `tests/test_mod_files.py:15` covers the pane only. 0016 says the literals test covers the extensions' sources, so the extension needs its own scan of `ui/vscode/src`. The agent name may appear only as an example in the setting's description, never in code.

## 3. Design

### D-FACTS: what the snapshot adds
`snapshot.py` gains `ACTION_STATUSES`, which `act.py` imports in place of `FROM_STATUSES`. Each registry row gains `actions`, the status writes `ws act` would accept now: `["pause"]`, `["resume"]` or `[]`, with `sync` added when `progressStale`. The snapshot's top level gains `refresh`: a list of `{path, recursive}`. That covers the registry, each workstream folder (recursive, which takes in the narrative files and `evidence/`), and git's HEAD, index, packed-refs, `refs/heads` (recursive) and `worktrees` (recursive). `serve.watched_paths` expands the same list, so there's one definition. The schema gains both fields, and `watch` stays as it is. Tested in `tests/test_snapshot.py`, `tests/test_act.py`, `tests/test_serve.py` and `tests/test_schema.py`. Rejected: computing the actions in TypeScript (T1), and a separate `ws watch` command, which would be a second read path.

### D-SHOW: `ws review --show`
`ws review <task> --show <path> --side old|new` prints JSON `{path, side, rev, text, binary}`. `rev` is the resolved commit, the merge base for a branch review (T4). `text` is null when the file doesn't exist on that side, and `binary` is true, with no text, for a binary file. An unknown path, one not in the task's diffstat, is refused like `--file`. Git runs with `GIT_OPTIONAL_LOCKS=0`. Tested in `tests/test_review.py`, schema included, so it shares no test file with VS-01, with added, deleted, modified, binary and branch-with-main-moved cases. Rejected: the extension running `git show` itself, which would put a second copy of the range rules in TypeScript.

### D-PKG: the package
`ui/vscode/` holds:
- `package.json`: engine `^1.100.0`, no runtime dependencies. The dev dependencies are `typescript`, `@types/vscode@1.100.x`, `@vscode/test-electron` and `@vscode/vsce`, with a lockfile. `capabilities.untrustedWorkspaces.supported: false` and `virtualWorkspaces: false`.
- `tsconfig.json` (T9), and `src/` holding `extension.ts`, `cli.ts`, `logic/*.ts`, the views and commands.
- `test/logic/*.test.ts` (node), and `test/integration/` (in VS Code).
- `.vscodeignore`, and `README.md` (the guide).

`make test-vscode` builds, then runs the integration tests against the installed app through `@vscode/test-electron`, with `vscodeExecutablePath` pointing at `/Applications/Visual Studio Code.app`, so nothing is downloaded. It's local only, like `test-mod`. `make vsix` packages the extension. `tests/test_vscode_files.py` runs the logic tests under node (skipped without node), as `tests/test_web.py:148` does. It also scans for literals and markup sinks (T6, T12) and checks that the real CLI answers each command `cli.ts` sends, as `tests/test_mod_files.py` does.

### D-CLI: one module talks to `ws`
`cli.ts` follows `ui/mod/hooks/data.ts`:
- `resolveRoot`, run per workspace folder and deduplicated by root;
- `loadSnapshot`, which checks `snapshotVersion === 1`;
- `loadReview` (with `--checks`, `--queue`, `--file` and `--show`), `loadBudget` (`ws audit context --json`) and `runAct`.

It uses `execFile` from the `wsCommand` argv with a 60-second timeout, never a shell. A missing `ws` gives a message naming the setting. `runAct` is the extension's only write.

### D-VIEWS: native surfaces
One view container, Workstreams, holds four tree views: Registry, Review queue, Health and Budget.
- **Registry.** Each workstream (with its status, `done/total` and error count) opens to its wave line, then its phases, then its tasks with badge descriptions. Tooltips carry the summary, acceptance and verify lines (T6).
- **Documents.** Plan, Progress, Decisions and Handoff open in Markdown preview from the snapshot's paths.
- **Status bar.** The active workstream's wave line and error count. Clicking it focuses the view.
- **Live refresh.** File system watchers on `refresh` (D-FACTS), debounced 300 ms, so there's one snapshot per burst. There's also a Refresh button.

`logic/*.ts` ports `waveLine`, `badgesOf`, `lanes`, `splitRows`, `gateSummary` and `rangeLine` from `src/workstream/assets/web/logic.js`, with tests mirroring `ui/web/tests/logic.test.mjs`.

### D-ACTIONS: writes and launches
Pause, Resume, Sync and Unclaim are context-menu commands on tree items. They only show where the snapshot's row `actions`, or a finding's `actions`, offer them. Each opens a modal naming the commit line and the integration branch, with pinned revisions (T7), then calls `runAct`. A refusal is shown as given. `launch.ts` holds the launch targets: today that's `terminal` (T8) with the clipboard as fallback, and later chat can be added beside it without touching the callers. Prompts come from one table, the same text as `promptText` in `logic.js`.

### D-REVIEW-UI: review and health
- **Review queue.** Branch work first, then landed work.
- **A task's review.** The gate summary and gates, each acceptance item with its proof, the evidence file (opened in the editor), and the diffstat. A file opens `vscode.diff` between `ws-review:` URIs served by a `TextDocumentContentProvider` over `--show`. A binary file opens nothing and says so.
- **Health.** A tree of findings, plus diagnostics in the Problems panel on the workstream's tasks file, at line 1. Each finding's actions are quick fixes that go through the same confirm.
- **Budget.** Rows with used against limit, run only when the view is visible.

## 4. Tasks

| ID | Title | Blocked by |
|---|---|---|
| VS-01 | The snapshot says what's allowed and what to watch | |
| VS-02 | `ws review --show` gives one side of a diff | |
| VS-03 | The extension's package, CLI module and test harness | |
| VS-04 | Registry, tasks, documents, status bar and live refresh | VS-01, VS-03 |
| VS-05 | Writes through `ws act`, and launching in a terminal | VS-04 |
| VS-06 | The review queue and diffs in the diff editor | VS-02, VS-05 |
| VS-07 | Health in the Problems panel, and the budget | VS-06 |
| VS-08 | Prove it in VS Code, and write down what's true | VS-07 |

- VS-01, VS-02 and VS-03 share no files, so they can run at once.
- VS-04 to VS-07 all touch `ui/vscode/package.json` and `src/extension.ts`, so they're chained.
- VS-08 is foreground: it needs the owner to see it.

## 5. End-to-end verification

1. `make vsix` builds the package, and `code --install-extension` (the app bundle's CLI) installs it into VS Code 1.139.
2. On a sample project built with the real CLI, from an installed wheel:
   - every view draws;
   - a pause commits through `ws act`;
   - a stale pause is refused, with a shell commit made while the modal was open, and HEAD and the tree stay unchanged;
   - a diff opens in the diff editor for a branch task after main moved, showing only the task's changes;
   - a health finding shows in Problems and its quick fix unclaims;
   - Run starts the configured agent in a terminal, and with no setting the prompt is copied.
3. This repo is viewed read-only.
4. The owner sees it drawn.
5. `ui/vscode/README.md`, `docs/decisions/0017-vscode-extension.md` (shown, and not proven) and the plan's status row are written.
