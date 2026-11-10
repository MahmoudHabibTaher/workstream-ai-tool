# jetbrains_ux: plan

## 1. Context

Another IntelliJ workstream plugin is easier to use than our UIs; the owner asked ours to favour its design. Ideas only, never its code or text.

**What the comparison found.** These are what make the other workstream plugin easier to use, all of which we lack:
1. Master-detail: a workstream list on the left (status icon, `done/total`, status, the open claim, problem count) and detail on the right.
2. A **Tasks** table (status, id, phase, title, waiting on) with a task pane under it. That pane holds the summary, a jump link for each "depends on" and "unblocks" task, files that open on click, acceptance, verify commands, notes and the claim's age. We put all of this in tooltips.
3. A **Graph** tab (the dependency tree) and an **Overview** tab (document links, open claims, scope, verify commands, baseline, the registry row).
4. Grouped toolbar menus, a Tools menu, empty states with a link to the next step, double-click to open a task's entry in its file, and a status bar showing the claimed task and its age.
5. A launch dialog with pre-flight checks (a blocking check disables OK), a task pin, the agent's effort and permission choices with the resulting command shown, an editable prompt and a choice of target: **Terminal, Copilot Chat or Air**. It remembers the last choices.

We don't adopt their raw `tasks.py` sub-commands (start, done, set, clear and so on). Our one writer is still `ws act`.

**What the owner chose (2026-11-10):** master-detail with Review/Health/Budget kept as their own tabs; Air reached by guarded reflection, falling back to the clipboard; agent presets that `ws` maps to flags; VS Code targets Terminal, Copilot Chat and the Claude Code extension, in native views, keeping 0016; the pane gets the layout and pre-flight, and still only fills the prompt box.

The JetBrains plugin (M10, decision 0018) shows everything as one Registry tree, with a task's facts in its tooltip. This workstream rebuilds the Registry tab as master-detail, adds the toolbar, menus and launch dialog described above, and adds Copilot Chat and Air as launch targets. The facts behind these (pre-flight, agent flags, unblocks, scope, baseline) don't exist in the CLI yet. They go into Python first (0016: "the extension decides nothing"), and the other two workstreams reuse them.

**Outcome:** in IntelliJ IDEA 2026.3 and Android Studio 2026.2:
- the Workstreams tab is a list with Tasks, Graph and Overview detail tabs;
- Run opens a launch dialog that starts the chosen agent in a Terminal tab, in Copilot Chat or in Air's new-session prompt;
- writes stay pinned and a stale one is still refused.

**Out of scope:** new kinds of write. A console of raw command output (our only write is `ws act`, whose result is already shown). Notifications beyond health. PyCharm. Marketplace publishing. VS Code and the pane, which are Plans B and C.

## 2. Traps

### T1: agent names are banned from core and from the IDE sources
`tests/test_no_project_literals.py:14-17` forbids `claude|copilot|anthropic|openai|codex` in `src/workstream/`, and `tests/test_jetbrains_files.py:24-26` forbids the same in `ui/jetbrains/src`. Agent facts live only in `src/workstream/assets/adapters/*.toml`, which the scan skips (its suffixes are `.py .md .js .css .html`). So agent flags go in a new `[launch]` table in each adapter TOML. A chat target has to name its plugin's classes, so those names live in one file, `ChatTargets.kt`, which the scan allows by name. Every other file stays clean, and the test says so.

### T2: the launch prompts have owners and copies
`src/workstream/snapshot.py:42` `LAUNCH_PROMPTS` owns them. `tests/test_jetbrains_files.py:160-166` fails if any Kotlin file holds a prompt's text, and `tests/test_schema.py:88` holds the launch `kind` enum equal to `LAUNCH_PROMPTS`. A new "run this task" launch is a new `LAUNCH_PROMPTS` entry, `run-task`, with `{task}`. The schema's enum changes with it, and the Kotlin builds nothing.

