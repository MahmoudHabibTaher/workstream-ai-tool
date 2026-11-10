# vscode_ux: plan

## 1. Context

Bring Plan A's design and launch targets to the VS Code extension (M9, decision 0017). It keeps 0016's native UI: no webview. It reuses Plan A's CLI facts (`unblocks`, `waitingOn`, `scope`, `baseline`, `ws launch check|argv|agents`), so it depends on `jetbrains_ux`.

**Outcome:** in VS Code, the Workstreams container has these views, linked by selection:
- **Workstreams**, the list;
- **Tasks**, the selected workstream's tasks, by phase;
- **Task**, the selected task's sections, as tree items: dependencies that jump, files that open, acceptance, verify, notes;
- **Graph** and **Overview**.

Review, Health and Budget stay. Run opens a launch flow (quick picks) with pre-flight, a task pin, presets and an editable prompt. It starts the agent in a terminal, in Copilot Chat in agent mode, or in the Claude Code extension's panel.

**Out of scope:** a webview. Cursor. Air, which has no VS Code version. New kinds of write.

## 2. Traps

### T1: no agent names outside one file
`tests/test_vscode_files.py:24-26` forbids `claude|copilot|…` in `ui/vscode/src`. Chat targets live in `src/chat.ts`, which the test allows by name.

### T2: one `TreeDataProvider` per view, linked through the store
VS Code has no master-detail widget. Selection in Workstreams sets the store's selected workstream (`ui/vscode/src/logic/store.ts`). Tasks, Graph and Overview redraw from it, and selecting a task drives Task. `createTreeView` is called at `ui/vscode/src/extension.ts:120-122`, and the views are declared at `ui/vscode/package.json:60`. Each new view needs both, plus `when` clauses so it shows only with a workstream selected. Expanded state survives a reload only when `TreeItem.id` stays stable, as `views/registry.ts` does today.

### T3: the Copilot Chat command takes an options object
`workbench.action.chat.open` accepts `{query, mode}`. The mode for agent sessions is `agent`, and an older build calls it `edit`. It only exists while the Copilot Chat extension is enabled, so check `vscode.commands.getCommands()` first. Copilot Chat isn't installed in the owner's VS Code (`~/.vscode/extensions` has only `anthropic.claude-code-2.1.318` and our extension), so VX-07 needs it installed.

### T4: the Claude Code extension takes a prompt through its URI handler
In `anthropic.claude-code-2.1.318`, the URI `vscode://anthropic.claude-code/open?prompt=<text>` opens a new panel with the prompt filled in. Its `claude-vscode.editor.open` command takes positional arguments that aren't documented. Use the URI through `vscode.env.openExternal`. A test asserts the URI is built with `URLSearchParams`, so repo text can't break the query.

### T5: the logic stays out of `vscode`
The logic modules never import `vscode` and run under `node --test` in `make test` (0017). New view builders go in `src/logic/` as plain data, like `logic/registry.ts`.

## 3. Design

### D-VIEWS: five linked native views
`views/workstreams.ts` (the list, replacing `views/registry.ts`), `views/tasks.ts`, `views/task.ts`, `views/graph.ts` and `views/overview.ts`, built from `logic/detail.ts`. A task item's description shows status, phase and "waiting on". Task items run `workstreams.selectTask`, and file items run `vscode.open`. Rejected: a webview (0016).

### D-MENUS: view title menus and palette
`view/title` and `view/item/context` menus group Run, Workstream, Task and Open, gated by `contextValue` as today (`logic/actions.ts`). Each view has `viewsWelcome` empty states. The status bar shows the claimed task and its age.

### D-LAUNCH: a quick-pick launch flow
A chain of quick picks:
1. the checks, with a blocking one ending the flow with its message;
2. the target, from those available;
3. for a terminal, the agent, effort and permissions (from `ws launch agents`);
4. an input box holding the prompt.

The last choices are kept in `workspaceState`. `launch.ts` `TARGETS` gains `chat.ts`'s two targets before the clipboard.

## 4. Tasks

| id | title | blocked by |
|---|---|---|
| VX-01 | Detail builders in logic/: list rows, task sections, graph, overview | – |
| VX-02 | Workstreams, Tasks and Task views linked by selection | VX-01 |
| VX-03 | Graph and Overview views | VX-02 |
| VX-04 | Menus, welcome views, status bar | VX-03 |
| VX-05 | Quick-pick launch flow with pre-flight and presets | VX-04 |
| VX-06 | Copilot Chat and Claude Code extension targets | VX-05 |
| VX-07 | Prove it in VS Code by hand | VX-06 |

## 5. End-to-end verification

VX-07, with the owner, who installs Copilot Chat in VS Code first. Build and install the `.vsix` (`make vsix`) and open the wheel-built sample. The five views draw and stay linked, and a dependency jumps. A blocked launch stops with its message. Run starts the agent in a terminal with the preset's flags. Copilot Chat opens in agent mode with the prompt. The Claude Code panel opens with the prompt filled in. A stale Pause is refused. `make test` and `make test-vscode` pass, and 0019 gains the VS Code results.
