# Decisions: VS Code UX redesign

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-10, user): scope approved

The owner chose native views (keeping 0016) over a webview detail panel.
VS Code targets: Terminal, Copilot Chat and the Claude Code extension. Air has no VS Code version.
Copilot Chat must be installed in VS Code for the manual check; it isn't today. **Closed.**

## D002 (2026-11-12, VX-01): "waiting on" comes only from the snapshot's `waitingOn`

`detail.ts` drops the `waits on` badge that `format.ts`'s `badgesOf` works out from `blockedBy`, and the task row's description takes "waiting on" from `task.waitingOn` instead. This follows jetbrains_ux T3: the IDE doesn't compute graph facts. `format.ts` wasn't in this task's files, so I didn't change it.
Rejected: changing `badgesOf` in `format.ts` to read `waitingOn`. That touches the Registry view's badges, which VX-02 replaces anyway. **Closed.**

## D003 (2026-11-12, VX-01): the builders mint stable ids for every section, item and graph node

Each graph node's id is its path from the root, so a task that appears twice still gets two distinct ids. Section and item ids come from their position under the task's or overview's id. This keeps `TreeItem.id` stable across reloads (plan T2).
Rejected: leaving ids to the views. **Closed.**

## D004 (2026-11-12, VX-01): the snapshot shape types live in `registry.ts`