### T3: the IDE must not compute graph facts
"Waiting on", "unblocks" and "ready" are graph facts. Today's badges (`ui/jetbrains/.../logic/Format.kt:80` `badgesOf`, ported to TypeScript at `ui/vscode/src/logic/format.ts:64` and `ui/mod/hooks/views/detail.tsx:22`) only rearrange fields the snapshot gives. Add `unblocks` (ids) and `waitingOn` (ids of unfinished `blockedBy`) to each snapshot task, built from `graph.py`, which `ws show` already uses for "what it unblocks". Add `scope` (from the queue) and `baseline` (key, result, recorded-at) to `ws snapshot -w`. `schema/snapshot.schema.json` is closed (`additionalProperties: false`), so the schema changes in the same task.

### T4: a chat prompt can't assume the skills are there
"Use the ws-run skill…" works in an agent only where `ws adapt` installed that agent's skills: `.workstream/adapters.json` lists `claude-code` here, not `copilot-cli`. Copilot Chat reads `.github/skills`, which the `copilot-cli` adapter writes. Air's agents are unknown. Pre-flight reports "skills not installed for <agent>" as a warning, from `adapt.py`'s installed list (`adapt.py:296`). A chat prompt also says where the repository root is when the IDE's project folder isn't it, as that plugin found.

### T5: the other plugins are optional and load in their own classloaders
Copilot and Air aren't dependencies, and their classes sit in content modules with separate classloaders, so `Class.forName` from our loader fails. Load each class through the classloader of an action that the plugin registers, found with `ActionManager.getAction(id)`, and check the plugin is enabled first. Air starts a new session only through non-public classes, so its target is guarded: any reflective failure goes to the clipboard with a line saying why. That's the owner's call, recorded as an exception to 0018's "no internal API" rule. `verifyPlugin` can't see reflection, so it still says Compatible.

### T6: repo text in a detail pane is markup
The task pane and Overview need links and lists. `JEditorPane` with HTML is a markup sink that `tests/test_jetbrains_files.py:29-31` (`SINK`) flags unless the text goes through `Text.kt`'s `Text.html`. Build both panes with the Kotlin UI DSL (`panel { }` with labels and `ActionLink`s), or put every string through `Text.html`. Add the new view files to the test's list of drawing files (`REGISTRY`, `REVIEW` and so on, at lines 36-41).

### T7: writes stay pinned to what was drawn
Pause, Resume, Sync and Unclaim pass the drawn `revisions` (0018 D017). Moving them from tree nodes to list rows and toolbar menus must keep the node's `revisions`, not re-read the snapshot when the confirm opens. `WsActionsTest.kt` already covers this, so extend it rather than write a new path.

### T8: every argv is checked against the real CLI
`tests/test_jetbrains_files.py` runs each argv `Cli.kt` builds. The new `ws launch check` and `ws launch argv` calls must be added there, or the test misses them.

## 3. Design

### D-FACTS: snapshot facts for the detail views
Each task gains `unblocks` and `waitingOn` in `snapshot.py`, from `graph.py`. `ws snapshot -w` gains `scope` and `baseline`. Update the schema and add tests to `tests/test_snapshot.py` and `tests/test_schema.py`. There's no `snapshotVersion` bump for added fields, as in 0010.

### D-PREFLIGHT: `ws launch check`
`ws launch check -w <id> --kind <kind> [--task T] [--agent A] --json` prints `{checks: [{id, ok, blocking, message}]}`. The checks are:
- validate errors (blocking);
- the wave's state: no actionable task blocks `run`;
- a claim already open (a warning for `run-task`, blocking for `run`);
- a dirty tree on tracking paths (blocking);
- a baseline that isn't recorded (a warning);
- the agent's skills not installed (a warning, T4).

It lives in a new `src/workstream/launch.py`, with each check reusing `validate`, `wave`, `gitutil` and `adapt`. Tested in `tests/test_launch.py`.

### D-PRESETS: agent presets in the adapter TOMLs
A `[launch]` table holds the command and how effort and permissions map to flags. For claude-code, that's `--effort` and `--permission-mode`, with the prompt as the last argument. For copilot-cli, it's `--reasoning-effort`, `--allow-all-tools`/`--allow-all` and `-i <prompt>`. The levels are read from each CLI's real `--help` when the task is done, not guessed. `ws launch argv --agent A [--effort E] [--permissions P] --prompt-kind K -w id [--task T] --json` prints `{argv, effortLevels, permissionChoices}`. The prompt comes from `LAUNCH_PROMPTS`, or is passed as edited text with `--prompt`. `ws launch agents --json` lists the presets for a picker. Rejected: flags written in Kotlin or TypeScript (T1), and a free-text flags box as the only option.

