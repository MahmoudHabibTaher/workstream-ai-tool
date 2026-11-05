---
name: ws-run
description: Run a planned workstream (claim a batch, start a clean worker per task, land the results, repeat).
---

# Run a workstream

You coordinate; workers do the tasks, each in a clean context. Never do a background task yourself, and never chain tasks in one context. Starting this skill is the go-ahead for the whole loop, up to the conditions in `ws protocol stop`.

**Once, first:** `ws validate -w <id>`, `ws reconcile` and `ws status -w <id>`. Tell the user how many tasks and phases this covers. With no id, `ws list`; if several are open, ask which.

**Then loop:**

1. `ws wave -w <id>`. Exit 2 means finished: see `ws-coordinate` to close. Exit 3 means stuck: stop.
2. **Leftovers first.** A task listed as in progress outside a batch you are running was interrupted. Try `ws settle <task> -w <id> --dry-run`: land it if the gates pass. If they fail but the worktree holds work, start a fresh worker with the usual prompt on the same worktree, and don't claim it again: its brief lists what it found. Requeue with `ws worktree remove <task> -w <id>` and `ws unclaim <task> -w <id>` only when the worktree has nothing to keep. Say which you did.
3. **Claim one batch** from the wave: background tasks, up to `max_workers`.
   ```
   ws claim --commit -w <id> --by <label> <task> <task>
   ws worktree create -w <id> <task> <task>
   ```
4. **Start one fresh worker per task,** in parallel, on your own model unless the user named another. The whole prompt is: run `ws brief <task> -w <id>` and follow it. Wait to be notified; never poll. A finished worker's context is spent, so never give it a second task. One that ends without saying done or blocked has stopped, and won't resume: handle it as a leftover, as in step 2.
5. **Land them:** `ws settle -w <id> <task> <task>`. A worker's report is a claim; the gates in this command are the check. Don't redo their work to verify it. A `to apply:` line is text a worker couldn't write, kept in the evidence file it names: apply it and commit before the next round, because you can edit what a background worker can't.
6. Give the user one line: what landed and what is open. Back to 1. Between rounds, do nothing else but apply that text: work outside a claimed task can't be attributed.

**Foreground tasks** run in this session, one at a time, after the batch: claim it alone and follow its brief yourself, landing step included. No checkout changes branch.

**Resuming a blocked task:** once the user answers, start a fresh worker with the same prompt on the same worktree. Don't claim it again: the brief sees it is blocked and tells the worker to keep what's finished. Land it with `ws settle` as usual. Never `ws unclaim <task> -w <id>` for this: that requeues the task instead of resuming it.

When the loop ends, report once: each task and its commit, how it ended, what is ready or blocked, and every question raised, unanswered. Those are the user's to settle.
