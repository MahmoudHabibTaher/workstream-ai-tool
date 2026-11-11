# Decisions: JetBrains UX redesign

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-10, user): scope approved

The owner (2026-11-10) finds the other workstream plugin's UI better and asked for our UIs to favour it. It is another workstream plugin: ideas only, no code or text.
Master-detail: a list plus Tasks/Graph/Overview detail; Review, Health and Budget stay as their own tabs.
Launch targets: Terminal, Copilot Chat and Air. Air is reached by guarded reflection into non-public classes, falling back to the clipboard; an exception to 0018's no-internal-API rule.
Launch options: agent presets (agent, effort, permissions) that ws maps to flags from the adapter TOMLs, plus pre-flight checks, a task pin and an editable prompt.
Ruled out: porting the other workstream plugin's raw tasks.py commands; any write other than ws act. **Closed.**

## D002 (2026-11-11, JX-02): baseline is `{keys: [...], errors: [...]}`, one entry per key with `exit` and a `findings` count as its result

The plan names "key, result, recorded-at". A recorded key holds an exit code and a list of known findings, so the result is given as those two facts (`exit`, `findings` as a count), not a derived word like "clean", which would be a judgement a UI could also make differently. Each entry also carries `source` (`project` from `ws init`, or `workstream` from `ws baseline record`), `parser`, `command`, and its record's `recordedAt` and `commit`: the two records are stamped at different times, so recorded-at is per key, and the merge follows `baseline.load_for` (the workstream's key wins). A `baseline.json` that can't be read is named in `errors` and the other record still draws, so one broken file can't break `ws snapshot`. A key no record holds is simply absent (no "not recorded" entries); pre-flight can compare against `baseline.keys_to_record`.
Rejected: a single `result` string field; the top-level `recordedAt` of the merged record only (wrong for inherited keys); raising on a broken baseline file. **Closed.**

## D003 (2026-11-11, JX-02): unblocks are direct dependents, waitingOn is unfinished direct blockers

`unblocks` matches what `ws show` prints (tasks naming this one in `blockedBy`, in priority order, whatever their status), not `graph.dependents`' transitive closure. `waitingOn` is `blockedBy` minus done ids, the same test `graph.actionable` and `graph.why_not_actionable` use, so an id naming no task counts as waiting. Both come from `graph.blocked_by_graph`, so ill-typed `blockedBy` gives empty lists. `graph.py` itself is unchanged (it isn't in the task's file list); the reverse edges are built in `snapshot.task_graph_facts`.
Rejected: transitive unblocks; adding a new function to graph.py. **Closed.**

## D004 (2026-11-11, JX-02): scope is the queue's scope with only well-typed fields, or null

`scope` is always present under `-w`: null when the queue has none (or it isn't an object), else `inScope`/`outOfScope`/`rule` as present and well-typed. The schema closes it. Neither `scope` nor `baseline` appears without `-w`.
Rejected: omitting the key when absent (a UI would have to tell "missing" from "old CLI"). **Closed.**

## D005 (2026-11-11, JX-03): `validate` checks this workstream only, through `registry.validate_entry`

The same call `ws validate -w <id>` makes. Another workstream's broken queue doesn't stop a launch on this one; the message gives the first error and points to `ws validate -w <id>` for the rest.
Rejected: `registry.validate_all`, which would let any workstream's error block every launch. **Closed.**

## D006 (2026-11-11, JX-03): the command exits 0 whenever the checks ran; the verdict is in the JSON

`ws launch check` exits 0 even when a blocking check fails, so a UI reads each check's `ok`/`blocking` rather than treating a nonzero exit as "the CLI failed". Exit 1 is kept for what the caller got wrong (unknown workstream, `run-task` without `--task`, `--task` with another kind, a task the queue doesn't hold) and for argparse errors (an unknown `--kind`). The text form ends with `blocked` or `ready to launch`. `launch.blocked(result)` gives the verdict to Python callers.
Rejected: exit 1 on a blocking failure (a UI would have to tell it apart from a real error). **Closed.**

## D007 (2026-11-11, JX-03): only the checks that apply to the kind are listed; `skills` only with `--agent`

`run` gets validate, wave, claim, dirty, baseline; `run-task` gets the same minus wave; coordinate/close/abandon get validate, dirty, baseline. `skills` is added when `--agent` is given. Every check carries `blocking` even when it passes, so a UI can show how each would count.
Rejected: listing every check for every kind with a "not applicable" state (a fourth state the schema and UIs would have to draw). **Closed.**

## D008 (2026-11-11, JX-03): `run-task` is accepted as a kind before its prompt exists

