# 0019: The IDE UIs take their shape from the other workstream plugin

Decided with the owner on 2026-11-10 (workstream `jetbrains_ux`, D001), before the redesign started. It changes how the JetBrains plugin ([0018](0018-jetbrains-plugin.md)) and, after it, the VS Code extension ([0017](0017-vscode-extension.md)) lay out their views and start agents. Native UI ([0016](0016-native-ide-ui.md)) and "the plugin decides nothing" stay.

**Why.** The owner compared our tool window with another workstream plugin, and found its UI better to work in. They asked for ours to favour it.

## The boundary: ideas only

the other workstream plugin is a work project. We take ideas from using it, never its code, its strings or its docs. Every adopted idea below is described in our own words and built from our own CLI. Nothing in this repo is copied from it, no file of its repo is read while building, and none of its commands are ported: it drives its registry through its own scripts, and our plugin still gets every fact from the `ws` CLI and makes every write through `ws act`.

## What it does better

| Area | Our plugin (0018) | What the other workstream plugin shows works better |
|---|---|---|
| Layout | One tree with everything nested, detail in tooltips | A list of workstreams on one side, the selected one's detail on the other |
| A task | A tree node and a hover | A pane of its own: state, files, acceptance, launch |
| The whole workstream | Waves as tree levels | A dependency graph, and an overview page of progress |
| Actions | A flat list on the node's popup | Menus grouped by what the action is for |
| Starting an agent | Run copies a fixed prompt into a Terminal tab | A launch dialog that checks the ground first, then starts |
| Which agent, where | One agent command setting, Terminal only | Saved presets, and a choice of where the chat opens |

## What we adopt

1. **Master-detail.** A list of workstreams, and for the selected one a detail with three tabs: Tasks, Graph and Overview. Review, Health and Budget stay as their own tool window tabs, because they span workstreams.
2. **A task pane.** Selecting a task shows its state, claim, files, acceptance and launch in one pane, from the snapshot's row for it.
3. **Graph and Overview.** Graph draws the task dependencies the snapshot already lists; Overview sums the workstream's progress, health and budget. Neither computes a fact the CLI doesn't give.
4. **Grouped menus.** Actions are grouped by purpose (state changes, launching, opening files) rather than listed flat.
5. **A launch dialog with pre-flight, presets and chat targets.** Before starting, the dialog runs pre-flight checks, lets the user pin a task and edit the prompt, and offers agent presets (agent, effort, permissions). The preset becomes flags that `ws` maps from the adapter TOMLs, so no flag is spelt in the plugin. The prompt can go to three targets: a Terminal tab, Copilot Chat, or Air.

## What we don't adopt

- **Its registry commands.** Porting its raw task scripts would give the plugin a second writer. A write this redesign needs that `ws act` lacks is added to `ws act` first, in its own task.
- **Any write outside `ws act`**, including editing registry or plan files from the UI.
- **Its look.** Colours, icons, wording and labels are ours, drawn with the platform's own components.
- **A web panel.** 0016 stands.

## The rules this changes

**No internal API, with one exception: Air.** 0018 requires `make verify-jetbrains` to say Compatible with no internal-API use. Copilot Chat is reached through classes the plugin registers publicly, but Air opens a new session only through non-public classes. The owner accepted reaching those by reflection, guarded: Copilot and Air are optional, their classes live in content modules with their own classloaders, so each is loaded through the classloader of an action that plugin registers (found by id with `ActionManager`), after checking the plugin is enabled. Any reflective failure falls back to copying the prompt to the clipboard, with a line saying why. `verifyPlugin` cannot see reflection, so it still says Compatible; this record, not that result, is what allows it. Nothing else may use internal API, and the Air target is the first thing to drop if it breaks.

**Agent names stay out of code, with one exception: `ChatTargets.kt`.** `tests/test_no_project_literals.py` bans agent names in `src/workstream/`, and `tests/test_jetbrains_files.py` bans them in `ui/jetbrains/src`. Agent flags for presets go in a new `[launch]` table in each `src/workstream/assets/adapters/*.toml`, which the core scan already skips. A chat target, though, has to name the other plugin's action ids and classes, so those names live in one file, `ChatTargets.kt`, which the JetBrains scan allows by name once the chat targets land. Every other file stays clean, and the test checks that the exception covers that file only.

## What was built

Ten tasks (JX-01 to JX-10); the workstream's `DECISIONS.md` holds the smaller calls (D002 to D037).

