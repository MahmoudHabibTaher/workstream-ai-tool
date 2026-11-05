# MBZ feedback: plan

## 1. Context

The agent that ran subsonic's MBZ-08 to MBZ-10 reported five rough edges in `ws`. Each was checked against the code and the run's records. Four hold, the fifth is partly wrong because `expect` already exists, and the check found two more: a user decision naming the task (D018) was trimmed out of MBZ-10's brief, and a superseded number stays in the brief's plan section because a plan can't be edited.

**Outcome:** text left for a file a worker can't edit is tracked until it is applied. A decision that changes a task reaches that task's brief and prompts for the correction. Acceptance items that can't be proven before settling get flagged when written. The settle warning says what it means. A result that differs from acceptance is always proposed as a decision.

**Out of scope:** comparing results against worded acceptance automatically; following all earlier tasks for gotchas in a brief; changing the gotcha cap; showing the new evidence section in the web review; Copilot evals, which use paid work-account credits; any change in subsonic-server or the Kotlin harness; making a plan editable.

## 2. Traps

### T1: `ws` on the PATH is the main checkout, not your branch
The install is editable, so a bare `ws` in a worktree runs main's code and proves nothing about your branch. Prove a change with `make test TESTS=tests.test_x`, which runs under `PYTHONPATH=src` from your worktree.

### T2: the `.claude/` skills are generated, and a background worker can't edit them
`ws adapt claude-code` writes them from `src/workstream/assets/skills/`. Skill tasks change only the source, and MF-10 refreshes the copies. Don't change a skill's `description`: always-on on claude-code is 149 of 150.

### T3: the doctor and the settle gates share `_print_gates`
`src/workstream/cli.py:803` prints `warn <name>: <detail>` for every non-blocking gate, and `tests/test_adapt.py:126` and `tests/test_doctor.py:129` pin that form. `schema/review.schema.json:144` also constrains a gate's shape. So don't add a gate field or change the shared printer. `src/workstream/cli.py:897` is the one line that misreads.

### T4: the evidence parser splits on any `## ` line
`SECTION_RE` (`src/workstream/evidence.py:28`) ends a section at the next `## `, and rule text can hold one. `_named` (`:58`) picks the first heading containing `acceptance`, `decision` or `gotcha`, so the new heading must contain none of those. Parse the new section by hand, from its heading to the end of the file, so it must come last. Mark each file with `` ### `path` ``, so a `### ` inside the text isn't read as a file. `tests/fake_agent.py:66` matches the text between `## Proposed decisions` and `## Gotchas`, so nothing may go between them.

### T5: an `open:` line already means something
`result["open"]` (`src/workstream/settle.py:347`) names decisions just numbered, and `ws protocol stop` item 9 sends open decisions to the user. Text waiting to be applied isn't a question for anyone, so it gets its own prefix, `to apply:`, and no stop condition.

### T6: the file checked must be read from the integration checkout, and may have been reworded
`ws settle --root` and `ws close` run against `project.root`. A coordinator may reflow the text when applying it, so compare with whitespace collapsed. A path from a worker's evidence can point anywhere: `evidence.problems` rejects an absolute path or one with `..`. Rewording more than whitespace leaves the warning in place, which is why it warns rather than refuses.

### T7: `_with_decisions` stops at the first entry that doesn't fit
`src/workstream/brief.py:337` breaks, so one long entry hides every shorter one after it. Reordering alone doesn't fix that. `tests/test_settle.py:959` pins the `more:` pointer.

### T8: `CLOSES_RE` only reads an entry's first line
`src/workstream/decisions.py:19` anchors on the first line so a quoted `Closes:` closes nothing, and `closing_body` (`:74`) puts that line first. So `Changes:` goes after any `Closes:` line, anchored the same way. An open decision hasn't settled anything, so it must not prompt a correction.

### T9: `(changed by Dnnn)` is overwritten by the next correction
`correct_acceptance` (`src/workstream/tasks.py:541`) and `correct_summary` (`:561`) rewrite the text, so a second correction erases the first decision's mark, and the claim would warn again about a correction already made. Merge the marks: `(changed by D018, D040)`. The same text and decision must still produce the same bytes, so LE-04's `nothing changed` holds (`src/workstream/cli.py:319`).

### T10: `ws claim` has two paths
`cmd_claim` (`src/workstream/cli.py:662`) goes through `act.commit_claim` with `--commit` and `tasks.claim` without, and both must warn. Don't warn from inside `tasks.claim`: it's also used without a decisions log in reach.