`launch.KINDS` is `snapshot.LAUNCH_PROMPTS`' keys plus `run-task`, de-duplicated, so JX-04 adding the `run-task` prompt changes nothing here. For `run-task` the claim check names the pinned task when it's the one already claimed ("AL-01 is already claimed"); either way it's a warning, as D-PREFLIGHT says.
Rejected: waiting for JX-04's prompt, or a second list of kinds. **Closed.**

## D009 (2026-11-11, JX-03): a check that can't read its input fails, it doesn't raise

An unreadable queue fails wave/claim/baseline with `cannot read the queue: ...` (keeping each check's own blocking), a broken `baseline.json` or adapters manifest fails its check with the read error, and a git failure fails `dirty` (blocking). The other checks still run, as D002 does for the snapshot.
Rejected: raising, which would hide every other check behind one broken file. **Closed.**

## D010 (2026-11-11, JX-04): a registry row doesn't offer run-task; `snapshot.ROW_LAUNCHES` lists the four a row offers

`row_launches` used to iterate over all of `LAUNCH_PROMPTS`. With `run-task` in the table, every row would have offered a run-task launch with no task to fill `{task}`. Rows now iterate over `ROW_LAUNCHES = ("run", "coordinate", "close", "abandon")`. The schema's kind enum is still every `LAUNCH_PROMPTS` key, as acceptance 2 requires, so the enum allows run-task while no row emits it. Because of this, `tests/test_snapshot.py`'s check against logic.js's `promptText` (`set(web) == set(LAUNCH_PROMPTS)`) now compares against `ROW_LAUNCHES`. That file wasn't on the expected list. I changed one line in it, because otherwise `make test` fails.
Rejected: having rows offer run-task with an unfilled `{task}`, or adding run-task to logic.js, which is a web-UI copy outside this task. **Closed.**

## D011 (2026-11-11, JX-04): no effort or permissions given adds no flag; the choices are only the flagged ones

When `--effort` or `--permissions` is left out, nothing is added, and the agent's own default or settings decide. So no "default" entry appears in `permissionChoices`. claude-code's six choices are exactly `--permission-mode`'s values. copilot-cli's are `allow-all-tools` and `allow-all`, as D-PRESETS names them. `--yolo` (the same as `--allow-all`) and copilot's `--mode plan|autopilot` are left out.
Rejected: a synthetic `default` choice, which would be a fourth name a UI has to explain. **Closed.**

## D012 (2026-11-11, JX-04): the run-task prompt text

`"Use the ws-run skill to run only task {task} of workstream {ws}."` `ws-run` is the skill that claims and starts workers, so a pinned task goes through it.
Rejected: a new skill name, because skills are outside this task. **Closed.**

## D013 (2026-11-11, JX-04): the argv JSON shape and the agents list

`ws launch argv --json` prints exactly `{argv, effortLevels, permissionChoices}`, with `permissionChoices` as a list of names (the flags are already in `argv`). Without `--json` it prints `shlex.join(argv)`. `ws launch agents --json` prints `{agents: [{agent, label, command, effortLevels, permissionChoices}]}`. `--prompt-kind` accepts the keys of `LAUNCH_PROMPTS`. `--prompt` replaces the text after the workstream, kind and task have been checked, so an edited prompt still names a real target. Unknown effort or permissions, an unknown agent, a missing or extra `--task`, or a task the queue doesn't hold exits 1, as D006 does for `check`.
Rejected: `permissionChoices` as {choice: flags} objects (a UI only needs the names, since `ws launch argv` builds the flags), and `--prompt` skipping the checks. **Closed.**

## D014 (2026-11-11, JX-05): the tasks file is the `watch` entry after the registry that `paths` doesn't name

`ws snapshot -w` gives no tasks-file path, but its `watch` is the registry, then `project.tasks_path(ws)`, then handoff and progress (`snapshot.watch_paths`). `Snapshots.tasksFile` takes the first entry after the registry that isn't one of `paths`' documents, so double-click opens the file the CLI named rather than one the plugin guesses. Adding a `paths.tasks` to the snapshot would be cleaner but is a CLI and schema change outside this task (see Gotchas).
Rejected: building `<folder>/tasks_list.json` in the plugin (a fact the CLI owns); a positional `watch[1]`. **Closed.**

## D015 (2026-11-11, JX-05): Snapshots.kt reads the new task fields

`unblocks`, `waitingOn`, `files`, `notes`, `claimedBy` and the row's `progress["in-progress"]` (the list's claim count) are read in `Snapshots.kt`, which isn't in the task's file list but is the only place snapshot JSON is parsed; `Task` and `Progress` in Format.kt gain the fields. `badgesOf` now takes `waitingOn` from the snapshot instead of working it out from `blockedBy` (plan T3), so its `tasks` parameter is gone.
Rejected: parsing in the view (two parsers). **Closed.**

