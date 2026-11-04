# Decisions: Left open

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-04, user): scope approved

The user asked for one task and one fresh background worker per bug under Left open in docs/decisions/0012-run-feedback.md, with a final proof task. Foreground tasks always get a worktree, including those with requires, and their briefs land through --root, so the main checkout never changes branch. Rejected: keeping the refusal for tasks with requires. Claude Code eval spend is approved for LO-09; Copilot evals are not. D013 and the rest of run_feedback's decisions stay binding, including the 4500 brief budget, and D013's doubled marker is not rewritten. **Closed.**

## D002 (2026-11-04, coordinator): add LO-10 to LO-14 for the ws gaps subsonic-server's first real use found, keeping LO-09's blockers as they are

A session in subsonic-server used the new ws commands to get MBZ-07 ready to claim, and reported five gaps. They belong here, not in a new workstream, and the user wants each issue on its own agent, so one task per gap. All five held against the code; none was dropped. 1 and 2: cmd_update has no --summary and refuses bare --commit without --acceptance (reproduced). 4: tasks.py _verify_warnings names only export. 5: cmd_update always prints status. 3: a sample repo showed that a no-match filter exits 0 and passes ws verify, and that an expect of the runner's pass line fails it, so LO-12 is documentation with no new check. Rejected: detecting no tests from the exit code or from runner output, because the exit code says nothing and matching each runner's words is what tests/test_no_project_literals.py keeps out of core. The same run found two limits LO-12 must state: an expect of the bare test name passes when make echoes the command, and ws add stores acceptance as text so it can't set expect (ws seed can). Order: LO-10, LO-11, LO-13 and LO-14 chain after LO-08 because they share cli.py, tasks.py or tests/test_tasks.py; LO-12 follows LO-05 because they share PROTOCOL.md and tests/test_protocol.py. LO-09 stays as approved and does not wait on them, so only their lower phases put them first: land each before asking ws wave again, or LO-09 can be offered while one is in progress. PLAN.md's end-to-end section doesn't cover them either; their own tests prove them, and LO-09's Claude Code evals run with them landed if that order holds. Rejected: chaining them after LO-09, which would land them after the proof and the evals. **Closed.**

## D003 (2026-11-04, LO-05): the landing step shell-quotes the checkout path

`brief.py` passes the path through `shlex.quote`, because a path with a space, as this repo's own has, would otherwise split into two arguments when pasted. A test lands a task from such a path.

Rejected: printing the path bare, which matches the plan's wording but fails on this repo. **Closed.**

## D004 (2026-11-04, LO-05): the landing step tells the worker to leave the worktree first

Settling removes the worktree, so a shell sitting in it is left in a deleted folder. The settle itself still succeeds from there, as the tests show, so this is advice about the shell afterwards and not a requirement.

Rejected: saying nothing, which leaves the worker's next command failing with no explanation. **Closed.**

## D005 (2026-11-04, LO-06): `ws next --json` with only held tasks left prints text, not JSON

It prints the same held-back lines with or without `--json`, because the existing empty case already prints plain text under `--json` and D-NEXT says to behave as that case does. The first line still starts "(no actionable task", so a caller checking that prefix keeps working.
Rejected: a JSON shape for the held case, which would make the two empty cases differ and add an output format the task did not ask for. **Closed.**

## D006 (2026-11-04, LO-06): `_print_held` split out of `_print_held_and_blocked`

`cmd_next` shares the held-back wording through a small helper rather than calling `_print_held_and_blocked`, since D-NEXT asks for the held tasks only.
Rejected: calling `_print_held_and_blocked` directly, which would also list blocked tasks under `ws next`. **Closed.**

## D007 (2026-11-04, LO-12): the schema says "`ws update` with `--acceptance`" rather than "`ws update --acceptance`"

`test_every_command_they_mention_parses` parses every backticked `ws` command, and `ws update --acceptance` alone fails to parse because the flag takes two arguments. The rewording says the same thing and leaves that test as it is.

Rejected: adding an exception to that test, which would weaken a check to suit one phrase; and dropping the backticks, which would make the command the only unmarked one in the row. **Closed.**
