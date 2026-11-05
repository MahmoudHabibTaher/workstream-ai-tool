# Where every rule went

M3 is done when each prose rule in the two source harnesses has a home here: enforced in code, kept as a line in a skill or the protocol, handed to the project, or deliberately deleted. A rule the CLI enforces costs no context, which is where the savings come from.

Rules are restated in my own words. Neither harness's text is copied here.

`tests/test_rule_map.py` checks this file. A `code` row must name something that exists, and a `skill` or `protocol` row must quote text that is really there, so a rule can't be dropped without changing this table.

| Now | Where or why |
|---|---|
| `code` | `module.name` in `src/workstream/` |
| `skill` | `skill-name: "text in it"` |
| `protocol` | `section: "text in it"` |
| `project` | It's a fact about one project or agent, so it goes in config, a runbook or an adapter |
| `deleted` | Why it is no longer needed |

## Planning

| Source | Rule | Now | Where or why |
|---|---|---|---|
| both | The deliverable is a workstream, not code; approval doesn't start anything | skill | ws-plan: "never "start it", even on autopilot" |
| both | Every task starts unstarted, with no bootstrap task marked done | code | tasks.validate_tasks |
| subsonic | Stop if the work duplicates an open workstream | skill | ws-plan: "If this duplicates open work" |
| kotlin | Read the registry, since only it shows closed workstreams | skill | ws-plan: "`ws list --all`" |
| subsonic | Decisions of related past workstreams stay binding | skill | ws-plan: "they stay binding" |
| both | Ask the user only what the code can't answer | skill | ws-plan: "only what the code can't answer" |
| kotlin | Ask one question at a time | skill | ws-plan: "one question at a time" |
| subsonic | Find traps in real code, with file and line, before designing | skill | ws-plan: "This is the plan's main value" |
| subsonic | Note existing tests that new ones should resemble | skill | ws-plan: "existing tests new ones should resemble" |
| subsonic | Check files near a size limit | project | A project's own check: a `verify` key |
| subsonic | Every design includes how it is tested | protocol | plan-shape: "how it is tested" |
| subsonic | Docs work belongs in the task that changes the thing | skill | ws-plan: "Docs go with the task that changes them" |
| subsonic | One task is one branch and one merge | skill | ws-plan: "One task is one branch and one merge" |
| kotlin | Size a task to one clean session | skill | ws-plan: "sized for one clean session" |
| subsonic | Prefer 3 to 10 tasks; 20 or more is probably two workstreams | skill | ws-plan: "a plan needing 20 or more" |
| kotlin | Acceptance that can't be checked means the task is too vague | skill | ws-plan: "is too vague" |
| kotlin | A task touching many files is too big | skill | ws-plan: "is too big" |
| subsonic | Pick a free task prefix | code | registry.create |
| subsonic | Priority is the real order; phase groups | protocol | task-schema: "the real order" |
| both | Acceptance items are observable facts | protocol | task-schema: "Observable facts" |
| subsonic | Tasks editing the same file are chained | code | tasks.validate_tasks |
| subsonic | What a worktree can't do goes in a typed field, never in notes | skill | ws-plan: "never in `notes`" |
| subsonic | Some requirements force foreground, and contradictions are refused | code | tasks._mode_conflict |
| subsonic | The last task is the end-to-end proof | skill | ws-plan: "The last task is the end-to-end proof" |
| subsonic | `needsUserDecision` only for what planning couldn't settle | protocol | task-schema: "True only for what planning couldn't settle" |
| subsonic | Every open task states its release impact, when the workstream ships a release | code | tasks.validate_tasks |
| subsonic | A workstream may skip the release | skill | ws-plan: "`--tier full` if it ships a release" |
| subsonic | `docs` paths must exist | code | tasks.validate_tasks |
| subsonic | The plan is written once and split, not written again | code | plan.seed_from_plan |
| subsonic | No template placeholder survives | code | registry.validate_entry |
| subsonic | The plan is immutable once approved | code | plan.seed_from_plan |
| kotlin | Choose the narrowest folder holding everything the tasks touch | skill | ws-plan: "narrowest folder" |
| kotlin | Workstream names are unique across the repo | code | registry.create |
| kotlin | A queue outside a workstreams folder isn't a workstream | code | registry.discover_queues |
| both | Present the plan compactly | skill | ws-plan: "Present it compactly" |
| kotlin | Write no files before the user approves | skill | ws-plan: "Write no workstream files before the user approves" |
| kotlin | Never invent a validation command | skill | ws-plan: "Never invent a command" |
| kotlin | Lint alone proves nothing | skill | ws-plan: "Lint alone proves nothing" |
| kotlin | Each kind of task must run what it produces | code | tasks._verify_errors |
| kotlin | Take the baseline at planning time, on a clean tree | code | verify.record_baseline |
| kotlin | A failing build on an untouched tree is not a baseline | skill | ws-plan: "that is a broken build" |
| both | Commit the plan as one restore point | skill | ws-plan: "Commit the folder and the registry" |
| both | Then stop; starting is the user's call, in a fresh session | skill | ws-plan: "in a fresh session" |
| kotlin | Delegate planning to a dedicated agent | deleted | Optional, and the choice belongs to the session. It says nothing about the result |
| kotlin | A workstream has a single root task | deleted | Nothing depends on it, and parallel work wants several roots |
| kotlin | Each queue carries its own copy of the protocol steps | deleted | One versioned protocol is the point |
| kotlin | Failure-mode tables in each skill | deleted | Each row is now a gate or a line in this table |