## D016 (2026-11-11, JX-05): the workstream's claim is a count of its claimed tasks

The list row shows `N claimed` from the registry row's `progress["in-progress"]`, since the top-level snapshot has no per-task claim for rows. A row reads `alpha  0/2 · active · 1 claimed · 9 errors`; the claimer and age appear in the task pane's Claim section (`claimedBy · 3h ago`, in-progress tasks only).
Rejected: loading every workstream's `ws snapshot -w` to name claimers in the list (one CLI run per row per reload). **Closed.**

## D017 (2026-11-11, JX-05): pane text is drawn by components that never read markup, inside a UI DSL panel

The pane is a `panel { }` whose rows hold a read-only `JBTextArea` per line, a `SimpleColoredComponent` per heading and an `ActionLink(Text.html(...))` per link, so neither the DSL's `label()` (a JLabel, which reads `<html>`) nor JEditorPane is used. The test file checks this shape.
Rejected: `label(Text.html(...))` for every line (works, but wraps poorly and turns every line into HTML). **Closed.**

## D018 (2026-11-11, JX-05): documents move to links in the detail header; Graph and Overview are left for JX-06

The tree's Documents node is gone with RegistryView.kt; the selected workstream's documents (from `paths`) are links under its name and wave line, so the plan stays one click away. The detail's `JBTabbedPane` has only Tasks for now. The tree-only builders (`PhaseNode`, `WaveNode`, `DocumentsNode`, `DocumentNode`, `MessageNode`, `workstreamChildren`, `phaseChildren`, `documentChildren`) are removed; `Shown.collapsible` stays because Review and Health use it. The tool window's first tab is now "Workstreams" (was "Registry").
Rejected: keeping RegistryView.kt alongside (two views of the same data). **Closed.**

## D019 (2026-11-11, JX-05): a writes target is the task only when the table was used last

`selected()` is the selected task when the table had focus last (or a jump link was clicked), else the selected list row; both popup menus use `POPUP_GROUP`. Each node keeps the revisions it was drawn with.
Rejected: always preferring a selected task (Pause from the list would then need deselecting the table first). **Closed.**

## D020 (2026-11-11, JX-06): the Graph expands a task once; later appearances are leaves marked "shown above"

`graph()` in logic/Registry.kt roots the tree at the tasks whose `blockedBy` names none of the table's tasks. Children are the `unblocks` ids, in table order. A task reached a second time (a diamond, or a cycle) is drawn as a leaf with `status · shown above`. A task that no root reaches (a cycle) becomes an extra root. Only snapshot fields are used (plan T3). Selecting a task in the table selects where that task is expanded in the Graph.
Rejected: repeating whole subtrees under every parent (the tree can grow without bound, and a cycle never ends). **Closed.**

## D021 (2026-11-11, JX-06): Overview content and sources

The sections, in order, are Documents (links from `paths`), Registry (the list's row: title, summary, status · tier, done/total · claimed, depends on, dates, base commit, notes), Open claims (the in-progress tasks, each a jump link `id · claimedBy · age`), Scope / In scope / Out of scope (the snapshot's `scope`), Verify (the distinct `verifyCommands` across the tasks) and Baseline (one line per key, then `Error: …` lines). Open claims and Baseline always show and say `None` / `None recorded` when empty. The other sections are left out when they have nothing to show. The Overview reuses the `TaskPane` class (D017's shape), so its text goes through JBTextArea and `Text.html` links.
Rejected: a workstream-level verify list (the snapshot has none, so the plugin would be guessing). **Closed.**

## D022 (2026-11-11, JX-06): files touched outside the task's list

- `Snapshots.kt` parses `scope`, `baseline` and the registry row's `tier/created/startedAt/completedAt/baseCommit/notes`. It is the only place snapshot JSON is parsed (same reason as D015).
- `logic/Format.kt` adds those six fields to `Row`, all optional.
- `tests/test_jetbrains_files.py` updates its shape check: the `append(` list gains the GraphRenderer's three calls, the ActionLink arguments become `Text.html(item.label)`, and it asserts `GraphRenderer : ColoredTreeCellRenderer()` and the Overview pane. T6 asks for this test to be updated for new views, and no new view file was added.
- `PaneItem.TaskLink` and `PaneItem.FileLink` gain a `label` that defaults to the id or path, so the Overview's claims and documents can carry their own text.
Rejected: a separate parser in the view. **Closed.**
