# 0017: The VS Code extension

Decided while building M9. The workstream's own `DECISIONS.md` has the smaller calls (D001 to D032), and [the guide](../../ui/vscode/README.md) has how to use it. Why native UI rather than a webview over `ws serve`: [0016](0016-native-ide-ui.md).

**The extension decides nothing.** Every fact comes from `ws snapshot`, `ws review` or `ws audit context`, and every write from `ws act`. The TypeScript only arranges what the CLI returns. When a view needed a fact the CLI didn't give, the fact went into Python first: the snapshot's row `actions` and `refresh` paths (VS-01), and `ws review --show` for one side of a diff (VS-02).

**Writes are pinned to what was drawn.** The confirm is VS Code's native modal, which can't redraw while open, so whether the view is out of date is judged when it opens. `ws act` checks the registry's and the queue's hashes against the snapshot the item was drawn from, so a change made while the box is open is still refused.

**Launches start a process, not a shell line.** `workstreams.agentCommand` is an argv, and the prompt is its last argument, so no shell parses repo text. With no agent command set, the prompt goes to the clipboard. A chat target can join `launch.ts` later without touching its callers.

**Tests run against the installed VS Code.** `make test-vscode` uses `/Applications/Visual Studio Code.app` through `@vscode/test-electron` and downloads nothing, so, like `make test-mod`, it's local only. The logic modules never import `vscode` and run under `node --test` inside `make test`.

## Rules for changing it

- **One writer.** Only `runAct` in `cli.ts` writes, through `ws act`. A new kind of write starts in `ws act`.
- **Every argv is checked against the real CLI.** `tests/test_vscode_files.py` runs each command `cli.ts` builds.
- **Repo text is never markup.** Tooltips and labels are plain strings; the same test scans for markdown and HTML sinks.
- **No runtime dependencies.** Dev dependencies are locked; see D010 for the fifth.

## What was shown

On macOS, VS Code 1.139.0 (arm64), Python 3.14, on 2026-11-06. The owner drove VS Code by hand; the coordinator ran the shell side and read git afterwards.

| Check | Result |
|---|---|
| Package and install | `make vsix` packaged `workstreams.vsix` (23 files, 37.24 KB); `code --install-extension` installed it, listed as `workstream.workstreams@0.1.0` |
| Sample project from an installed wheel | `ws` 0.1.0 from a wheel in a clean venv built two workstreams, a stale claim and a branch, with main moved after the branch was cut. The extension's `wsCommand` pointed at the venv's `ws` |
| Views | Registry, Review, Health and Budget drew, and the Problems panel listed the findings on `workstreams/alpha/tasks_list.json` |
| A pause landing | `fb11a55 alpha: pause (ws act)` and `37d303e beta: pause (ws act)` |
| A stale pause refused | With the alpha Pause box open, a shell commit (`90c152e touch`) changed the registry. Confirm was refused as stale, as the owner reported, and no alpha pause commit followed |
| A branch diff after main moved | `shared.txt` under Review → On a branch → S-2 opened side by side, `two` → `TWO`, against the merge base rather than main's tip |
| A quick-fix unclaim | The stale-claim finding's quick fix landed as `a416a01 alpha: unclaim S-1 (ws act)` |
| Run in a terminal | Without `agentCommand`, the prompt went to the clipboard as designed. With it set, a terminal opened and the agent got `Use the ws-run skill to run workstream alpha.` as its argument |
| This repo, read-only | Viewed in VS Code with no writes; HEAD, status and refs were the same afterwards |
| Automated | `make test` and `make test-vscode` pass, including the integration suite in that VS Code |

## Not proven

- **A real agent started by Run.** The sample's agent command printed its argument instead of starting Claude Code, so nothing ran a workstream from VS Code.
- **The stale refusal's exact text.** The owner confirmed the refusal; the message wasn't copied from the screen. The same text is checked by the integration test.
- **Cursor, and other OSes.** Only VS Code on macOS. Cursor was out of scope.
- **Several active workstreams.** The status bar shows the first active one (D017).
- **A write to a real project.** Writes ran on the sample only, by design.
- **A long session**, or a large queue. Runs lasted minutes.

## Left open

- D010: `@types/node` as a fifth dev dependency.
- D029: a workstream's tasks file is found from the order of its snapshot's `watch`; a `paths.tasks` field in the snapshot would be cleaner.