## Claiming and batching

| Source | Rule | Now | Where or why |
|---|---|---|---|
| both | Only actionable tasks can be claimed, all or nothing | code | tasks.claim |
| subsonic | A workstream it depends on must be done first | code | registry.check_claimable |
| subsonic | A paused or closed workstream isn't dispatched until resumed | code | registry.check_claimable |
| subsonic | Commit the claim on the integration branch before workers start | code | act.commit_claim |
| subsonic | Workers branch from the claim commit, or they start from the wrong code | code | worktree.create |
| subsonic | A batch is one phase | code | tasks.batch_problems |
| subsonic | Tasks in a batch don't share files | code | tasks.batch_problems |
| subsonic | Split on the mode field alone | code | worktree.create |
| subsonic | Foreground tasks run alone in the main session, after the batch | skill | ws-run: "Foreground tasks" |
| subsonic | Cap the batch for review load | code | worktree.create |
| subsonic | Ignored dependencies a worktree needs get linked in | project | `[worktree] setup` in the config |
| subsonic | A task needing confirmation isn't dispatched silently | code | graph.actionable |
| kotlin | One open session at a time | deleted | Worktrees replaced the single slot; a claim is the record |
| kotlin | Clock in again after a crash | code | snapshot.health_findings |
| both | Interrupted tasks are dealt with before new work | skill | ws-run: "Leftovers first" |
| subsonic | Never delete a branch holding unmerged commits | code | worktree.remove |
| kotlin | Pre-flight: valid graph, no drift, clean tree | skill | ws-run: "Once, first" |
| kotlin | Say how many tasks this covers before starting | skill | ws-run: "Tell the user how many tasks" |
| subsonic | Invoking the run is the go-ahead for all of it | skill | ws-run: "Starting this skill is the go-ahead" |
| kotlin | Sequential shifts only | deleted | Worktrees and the single writer made parallel safe |

## Working a task

