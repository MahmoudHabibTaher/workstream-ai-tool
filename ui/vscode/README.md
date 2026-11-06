# Workstreams for VS Code

Shows a workstream project in VS Code's own UI. Every fact comes from the `ws` CLI and every write goes through `ws act`; the extension only arranges what the CLI returns (decision 0016).

## Install

```sh
make vsix
code --install-extension ui/vscode/workstreams.vsix
```

The extension runs only in trusted workspaces, and not in virtual ones.

## What it shows

The **Workstreams** view container holds the **Registry**, **Review**, **Health** and **Budget** trees.

- Each open workstream shows its status, `done/total` and its count of health errors. It opens to its wave line, then its phases in order, then each phase's tasks by priority, with badges such as `★ ready`, `waits on …` and `claimed 1h`. Last comes **Documents**.
- A task's tooltip holds its summary, acceptance items and verify commands. Repo text is shown as plain text, never as markup.
- **Show done** in the view's title bar adds the closed workstreams, and **Hide done** takes them away again. **Refresh** reads the snapshot again.
- Under **Documents**, Plan, Progress, Decisions and Handoff each open in Markdown preview.
- The status bar shows the active workstream's wave line and error count. Clicking it focuses the view.
- The view stays current without Refresh. The extension watches every path in the snapshot's `refresh` list, waits until changes stop for 300 ms, and then reads one snapshot per burst. A claim, a commit or a new evidence file made from a shell shows up on its own.

### Review

The **Review** tree is `ws review --queue`: **On a branch** first, then **Landed**. Each task opens to what `ws review --checks` says about it.

- Its range, then its gate summary with each gate under it. A landed task says its gates ran when it landed.
- **Acceptance and proof**: each item with the proof its evidence quotes, or `Nothing quoted.`
- **Evidence** opens the evidence file in the editor. A landed task's opens as the file; a branch's opens read-only from the branch.
- **Files** lists the diffstat. A file opens in the diff editor, each side read through `ws review --show`, so a branch's old side is its merge base and not main's tip. A file the side doesn't have is empty there. A binary file opens nothing and says so.

### Health

The **Health** tree is the snapshot's `health` findings: **Errors**, then **Warnings**, in the CLI's order, or `Nothing to report.` A finding that names a workstream is also in the Problems panel, at line 1 of that workstream's tasks file. Its quick fixes are the writes the finding offers, such as **Unclaim** on a stale claim, and they open the same confirm as the menus do. When the finding goes, so does its diagnostic.

### Budget

The **Budget** tree is `ws audit context --json`: each role's tokens against its limit, the share used, and `over` when it is over. It runs only while the view is in sight, when it comes into sight and on **Refresh**; the reloads on file changes don't run it.

## What it does

A workstream's, task's or finding's context menu holds only what the snapshot offers there: a row's `actions`, or a finding's.

- **Pause**, **Resume**, **Sync Progress** and **Unclaim** open a modal naming the commit line and the integration branch. Confirming runs `ws act` against the revisions of the snapshot the item was drawn from, so a change made after you saw it is refused. A refusal is shown as `ws act` gave it. When the extension already holds a newer snapshot, the modal says the write will be refused.
- **Run**, **Coordinate**, **Close** and **Abandon…** on an open workstream start your agent in a terminal at the project root, with the prompt as its last argument; no shell parses it. Abandon asks for the reason first. With no agent command set, the prompt goes to the clipboard instead.

## Settings

- `workstreams.wsCommand`: the argv that runs the CLI, `["ws"]` by default. No shell parses it. Point it at a checkout's own code with `["python3", "-B", "-m", "workstream"]` and that checkout's `src` on `PYTHONPATH`.
- `workstreams.agentCommand`: the argv that starts your coding agent, empty by default. The prompt is added as the last argument.

When the CLI can't be started, the extension says so, names this setting, and runs nothing else. A window whose folders aren't workstream projects gets one message and nothing more.

## Develop

- `npm ci` in `ui/vscode` (a worktree's setup runs it).
- `make test` runs the logic tests under node, through `tests/test_vscode_files.py`.
- `make test-vscode` builds with `tsc` and runs the integration tests in the VS Code installed at `/Applications/Visual Studio Code.app` (override with `VSCODE_EXECUTABLE`). Nothing is downloaded. They run the checkout's own CLI, not the `ws` on PATH.
- Logic lives in modules that never import `vscode`, written in erasable TypeScript so `node --test` runs the `.ts` files directly.
