# Workstream protocol

Version 1. `ws protocol <section>` prints one section, so nobody loads the rest. A rule the CLI can enforce isn't here: the CLI refuses instead.

## worker

- Do this task only, then stop. Other work you find goes under Gotchas.
- Ending your turn ends you: nobody resumes you, and whatever you left running dies with you. Don't end it until you have reported.
- Search before you read, then read only the lines you need. Whatever you read stays in your context for every later call.
- Create and change files with your edit tools, and give the shell one command per call: a background worker can't ask permission for anything else. A denied call isn't a block until you've tried it that way.
- Write code, docs and your own evidence file. Every other file in a workstream folder, and the registry, belongs to the coordinator.
- Check each acceptance item for real and quote what you saw. "Done" isn't proof.
- Findings in the baseline aren't yours: don't fix them, and don't add to them.
- A reversible call goes in your evidence as `### P1: the call`, with the reason and what you rejected. Never invent a `D` number. Mark one that someone must still settle `**Open.**`.
- Don't reopen a recorded decision without new evidence.
- Stop rather than guess when `ws verify` can't pass, the work needs something out of scope, it would contradict a decision, the plan missed something that changes the design, the task's premise is wrong, or a `verify` command can't prove what acceptance claims. Write `- **Status:** blocked (the reason)`, commit that, and report.
- Don't merge, and don't switch to the integration branch.

## files

| File | What it is | Who writes it |
|---|---|---|
| `PLAN.md` | The design. Immutable once approved | Planner, once |
| `tasks_list.json` | The queue | The CLI only |
| `baseline.json` | What commands reported before work began | `ws baseline record` |
| `DECISIONS.md` | Settled calls. Not reopened without new evidence | `ws settle` for workers' proposals; `ws decide` for anyone else's |
| `PROGRESS.md` | History, newest first | `ws settle` |
| `session_handoff.md` | Where things stand now, overwritten each time | `ws settle`, `ws handoff` |
| `evidence/<TASK>.md` | What one task did and proved | That task's worker, on its branch |

Each fact has one home; elsewhere, cite it. Before writing a sentence, ask whether the code, the diff or a reference already says it.

## plan-shape

An approved plan is one Markdown file with these sections, then the blocks below. `ws seed --from-plan` splits it, so nothing is written twice.

1. **Context:** why, the outcome, and what is out of scope.
2. **Traps:** `### T1: <one line>`, with `file:line`, what makes the obvious change wrong, and what to do instead.
3. **Design:** `### D-<NAME>: <one line>`, naming files, functions and rejected alternatives, and how it is tested.
4. **Tasks:** a table of id, title and blocked-by, noting which share files or run in the foreground.
5. **End-to-end verification:** how the last task proves the outcome for real.

Tasks cite traps and designs in `findings`, and `ws brief` gives each worker only those sections.

````
```json ws-tasks
{"scope": {"inScope": [], "outOfScope": [], "rule": "one binding sentence"}, "tasks": [...]}
```

```text ws-decisions
What the user chose or ruled out.
```
````

## task-schema

Required: `id` (`<PREFIX>-01`), `phase`, `priority` (10, 20, 30; the real order), `title`.

| Field | Holds |
|---|---|
| `kind` | What it produces; `[adequacy]` in the config says what that kind must verify with |
| `summary` | What the task requires |
| `findings` | Plan sections to read: `T1`, `D-API` |
| `files` | Expected paths, folders or globs. Touching anything not here or in `docs` warns |
| `docs` | Paths that bear on the task; each must exist, and may be changed |
| `acceptance` | Observable facts: a named test, a command and its output. `{"text": "...", "kind": "manual"}` for a person's check. `{"text": "...", "expect": "72/5/16"}` fails `ws verify` unless that literal is in the logs of its commands. A name filter that matches nothing can still exit 0, so there `expect` should name the line the runner prints for that test passing: a bare test name can match an echoed command. `ws add` and `ws update` with `--acceptance` can't set `expect`; `ws seed` can add such a task to an existing queue |
| `verify` | Keys from `[commands]`, or a raw command. Must run what the task produces |
| `blockedBy` | Task ids. Tasks sharing files must be chained |
| `needsUserDecision` | True only for what planning couldn't settle |
| `mode` | `background`, or `foreground` for a task needing a session to itself. Both get a worktree |
| `requires` | The config's values, such as `browser` or `user`; some force foreground |
| `releaseImpact` | `none`, `patch`, `minor` or `major`, required on a `full` workstream |
| `notes` | Hints. Nothing branches on free text |

## stop

Stop, say exactly what fired and what is left, and ask. Never guess past one. Files hold all the state, so running again resumes.

1. `ws validate` or `ws reconcile` reports a problem you didn't cause. Report it; don't repair past it.
2. A task comes back blocked: pass on the reason word for word, as a decision the user owes.
3. A worker asks a question or stalls. Pass it on unanswered.
4. `ws settle` doesn't land a task: failed gates, a conflict, or checks failing after the merge. Don't resolve conflicts by hand.
5. `ws wave` exits 3: open tasks remain and none can start.
6. A round lands nothing, whatever the workers said.
7. A workstream it depends on isn't done, or the queue closes with deferred tasks.
8. A release would be `major`, or its checks go red.
9. An open decision has tasks waiting on it: it goes to the user before those tasks are claimed.
10. `ws settle` says a brief is over budget. The merge stands; what to do about the brief is the user's call.
