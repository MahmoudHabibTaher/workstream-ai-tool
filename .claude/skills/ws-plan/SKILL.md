---
name: ws-plan
description: Plan large work as a workstream of verifiable tasks (traps, design, baseline). Never implements it.
---

# Plan a workstream

The deliverable is a committed, registered workstream, not code. Approving a plan means "create it", never "start it", even on autopilot. Every task stays `todo`.

1. **Orient.** `ws list --all` shows what exists and which names and prefixes are taken. If this duplicates open work, stop and say so. Read the project's own instructions, and the decisions of related workstreams: they stay binding.
2. **Settle scope.** Ask the user only what the code can't answer, one question at a time: the outcome, what is out of scope, which trade-off when two designs are sound. Write down their answers for the `ws-decisions` block.
3. **Find the traps.** This is the plan's main value. For each change, read the real code and record what makes the obvious change wrong, with `file:line`. Note the existing tests new ones should resemble.
4. **Design and cut tasks.** Follow `ws protocol plan-shape` and `ws protocol task-schema`.
   - One task is one branch and one merge, sized for one clean session. Prefer 3 to 10; a plan needing 20 or more is probably two workstreams.
   - A task whose acceptance can't be checked is too vague: split it. An item whose result must be an exact value names it with `expect`. An item asking for a change to a tracking file, such as `tasks_list.json` or `DECISIONS.md`, can't pass, since settling writes those after evidence must pass: ask for the evidence or a proposed decision. One touching more than a handful of files is too big.
   - `verify` must run what the task produces. Lint alone proves nothing. Never invent a command: use `[commands]` keys you have seen work.
   - Say what a worktree can't do in `mode` and `requires`, never in `notes`.
   - The last task is the end-to-end proof. Docs go with the task that changes them.
5. **Present it compactly:** phases, ids, titles, dependencies, the scope rule, open questions. Write no workstream files before the user approves, and say that approving creates it without starting anything.
6. **Create it.** Choose the narrowest folder holding everything the tasks touch (`--under`, or the repo's root folder for wider work). Add `--tier lite` for a few tasks needing no decision log, or `--tier full` if it ships a release.
   ```
   ws new <id> --title "..." --summary "..." --prefix <PREFIX>
   ws seed -w <id> --from-plan <plan file>
   ws baseline record -w <id>
   ws validate -w <id>
   ```
   If a compile or test command fails on the untouched tree, stop and tell the user: that is a broken build, not a baseline. Commit the folder and the registry as `<id>: plan`.
7. **Stop.** Report the folder, the task table and the first ready task. Starting it is the user's call, in a fresh session with `ws-run`, even if they ask you to carry on here.

## On Claude Code

Do steps 1 to 5 in plan mode, and ask with the question tool. The plan file you write there is what `ws seed --from-plan` reads.