| Source | Rule | Now | Where or why |
|---|---|---|---|
| both | Workers get everything they need in one place | code | brief.render |
| both | Read handoff, progress and decisions in order at start | code | brief.render |
| both | Read cited traps and design sections | code | brief._plan_sections |
| subsonic | Read only decisions that bear on the task | code | decisions.relevant |
| both | One task, then stop | protocol | worker: "Do this task only, then stop" |
| kotlin | Never chain tasks in one context | skill | ws-run: "never chain tasks in one context" |
| kotlin | The declared scope binds every task | code | brief._scope_lines |
| both | Work outside scope is a stop, not a quiet widening | protocol | worker: "the work needs something out of scope" |
| subsonic | Workers write code, docs and their own evidence | protocol | worker: "Every other file in a workstream folder" |
| new | Text for a file a worker can't edit goes in its own evidence section | protocol | worker: "under `## Text to apply`" |
| new | That text is tracked at settle and close until it is in its file | code | handoff.texts_to_apply |
| new | Applying that text is the coordinator's job before the next round | skill | ws-run: "apply it and commit before the next round" |
| subsonic | The single writer is enforced, not hoped for | code | gates.tracking_violations |
| both | Check each acceptance item for real and quote it | protocol | worker: "Check each acceptance item for real" |
| both | Findings already in the baseline aren't the task's to fix or grow | protocol | worker: "don't fix them, and don't add to them" |
| subsonic | Decisions are proposed, never numbered, by workers | protocol | worker: "Never invent a `D` number" |
| both | Don't reopen a settled decision without new evidence | protocol | worker: "Don't reopen a recorded decision" |
| subsonic | Contradicting a decision is a stop | protocol | worker: "it would contradict a decision" |
| subsonic | A trap the plan missed that changes the design is a stop | protocol | worker: "the plan missed something" |
| subsonic | An open question stays marked open in the log | code | decisions.render_entry |
| kotlin | A wrong premise is a stop | protocol | worker: "the task's premise is wrong" |
| subsonic | A `verify` that can't prove acceptance is a stop | protocol | worker: "a `verify` command can't prove what acceptance claims" |
| subsonic | Blocked is committed on the branch and reported | protocol | worker: "commit that, and report" |
| subsonic | Workers don't merge or leave their branch, except a foreground brief's landing step | protocol | worker: "Don't merge" |
| kotlin | Blocking is a correct outcome, surfaced to the user | protocol | stop: "as a decision the user owes" |
| both | Run named commands, not guesses | code | tasks.verify_commands |
| both | Build output stays out of context | code | verify.format_run |
| kotlin | A key passes when nothing is reported beyond the baseline | code | baseline.judge |
| kotlin | A validation flag is the agent's own assertion | code | verify.verify_task |
| both | Rejected options are written down | code | evidence.problems |
| subsonic | Evidence has one shape, started for the worker | code | evidence.skeleton |
| subsonic | Update rule globs and doc pages; doc references must pass | project | A project's own docs step: a `verify` key and its instructions |
| subsonic | Re-read hard constraints before touching named files | project | The project's own instructions, loaded by path |
| kotlin | Doc-comment length budgets | project | Language conventions belong to the project |
| kotlin | One task, one work commit | deleted | A merge commit stands for the whole branch |
| subsonic | Run a baseline check at the start of each session | deleted | Workers verify before anything lands and `settle` re-checks merged code, so a red tree shows up without a ritual. `ws doctor --run` does it on demand |
| kotlin | Check the clock mid-shift | code | cli.cmd_status |
| kotlin | Keep a legacy start and done flow for one-offs | deleted | Two ways to do one thing |

## Landing