### T11: a hard error in `validate_tasks` would break existing queues
Its open-task rules run on every `ws validate`, and `seed_from_plan` validates the existing tasks too (`src/workstream/plan.py:189`). So the tracking-file check is a warning there. `RF-02` and `RF-09` show legitimate items: tests about these files. The file names already live in `hook.WRITERS` (`src/workstream/hook.py:35`), so reuse them, with `TASKS_NAME` and friends, rather than a second list.

### T12: `correct_acceptance` drops `expect` on purpose
`src/workstream/tasks.py:543` removes it, since the old literal could make the new text impossible to pass. Keep that when `--expect` isn't given. With it, a string item becomes `{"text", "expect"}`. `_expect_errors` (`:259`) must run on the result, so a manual item or a task with no `verify` is refused. `PROTOCOL.md`'s task-schema line says `ws update` can't set `expect`, and must change.

### T13: every backticked `ws` command in a skill must parse, and protocol quotes are tested
`tests/test_protocol.py:66` parses them, with their arguments. `tests/test_rule_map.py` checks each row's quote exists, so keep the quoted literals in `PROTOCOL.md` and the skills. Core names no agent: `tests/test_no_project_literals.py`.

### T14: tasks sharing a file must be chained
The wave moves on as soon as a lower phase has nothing actionable, so `blockedBy` carries the order.

## 3. Design

### D-WARNING: the warning prints what's wrong, not the check's name
The scope gate's detail becomes `files outside the task's list: b.txt`, in both `settle_gates` and `ready_gates` (`src/workstream/gates.py:114`, `:138`). `src/workstream/cli.py:897` prints `warning: {detail or name}`, so it reads `T1: warning: files outside the task's list: b.txt`. `_print_gates` is unchanged and now reads `warn the diff stays within the task's files: files outside the task's list: b.txt`. Tests: `tests/test_settle.py:397` asserts the new wording and that `warning: the diff stays within` is gone. Rejected: a gate field for the warning (T3).

### D-TEXT: an evidence section for text someone else must apply
`evidence.skeleton` ends with `## Text to apply`, body `None.`, explaining the form. `evidence.parse` adds `texts: [{path, text}]`, read as T4 says. `evidence.problems` reports a section with text but no file, a file with no text, and an absolute or `..` path. `_cannot_edit_lines` (`src/workstream/brief.py:246`) points there instead of Gotchas, and the worker rules gain one line, since `_cannot_edit_lines` fires only when the task names the file. Tests beside `tests/test_plan_tools.py:273`. Rejected: parsing a convention inside Gotchas, which a worker can phrase any way.

### D-APPLY: `ws settle` and `ws close` track it until it's applied
`handoff.texts_to_apply(project, ws, rows)` reads each done task's evidence and returns those whose text isn't in the named file under `project.root`, whitespace collapsed (T6). A file that doesn't exist counts as not applied. `settle` adds them to its result after `_record`, and `cmd_settle` prints `to apply: MBZ-08: .claude/rules/enrichment.md (evidence/MBZ-08.md)`. `handoff.render` lists them. `cmd_close`, including `--dry-run`, prints a `warning:` for each and still closes, before any prune or purge removes the evidence. `ws-run` step 5 says that a `to apply:` line is the coordinator's to apply and commit before the next round, because it can edit what a background worker can't, and step 6's "do nothing else" allows it. Tests in `tests/test_settle.py`: listed at settle, gone once applied, across two tasks, none for a blocked task, and warned at close. Rejected: following every earlier task in the brief, which grows every brief and still doesn't say whether the text was applied.

### D-TRIM: decisions naming the task come first
`_with_decisions` orders entries so those naming `task["id"]` come first, each group newest first, and `continue`s past one that doesn't fit (T7). `relevant` stays as it is. Tests in `tests/test_brief.py`: an old entry naming the task survives where newer generic ones are dropped, a long one doesn't hide a short one, and the `more:` count is right.