`SnapTask`, `Scope`, `Baseline`, `BaselineKey` and the widened `WsSnapshot` sit next to the existing `WsSnapshot`. `DetailRow` (the registry row's other fields) sits in `detail.ts`.
Rejected: a separate types module. **Closed.**

## D005 (2026-11-12, VX-02): the Workstreams view's id is `workstreams.list`, and the Tasks and Task views are `workstreams.tasks` and `workstreams.task`

Both linked views use `when: workstreams.selected`, a context key the extension sets on the first selection. The Task view therefore shows (empty) once a workstream is picked, not only once a task is. That follows plan T2's "only with a workstream selected". The write menus now match `/^workstreams\.(list|tasks|health)$/`, so Unclaim is offered on a Tasks item, and the launches match `view == workstreams.list`. The status bar focuses `workstreams.list`.
Rejected: keeping the id `workstreams.registry` under the name "Workstreams", which would leave a misleading id behind; and a second `taskSelected` key for the Task view. **Closed.**

## D006 (2026-11-12, VX-02): selection lives in the store and is set by item commands, not by `onDidChangeSelection`

`Store.select`/`selectTask` and their own `onSelect` listeners do this, so a selection redraws only Tasks and Task, and doesn't run the reload paint, diagnostics and watchers that `onChange` does. A workstream row runs the hidden `workstreams.selectWorkstream`, and a task row and a dependency run `workstreams.selectTask(root, ws, id)`. A jump also reveals the task in the Tasks view when that view is visible, as a best effort. The selection survives a reload.
Rejected: listening to `TreeView.onDidChangeSelection`, which an integration test can't drive without `reveal`, and which doesn't fire again when you click the row that is already selected. **Closed.**

## D007 (2026-11-12, VX-02): the old Registry builders are gone, and so is the Documents node and its `workstreams.openDocument` command

`views/registry.ts` is deleted. `logic/registry.ts` keeps only the snapshot types (D004), `DOC_LABELS`, `activeWorkstream` and `statusText`. `Node`, `workstreams`, `workstreamChildren`, `phaseChildren`, `documentChildren` and `shown` are removed, along with their tests in `test/logic/registry.test.ts`, and `test/logic/actions.test.ts` now checks the same offers through `listRows`/`taskRows`. Until VX-03 draws the Overview, whose Documents section opens through `vscode.open`, the workstream documents have no view. The Tasks view keeps the wave line above the phases.
Rejected: keeping a Documents node under each row for one task, which would make the list a tree again. **Closed.**

## D008 (2026-11-12, VX-02): files outside the expected list

I touched `src/logic/registry.ts`, which the brief's "Builds on" note asked to retire. I also touched `src/commands.ts`, where only the `Target` type changed to the new view node types, and `tests/test_vscode_files.py`. That last file pinned the old view ids, the `registry|health` menu regex and `views/registry.ts`, so `make test` could not pass without changing it. It now pins the new ids, regexes and files.
Rejected: leaving those checks failing. **Closed.**

## D009 (2026-11-12, VX-03): Graph and Overview sit between Task and Review, with `when: workstreams.selected`

The views are `workstreams.graph` ("Graph") and `workstreams.overview` ("Overview"), right after the Task view, so the linked views stay together and Review still follows them (plan D-REVIEW-UI). Both use the existing `workstreams.selected` key (D005), and their titles show the selected workstream. Graph nodes run `workstreams.selectTask`. They carry a plain `graphTask`/`graphRepeat` contextValue, not the write offers, because the write menus' regex (D005) names only list, tasks and health.
Rejected: putting them after Budget, which would split the linked views; offering Unclaim on graph nodes, which would widen the menu regex that `tests/test_vscode_files.py` pins. **Closed.**

## D010 (2026-11-12, VX-03): The Overview and Task views share one way of drawing sections

`views/task.ts` now exports `detailItem`, `sectionNodes` and `detailChildren`, and `views/overview.ts` uses them. A claim item jumps through `workstreams.selectTask`, and a document opens through `vscode.open`. The registry row comes from `listRows(root, snapshot, true)`, so a closed workstream's Overview still has its row.
Rejected: a copy of the Task view's `getTreeItem` in overview.ts. **Closed.**

## D011 (2026-11-12, VX-03): `tests/test_vscode_files.py` touched, outside the expected files

Its two view-order pins now include `workstreams.graph` and `workstreams.overview` after `workstreams.task`. Without that change `make test` could not pass once the views are declared. This is the same situation as D008.
Rejected: leaving the pins failing. **Closed.**

## D012 (2026-11-12, VX-04): the four groups are separator groups, not submenus, and follow JetBrains' split

Both the item and title menus use the groups `1_run` (Run, Coordinate, Close, Abandon), `2_workstream` (Pause, Resume, Sync), `3_task` (Unclaim) and `4_open` (Plan, Progress, Decisions, Handoff; Open Diff and Open Evidence on Review items). This is the split jetbrains_ux's D-MENUS uses. The existing `when` clauses of the writes and launches are kept word for word, as `tests/test_vscode_files.py` pins them. The Open group has no tasks file, because the workstream snapshot's `paths` gives no tasks-file path.
Rejected: `contributes.submenus`. The pin reads `m["command"]` from each `view/item/context` entry, and a submenu entry has no `command`. **Closed.**

## D013 (2026-11-12, VX-04): the linked views' title menus act on the selection through context keys

`workstreams.selectedItem` and `workstreams.selectedTaskItem` hold the contextValues of the selected workstream's item and task's item. Those items are built as the Workstreams and Tasks views build them, and kept in `api.picked`. The Tasks, Task, Graph and Overview titles match those keys with the same regexes the item menus use on `viewItem`. A command run with no item (from a title) uses the picked item, so it pins that item's drawn revisions. List, Review, Health and Budget titles show only Refresh (and Show/Hide Done).
Rejected: title entries with no gating, which would show writes the snapshot didn't offer. **Closed.**

## D014 (2026-11-12, VX-04): `src/commands.ts` touched, outside the expected files

It gains the `picked` fallback in `write` and `start`, and the four `workstreams.open<Doc>` commands. The commands are registered there, so there is nowhere else for them. The welcome views also need a new `workstreams.hasProject` context key, set in `extension.ts`.
Rejected: registering the Open commands in extension.ts while the writes stay in commands.ts. **Closed.**

## D015 (2026-11-12, VX-04): the status bar while a task is claimed

The bar shows `$(checklist) <ws> · <task> · <age>`, then ` · N errors`, which mirrors jetbrains_ux D024. The claimed task is the first `in-progress` task of the active workstream's own snapshot, and the age is left out when the claim has no `startedAt`. The wave line still shows when nothing is claimed, and the age redraws every minute. The tooltip stays the literal 'Show the Workstreams view' because `tests/test_vscode_files.py` requires every `.tooltip =` to be a literal or `tooltip(`. `claimedTask` and `claimLine` live in `logic/format.ts`, so `registry.ts` is unchanged.
Rejected: a tooltip naming the claim (it fails that pin). **Closed.**
