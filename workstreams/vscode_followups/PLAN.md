# VS Code follow-ups

## 1. Context

The VS Code hand check (vscode_ux VX-07, decision 0019) passed, and the owner raised three problems. This workstream fixes them, and it settles vscode_ux D020, which is still open.

- **Crowded panel.** Eight views sit side by side in one container. Review, Health and Budget each move to a panel container of their own, the way the JetBrains tool window gives each one a tab. Workstreams keeps its five linked views.
- **Unreadable blocked launch.** A launch blocked by its checks shows one long error toast today: `Run alpha is blocked: validate: …; wave: …; claim: …`. Instead it becomes a read-only quick pick: one row per check with an icon, blocking checks first.
- **Too many steps.** A Terminal launch asks up to six things: checks, target, agent, effort, permissions and the prompt. Two changes shorten it without removing any choice:
  - the first pick offers the last full choice as one row;
  - agent, effort and permissions merge into one pick of combinations.
- **D020.** The launch menus decide from the row's status (`launches()` in `actions.ts`). The snapshot already gives each row a `launches` list holding each kind's prompt, and JetBrains uses it (`launchOf` in `Actions.kt`). VS Code should use it too.

**Out of scope:** `src/workstream` (the snapshot already has what's needed); `ui/jetbrains`; `ui/mod`; webviews; Cursor; a `run-task` launch on tasks.

## 2. Traps

### T1: the view list is pinned in the file tests
`tests/test_vscode_files.py:166-168` and `:177-180` assert the exact view ids under `views["workstreams"]`. Moving Review, Health and Budget to other containers breaks both. Update those asserts in the same task: they are what pins the new layout.

### T2: keep the main container's id
`extension.ts:170` focuses `workstreams.list`. The owner has already dragged the `workstreams` container into the panel, and VS Code remembers where a container sits by its id. Keep the id `workstreams` for the main container, and move it from `activitybar` to `panel` in `viewsContainers`. Give each new container a new id (`workstreams-review`, `workstreams-health`, `workstreams-budget`) and an `icon`, which panel containers need too. The view ids stay the same, so every `view == …` menu clause and the welcome view keep working.

### T3: the integration test reads the blocked launch from the toast
`ui/vscode/test/integration/suite.ts:443-447` checks `api.shown.at(-1)` against `/^Run alpha is blocked: …/` and asserts `offered.length === 0`. The new list is a pick that goes through `FlowUi`, so it needs its own `Step` (`blocked`), and the scripted answers must cover it. Keep these rules:
- a blocked launch still launches nothing, whatever row is picked;
- `say` still gets one short line, so the test API and the status message still record what happened.

### T4: the launch menus and the prompts each live in two places
These places hold the old rule today:
- `launches()` (`src/logic/actions.ts:30`) offers every launch on any open row;
- `contextValue` adds one `launch` word;
- `package.json` matches `/(^| )launch( |$)/`, which `tests/test_vscode_files.py:119-126` pins;
- `test/logic/menus.test.ts:58,67` and `actions.test.ts:34` test that rule.

The prompts sit in `PROMPTS` (`src/logic/launch.ts:11`), and `test_one_prompt_table_with_the_web_uis_text` (`tests/test_vscode_files.py:131-140`) pins them against the web UI's `logic.js`. Two more details:
- The snapshot's abandon prompt ends in `": "` with `ask: "reason"`. The extension fills a `<why>` placeholder instead (`needsReason`, `promptText`).
- `Row` in `src/logic/format.ts:32` has no `launches` field.

### T5: the flow's steps are scripted by name
`suite.ts:419-496` answers picks by `Step` and asserts the exact step order. For example, it expects `['target', 'agent', 'effort', 'permissions', 'checks']`. Merging agent, effort and permissions changes `Step` and every one of those asserts. Two more things the new flow must keep:
- The agent's own check (`launchFlow.ts:113`) runs after the preset is known. Repeating the last choice must still run it.
- `levels()` (`logic/launch.ts:93`) puts `''` ("none (no flag)") first, so "no effort flag" is a real choice that the combinations must keep.

### T6: what was last chosen can go stale
`LAST_KEY` holds the target, agent, effort and permissions. Any of them can stop being valid:
- a chat extension gets disabled;
- `workstreams.agentCommand` gets cleared;
- a preset drops a level.

Offer the repeat row only when every part is still offered. Otherwise leave it out and say nothing.

## 3. Design

### D-PANELS: four panel containers
In `package.json`, `viewsContainers.panel` declares four containers:
- `workstreams` (Workstreams) holds list, tasks, task, graph and overview;
- `workstreams-review` holds review;
- `workstreams-health` holds health;
- `workstreams-budget` holds budget.

There is no activity bar entry. Budget's audit still runs only while its view is visible (vscode_extension D030), so nothing changes in `health.ts`. The file tests pin the four containers and each one's views. The integration suite keeps passing unchanged, because view ids don't move.
Rejected: one Health container holding Budget too; leaving them in the activity bar.

### D-BLOCKED: the checks as a read-only list
When any check blocks, `passes()` (`launchFlow.ts:52`) calls `flow.ui.pick('blocked', …)`.
- The title reads `Run alpha is blocked by 3 checks`.
- Each check gets one row: `$(error)` for blocking, `$(warning)` for a warning, `$(pass)` for one that passed, in that order. The label is the check's id and the description its message.
- Picking a row whose check comes from the health findings (`validate`, `claim`) focuses `workstreams.health`. Any other pick, or Escape, closes the list. Nothing launches either way.
- `say` gets the short line `Run alpha is blocked by 3 checks`.

The list's rows and their order are worked out by a pure `blockedChoices(checks)` in `logic/launch.ts`, which unit tests cover. The warning-only path stays as it is.
Rejected: a modal with the checks as detail text, which reads less well than icon rows; keeping the toast.

### D-LAUNCHES: the snapshot owns the launch offers and their prompts
- `Row` gains `launches?: { kind; prompt; ask? }[]`.
- `contextValue` writes `launch:<kind>` for each offered kind, and `launches(row)` returns those kinds.
- Each menu matches `/(^| )launch:run( |$)/` and so on.
- `commands.ts` takes the prompt from the row's offer and appends the reason when `ask === 'reason'`. The `PROMPTS` table and `promptText` go away.
- The file test changes from "same text as logic.js" to "no `Use the ws-` text in the extension's sources".

This closes vscode_ux D020.
Rejected: keeping `PROMPTS` beside the snapshot, which leaves two copies of one text.

### D-SHORTER: repeat-last, then one combined pick
- **The first pick** (the target pick) leads with a `$(history)` row such as `Terminal · Claude Code · medium · acceptEdits`, described as "last used". It appears only while every part is still offered (T6). Picking it skips straight to the agent's own check, then the prompt.
- **The combined pick.** Picking a terminal fresh opens one `preset` pick listing every agent × effort × permissions combination, the remembered one first. The `workstreams.agentCommand` agent appears as a single row. Typing filters the list. `matchOnDescription` is already on.

The combinations and the repeat row are built by pure functions in `logic/launch.ts` (`combos`, `repeatChoice`), which unit tests cover. `Step` becomes `blocked | checks | target | preset`.
Rejected: a multi-step quick pick with a back button, which has the same number of steps.

## 4. Tasks

Each task touches `ui/vscode/test/integration/suite.ts` or `package.json`, so they run as one chain. VF-05 runs in the foreground with the owner.

| id | title | blocked by |
|---|---|---|
| VF-01 | Review, Health and Budget in panel containers of their own | |
| VF-02 | A blocked launch lists its checks | VF-01 |
| VF-03 | Launch menus and prompts from the snapshot (closes D020) | VF-02 |
| VF-04 | Repeat-last row and one combined preset pick | VF-03 |
| VF-05 | Prove it in VS Code by hand | VF-04 |

## 5. End-to-end verification

VF-05, with the owner: build and install the `.vsix` (`make vsix`), and open a sample built from the wheel. The owner sees:
- four panel tabs: Workstreams with its five linked views, plus Review, Health and Budget;
- a blocked Run showing one row per check, blocking first;
- a second Terminal launch taking two picks (repeat row, then prompt);
- a fresh Terminal launch using the combined pick;
- Abandon asking for a reason and passing it on.

`make test` and `make test-vscode` pass. 0019 and the README record the result.