### D-CHANGES: a decision says which tasks it changes
`ws decide --changes T1,T2` writes `Changes: T1, T2.` as the body's first line, after any `Closes:` line (T8). `decisions.changed_tasks(entry)` reads it. It refuses an unknown task, or one that's done or deferred, since `ws update` can't correct those. `tasks.correct_*` merge their marks (T9). `ws claim`, on both paths (T10), prints for each claimed task and each settled decision naming it with no mark in its summary or acceptance: `warning: T1: D018 changes it, and its summary and acceptance don't say so yet: ws update T1 --summary "..." --because D018`. A warning, because some decisions only change notes or verify, and a claim can be corrected afterwards since workers start after it. `ws-coordinate` line 13 gains the flag. Tests in `tests/test_decisions.py` and `tests/test_tasks.py`. Rejected: warning on every mention of a task id, which many decisions make without changing anything.

### D-CHANGED-SECTION: the brief says what changed since the plan
`_changed_lines` in `src/workstream/brief.py`, placed after Acceptance beside `_open_decision_lines` and likewise never trimmed: `## Changed since the plan`, a sentence saying these outrank the plan and the summary where they differ, then `- D018: <title>` per settled decision whose `Changes:` names this task. It uses titles only, so its size is bounded, and D-TRIM carries the bodies. Printed only when there is one. Tests in `tests/test_brief.py`. Rejected: rewriting cited plan text, since a plan is immutable and its number can't be located reliably; and a fixed sentence in every brief, which says nothing specific.

### D-TRACKING: acceptance naming a tracking file warns where it's written
`tasks.tracking_file_warnings(task)` returns one warning per item naming a tracking file (T11), saying `ws settle` writes it after evidence must pass, so the item should ask for the evidence or a proposed decision. `validate_tasks` adds it for open tasks, so `ws validate` and `ws seed --from-plan` show it. `ws seed` from JSON, `ws add` and `ws update --acceptance` print it too. `ws-plan` gains a clause in step 4. Tests in `tests/test_tasks.py`: warned on an open task, silent on a done one, exit 0 throughout. The user chose a warning over a refusal: all 3 such items among this repo's 274 are legitimate.

### D-DIFFERS: a difference from acceptance is proposed, and `expect` survives correction
The worker rules gain: a result that differs from an acceptance item goes under Proposed decisions as well as in the proof, even if you think it's fine. That makes D027's behaviour the rule. `ws update T --acceptance N "text" --expect "literal" --because D` sets the pin (T12), and `--expect` without `--acceptance` is refused. `ws-plan` already asks for `expect`. Tests in `tests/test_tasks.py`. Rejected: automatic comparison, since worded acceptance can't be compared mechanically.

## 4. Tasks

| Id | Title | Blocked by |
|---|---|---|
| MF-01 | Say what's wrong in the settle warning | |
| MF-02 | Add the evidence section for text to apply | |
| MF-03 | Track text to apply through settle and close | MF-01, MF-02 |
| MF-04 | Keep decisions naming the task when trimming | MF-02, MF-03 |
| MF-05 | `ws decide --changes`, with a warning at claim | MF-03 |
| MF-06 | Show what changed since the plan in the brief | MF-04, MF-05 |
| MF-07 | Warn on acceptance naming a tracking file | MF-05 |
| MF-08 | Propose differences, and `--expect` on `ws update` | MF-02, MF-07 |
| MF-09 | An eval for text left for a file a worker can't edit | MF-03 |
| MF-10 | Prove it end to end (foreground) | MF-06, MF-08, MF-09 |

MF-01, MF-03 and MF-04 share `tests/test_settle.py`; MF-02, MF-04 and MF-06 share `brief.py`; MF-01, MF-03, MF-05, MF-07 and MF-08 share `cli.py`; MF-05, MF-07 and MF-08 share `tasks.py`; MF-02 and MF-08 share `PROTOCOL.md`.

## 5. End-to-end verification

MF-10 runs a script with no agent, using the installed `ws` with the other nine tasks landed, on a sample repo in a folder whose path has a space, reproducing the MBZ cases:

1. A task touching a file outside its list: the settle line says `warning: files outside the task's list`.
2. Two background tasks each leaving text for one file, with a third task depending only on the second. Settling prints `to apply:` for both, `ws close --dry-run` warns about both, and after applying them nothing is listed.
3. `ws decide --changes` on a todo task: the claim warns, the brief has `## Changed since the plan`, and the decision survives trimming beside longer, newer ones. After `ws update --summary --because`, the claim of a second such task is the only warning left, and the first shows its mark.
4. An acceptance item naming a tracking file: warned at `ws add`, `ws validate` exits 0.
5. `ws update --acceptance --expect`: `ws verify` fails until the output holds the literal.

Then `ws adapt claude-code`, `--check` says OK, and `make eval AGENT=claude-code` runs on Opus 5.5 at medium effort, about $3. The results go in `docs/decisions/0015-mbz-feedback.md`, with what stays unproven. Nothing runs in subsonic-server.