| Source | Rule | Now | Where or why |
|---|---|---|---|
| both | A worker's report is a claim, not a fact | skill | ws-run: "A worker's report is a claim" |
| subsonic | Wait to be notified; never poll | skill | ws-run: "never poll" |
| kotlin | Never give a finished worker a second task | skill | ws-run: "never give it a second task" |
| kotlin | Workers run on the coordinator's model unless told otherwise | skill | ws-run: "on your own model" |
| subsonic | The coordinator must be the main session | project | An agent fact, in the generated adapter's notes |
| subsonic | Evidence must exist, with proof per item | code | evidence.problems |
| subsonic | A claimed `verify` must really have run | code | gates.verification_gates |
| kotlin | Validation is judged against what actually landed | code | gates.verification_gates |
| subsonic | Merge sequentially, lowest priority first | code | settle.settle |
| subsonic | A conflict is a stop; don't resolve it by hand | protocol | stop: "Don't resolve conflicts by hand" |
| subsonic | Check the tree after each merge, and stop on red | code | settle._post_merge |
| subsonic | Blocked work stays unmerged on its branch | code | settle._settle_one |
| subsonic | Clean up the worktree and branch after landing | code | settle._clean_up |
| both | A done task must name a real commit | code | tasks.update |
| kotlin | Never rewrite a commit a task points at | code | registry._queue_problems |
| subsonic | Number proposals in merge order and rewrite the evidence | code | settle._number_decisions |
| both | A progress entry per task, newest first | code | settle._progress_entries |
| kotlin | Refuse to settle unless the log and handoff were updated | deleted | `settle` writes both, so they can't be forgotten |
| both | Overwrite the handoff with where things stand | code | handoff.render |
| subsonic | The handoff lists files left mid-edit | deleted | A worker's edits stay in its worktree, and removing one with uncommitted work is refused |
| subsonic | All tracking changes land in one commit | code | settle._record |
| both | Registry counts stay current as a side effect | code | settle._record |
| kotlin | Touching files a task didn't name warns, without blocking | code | gates.out_of_scope |
| kotlin | Dependencies must be done before settling | code | gates.settle_gates |
| kotlin | The tree must be clean | code | settle.check_checkout |
| subsonic | Confirm each phase landed before the next | code | gates.settle_gates |
| both | Report once, with commits and open questions | skill | ws-run: "report once" |
| both | Don't touch anything between rounds | skill | ws-run: "Between rounds, do nothing else" |
| kotlin | If a round makes no progress, stop whatever the agent said | protocol | stop: "A round lands nothing" |
| kotlin | Pass on questions unanswered | protocol | stop: "Pass it on unanswered" |
| kotlin | A `force` flag that downgrades gates | deleted | No gate has one |

## Lifecycle and release

| Source | Rule | Now | Where or why |
|---|---|---|---|
| both | The registry is written only by the CLI | protocol | files: "The CLI only" |
| kotlin | Closing writes a record before deleting anything | code | registry.close |
| kotlin | Closing refuses when the folder holds the registry | code | registry.close |
| kotlin | Drift is reported, never silently repaired | code | registry.reconcile |
| kotlin | Choose a workstream by flag, folder, then the only open one, else refuse | code | cli._resolve_ws |
| kotlin | Reset clears run-time state and never the definitions | code | tasks.reset |
| kotlin | Clear a queue to re-plan the same folder | deleted | Decision record 0004 |
| both | Each fact has one home | protocol | files: "Each fact has one home" |
| subsonic | A task the plan missed needs a decision saying why | skill | ws-coordinate: "`ws decide "..." --why "..."` to say why" |
| subsonic | Correct a `verify` after reading the proposal | skill | ws-coordinate: "A `verify` a worker found wrong" |
| subsonic | Pausing or abandoning is the user's say-so | skill | ws-coordinate: "only on the user's say-so" |
| subsonic | Closing walks the plan's end-to-end checks | skill | ws-coordinate: "Walk the end-to-end section" |
| subsonic | Closing with deferred tasks is the user's call | protocol | stop: "the queue closes with deferred tasks" |
| subsonic | A stuck queue is a stop | protocol | stop: "`ws wave` exits 3" |
| subsonic | The bump is the highest impact among done tasks | code | registry.release_bump |
| subsonic | A major bump is a stop | protocol | stop: "A release would be `major`" |
| subsonic | No impact means no release | skill | ws-coordinate: "`none` means no release" |
| subsonic | A release fix isn't a change to the plan | skill | ws-coordinate: "is not a change to `PLAN.md`" |
| subsonic | Pinned toolchain checks, tags, CI watching, deploy probes, rollback | project | The project's runbook, named in `[release]` |
| subsonic | Clean build caches after a workstream | project | The project's runbook |
| kotlin | Reuse rules and module-specific command notes | project | The project's own instructions |
