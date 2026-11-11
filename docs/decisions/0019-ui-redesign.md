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

## Rules for changing it

- A new idea from the other workstream plugin comes in as a description of behaviour, written here, never as its code or text.
- A new chat target goes in `ChatTargets.kt` and falls back to the clipboard; a new agent flag goes in the adapter TOML.
- A second exception to the no-internal-API rule needs its own record.