### D-LAYOUT: master-detail Workstreams tab
`RegistryView.kt` is replaced by `WorkstreamsView.kt`:
- a `JBList` of rows on the left, through `ColoredListCellRenderer`;
- on the right, a `JBTabbedPane` with **Tasks** (a `TableView` above a task pane), **Graph** (a `Tree` built from `blockedBy`/`unblocks`) and **Overview**;
- splitter proportions remembered, the selection kept across reloads by id, double-click on a task opening the tasks file at its id.

The `logic/` ports gain plain-data builders for rows, columns, the task pane's sections and the overview's sections, so JUnit covers them. Review, Health and Budget stay as tabs.

### D-MENUS: toolbar, menus, empty states, status bar
The toolbar has grouped popups, each also under **Tools ▸ Workstreams** and on the list's and table's context menus, shown only where the snapshot offers them:
- **Run** (Run…, Run This Task…, Coordinate…, Close…, Abandon…);
- **Workstream** (Pause, Resume, Sync);
- **Task** (Unclaim);
- **Open** (Plan, Progress, Decisions, Handoff, tasks file).

Empty states: "`ws` not found → Configure…" and "No workstreams → how to plan one". The status bar shows `● <ws> · <claimed task> · <age>` when a task is claimed, and the wave line otherwise.

### D-DIALOG: the launch dialog
Opened by every Run-group action. It shows:
- the checks from `ws launch check` (a blocking one disables OK);
- a task pin (Run This Task…);
- the target: Terminal, then each chat target whose plugin is enabled;
- for Terminal only, the agent preset with its effort and permissions and the resulting argv from `ws launch argv`;
- the prompt, editable.

The last target, agent, effort and permissions are kept in `WsSettings`. `Launch.kt`'s `Launcher.launch` gains a `target` parameter, and the clipboard stays the fallback.

### D-CHAT: Copilot Chat and Air targets
In `ChatTargets.kt`, registered through optional `<depends>` config files like `workstreams-terminal.xml`:
- **Copilot Chat** starts a new agent-mode session with the prompt, through its public chat service, reached by reflection.
- **Air** opens its new-session prompt with the text in it. The person picks the agent there and sends it.

Both load classes as T5 says. Tests use fake classes under the same names in `src/test`, as that plugin's tests do, so no real plugin is needed.

## 4. Tasks

| id | title | blocked by | notes |
|---|---|---|---|
| JX-01 | Record the comparison and the rules it changes (decision 0019) | – | docs only |
| JX-02 | Snapshot facts: unblocks, waitingOn, scope, baseline | – | Python |
| JX-03 | `ws launch check`: pre-flight checks | JX-02 | Python, shares cli.py |
| JX-04 | `ws launch argv` and agent presets, plus the `run-task` prompt | JX-03 | Python, shares cli.py |
| JX-05 | Master-detail Workstreams tab: list, Tasks table, task pane | JX-02 | Kotlin |
| JX-06 | Graph and Overview tabs | JX-05 | shares WorkstreamsView.kt |
| JX-07 | Toolbar groups, Tools menu, empty states, status bar | JX-06 | shares WorkstreamsView.kt |
| JX-08 | Launch dialog with pre-flight, presets and targets | JX-04, JX-07 | |
| JX-09 | Copilot Chat and Air launch targets | JX-08 | |
| JX-10 | Prove it in both IDEs by hand | JX-09 | foreground, user |

## 5. End-to-end verification

JX-10, with the owner at the IDEs. They build the zip (`make jetbrains-zip`) and install it in IntelliJ IDEA 2026.3 and Android Studio 2026.2. The sample project comes from a wheel, as M10 built one: two workstreams, a stale claim, a branch. Then:
- the list, Tasks, Graph and Overview tabs draw, and a dependency link jumps;
- a launch with a blocking check can't be confirmed;
- Run starts Claude Code in a Terminal tab with the chosen effort and permission flags visible in the argv;
- Copilot Chat opens a new agent session holding the prompt;
- Air opens its prompt holding the prompt;
- a stale Pause is refused.

`make test`, `make test-jetbrains` and `make verify-jetbrains` pass, and 0019 records what was seen.