- **The CLI** gives the facts the views need: `ws snapshot -w` now carries each task's `unblocks` and `waitingOn`, the queue's `scope` and its `baseline`. Three new commands feed the launch dialog: `ws launch check` (pre-flight), `ws launch agents` (presets) and `ws launch argv` (the command line for a preset, from the adapter TOML's `[launch]` table). `run-task` is a launch kind of its own, used when a task is pinned.
- **The Workstreams tab** replaces the Registry tree: the list, then Tasks (table and task pane), Graph and Overview.
- **Menus** sit in four groups, shared by the toolbar, context menus and Tools | Workstreams.
- **The launch dialog** opens before every launch. The task pin is a picker in Run…'s dialog rather than a separate Run This Task… action (D023, D027).
- **The chat targets** are always registered in `plugin.xml` and offered only while their plugin is installed, enabled and its classes load, rather than registered through optional `<depends>` files (D033). Their tests use fakes under their own names, not the real plugins' (D034).
- **The Terminal launch runs inside the person's login shell** (D037). The hand check found that a Terminal tab running the agent's argv directly doesn't see the PATH that `~/.zshrc` sets, so a bare `claude` wasn't found from an IDE started from the Dock. The tab now runs `$SHELL -l -i -c 'exec "$@"' ws-launch <argv>`. The prompt is still an argument that no shell parses. Fish and other shells whose `-c` doesn't take `"$@"` run the argv as it is.
- **Blocking checks are shown first** (D037). The hand check found the dialog's checks were plain text scrolled past the blocking lines, with no reason by the disabled OK. They are now one row each with a state icon, blocking ones first, and the line by the buttons names what blocks.

## What was seen (JX-10)

The owner installed the plugin in IntelliJ IDEA 2026.3 and Android Studio 2026.2.2, both from the same build (`0.1.0.20261111152831`, published to a local plugin repository so each fix arrived as an update). The sample came from a wheel: `ws` 0.1.0 installed into a clean venv built `alpha` (S-1 claimed and backdated, S-2 claimed with work on `task/s-2`, S-3 blocked by S-1) and `beta`, then main moved. The plugin's ws command pointed at that venv's `ws`.

| Check | IntelliJ IDEA 2026.3 | Android Studio 2026.2.2 |
|---|---|---|
| List, Tasks, Graph and Overview draw; a dependency link jumps | Yes: "2 claimed" on alpha, a Claim section on S-1 and S-2, S-3 under S-1 in the Graph, both claims under Open claims | Yes |
| A launch with a blocking check can't be confirmed | Yes: alpha blocked by validate, wave and claim, listed first, OK off | Yes |
| Run starts Claude Code in a Terminal tab with the preset's flags | Yes: `/bin/zsh -l -i -c exec "$@" ws-launch claude --effort medium --permission-mode acceptEdits …` (IDE log, 15:55) | Yes: the same wrap (IDE log, 16:03) |
| Copilot Chat opens a new agent session holding the prompt | Yes | Yes |
| Air opens its prompt holding the prompt | Yes | Yes, once Android Studio's Air plugin shipped `intellij.air.frontend.prompt.ui`; before that the target was left out |
| A stale Pause is refused | Yes: `d443747` committed from a shell while the box was open; OK was refused and HEAD stayed `d443747` | Yes: `22cf098` the same way; HEAD stayed `22cf098` |

Two setup slips were caught on the way and are worth knowing. The old M10 sample and the old `ws` drew S-1 as unclaimed and a flat Graph, because that `ws` emits no `unblocks`. The `ws` path had been pasted into the Agent command setting. The README now says the Agent command is not the `ws` command.

## What was built in VS Code (vscode_ux)

Seven tasks (VX-01 to VX-07); the workstream's `DECISIONS.md` holds the smaller calls. The extension stays on native views (0016); there are no webviews.

- **Five linked views** replace the Registry tree: Workstreams, Tasks, Task, Graph and Overview, ahead of Review, Health and Budget. Picking a workstream fills the other four; a task row, a graph node or a dependency link picks the task. The selection survives a reload.
- **Menus** sit in the same four groups as JetBrains (Run, Workstream, Task, Open), as separator groups rather than submenus. The linked views' title bars act on the selection.
- **The launch flow** is a run of quick picks: checks (shown only when one warns; a blocking one ends the flow with its message), agent preset, effort, permissions, target, then the prompt to edit. A step with one choice is skipped, and the last choice is listed first.
- **The chat targets** are Copilot Chat (a new agent-mode chat) and the Claude Code extension (its panel, through its URI handler). Each is offered only while its extension is enabled; the clipboard stays the last fallback.

## What was seen (VX-07)

The owner installed the extension from a `.vsix` (built from `task/vx-07`) into VS Code 1.145.2 on macOS, with Copilot Chat and Claude Code (`anthropic.claude-code`) installed. The sample came from a wheel: `ws` 0.1.0 installed into a clean venv built `alpha` (S-1 claimed and backdated three days, S-2 claimed with work on `task/s-2`, S-3 blocked by S-1, its plan files left as templates so it fails validate) and `beta` (valid, unclaimed), then main moved. `workstreams.wsCommand` pointed at that venv's `ws`.

| Check | VS Code 1.145.2 |
|---|---|
| The five views are linked | Yes: alpha selected filled Tasks (`Stuck: 3 open, none act…`, Phase 1 0/3), Graph (S-3 under S-1), Overview (Documents, Registry `0/3 done · 2 claimed`, Open claims `S-1 · sample · 3d ago` and `S-2 · sample · 1h ago`, Baseline `None recorded`) |
| A launch with a blocking check can't go on | Yes: Run on alpha stopped at its checks |
| Run starts a terminal with the preset's flags | Yes |
| Copilot Chat opens an agent-mode chat holding the prompt | Yes |
| The Claude Code panel opens holding the prompt | Yes |
| A stale Pause is refused | Yes: with the confirm open, `156811b` changed alpha's queue from a shell; OK gave the stale-view refusal and HEAD stayed `156811b`. A commit that touches neither the registry nor the queue (`03f87eb`, a README line) does not make the view stale, by design: `ws act` compares only those two files' hashes |

The owner raised three things to improve, left for later work:

- The panel is crowded with eight views side by side; Review and Health could move to tabs of their own.
- A failed check during a launch is shown as a tooltip that is hard to read.
- The launch flow, the Terminal path in particular, takes several steps; it could be shorter without losing any choice.

`make vsix` had failed since 0017's hand check because the README linked to `../../docs/…`, which `vsce` refuses without a repository URL; the link is now a plain path.

## What was built in VS Code (vscode_followups)

Six tasks (VF-01 to VF-06) took up the three points above. The workstream's `DECISIONS.md` holds the smaller calls.

- **Four panel tabs:** Workstreams holds the five linked views; Review, Health and Budget each have a tab of their own, matching the JetBrains tool window's tabs.
- **A blocked launch lists its checks** in a read-only quick pick, blocking ones first, instead of the old toast. The toast now carries only the one-line title. When `validate` blocks, a read-only editor tab holds the whole `ws validate -w <id>` output (VF-06, added at the owner's request during the hand check: the list's row has room for only the first error).
- **A shorter Terminal path:** a repeat-last row at the top of the target pick, and one combined agent × effort × permissions pick. No choice was removed.
- **Menus and prompts come from the snapshot's per-row `launches`** (vscode_ux D020), so the extension offers only the launches the CLI does.

## What was seen (VF-05)

The owner installed the extension from a `.vsix` (built from `task/vf-05` with VF-01 to VF-06 merged) into VS Code 1.146.0 on macOS. The sample came from a wheel, built the way VX-07's was: `ws` 0.1.0 installed into a clean venv built `alpha` (S-1 claimed and backdated three days, S-2 claimed with work on `task/s-2`, S-3 blocked by S-1, its plan files left as templates so it fails validate) and `beta` (valid, unclaimed), then main moved. `workstreams.wsCommand` pointed at that venv's `ws`.

| Check | VS Code 1.146.0 |
|---|---|
| Four panel tabs | Yes: Review, Health, Budget and Workstreams beside Terminal; Workstreams holds Workstreams, Tasks, Task, Graph and Overview |
| A blocked Run lists its checks | Yes: "Run alpha is blocked by 3 checks", with `validate`, `wave` and `claim` failing first, then `dirty` and `baseline` passing |
| Validate's errors in a tab | Yes, on the second build. On the first build, the `validate` row showed only the first error and "(and 8 more…)"; the owner asked for a tab, which became VF-06 |
| A repeated Terminal launch takes two picks | Yes |
| A fresh Terminal launch uses the combined pick | Yes |
| Abandon carries its reason | Yes |

## What was built in the Claude Code pane (pane_ux)

Five tasks (PX-01 to PX-05); the workstream's `DECISIONS.md` holds the smaller calls.

- **Prompts come from the snapshot's per-row `launches`.** The pane's own copy, `promptText`, is gone, and `tests/test_mod_files.py` fails if any file under `ui/mod` holds a launch prompt's text.
- **Detail has Tasks, Graph and Overview** sub-screens. Graph draws each task under the tasks it waits on, from `blockedBy` and `unblocks`. Overview shows the documents (as feed buttons), claims, scope, verify commands and baseline.
- **A task opens its own page,** with depends-on and unblocks as buttons that jump. It replaces the inline expansion.
- **Every launch runs `ws launch check` first** and shows each check. A blocking failure fills nothing. The surface's Button has no disabled state, so a held launch is drawn as dimmed text naming the first blocking check, with **Check again** (D010). **Run This Task** on a task page fills run-task's prompt, which comes from the last argument of `ws launch argv --agent claude-code`, as the JetBrains plugin reads it (D011).

## What was seen (PX-05)

The owner ran `/reload-plugins` and `/workstreams` in the Claude Code desktop app. The plugin was read from `ui/mod` on `main` with PX-01 to PX-04 merged. pane_ux itself was the sample: PX-05 was claimed, so `ws launch check --kind run` blocked on `claim`.

| Check | Claude Code desktop app |
|---|---|
| Tasks, Graph and Overview draw | Yes, but the Graph's indentation is lost: PX-02 to PX-05 all sit one level under PX-01 instead of each one further in. The leading spaces in a line's text are collapsed on the desktop surface. `claude plugin test` keeps them, which is why the tests passed. |
| A task page's dependency buttons jump | Yes |
| A blocked Run shows its message and fills nothing | Yes |
| Run This Task fills the box and sends nothing | Yes |

## Rules for changing it

- A new idea from the other workstream plugin comes in as a description of behaviour, written here, never as its code or text.
- A new chat target goes in `ChatTargets.kt` and falls back to the clipboard; a new agent flag goes in the adapter TOML.
- A second exception to the no-internal-API rule needs its own record.
