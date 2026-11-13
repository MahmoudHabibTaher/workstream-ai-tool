# Decisions: Claude Code pane UX

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-10, user): scope approved

The owner chose layout plus pre-flight for the pane. It keeps filling the prompt box only: no other targets and no presets. **Closed.**

## D002 (2026-11-13, PX-01): abandon fills its prompt plus `<reason>`, taken from the launch's `ask`

The old `promptText` appended `<why>`. Now the placeholder is the launch's own `ask` field, so the CLI names it, and the pane has no wording of its own. Rejected: keeping a literal `<why>` in the pane, which is a second copy of what the snapshot already says. **Closed.**

## D003 (2026-11-13, PX-01): the status writes stay between run/coordinate and the other launches

Pause and Resume still sit after Run and Coordinate, as before. Close and Abandon follow, in the snapshot's order. Rejected: drawing all launches first, which would move the buttons around before PX-02's layout work. **Closed.**

## D004 (2026-11-13, PX-02): a task under two parents is drawn in full once, then as a "(shown above)" repeat

The Graph is a depth-first walk from the tasks that wait on nothing here, with children taken from `unblocks` in priority order. A task with two blockers appears under both, so each edge shows, but it recurses only the first time. Leftovers (a cycle) are drawn at the top level so no task is dropped. Rejected: drawing each task once under its first parent only, which hides the second edge. **Closed.**

## D005 (2026-11-13, PX-02): a Graph line jumps to Tasks with that task expanded

Until PX-03 adds the task page, there is nowhere else to show a task. PX-03 can point `onJump` at the task page instead. Rejected: making Graph lines inert. **Closed.**

## D006 (2026-11-13, PX-02): Overview's documents are buttons that open the feed tab

The four documents the feed already pages (plan, progress, decisions, handoff) are shown when the snapshot gives a path, and pressing one opens that feed tab. Back from the feed returns to Overview, because `sub` is kept in the view. Evidence files are not listed: the feed has no tab for them. Rejected: listing bare paths. **Closed.**

## D007 (2026-11-13, PX-02): Overview's verify commands are each task's commands, once per label

The snapshot has no workstream-level command list, so Overview shows the union of the tasks' `verifyCommands`, in the order tasks first name them. Rejected: reading the project config, which would mean the pane computing a fact the CLI doesn't give. **Closed.**

## D008 (2026-11-13, PX-03): the task page replaces the inline expansion in Tasks

A task row now opens `screen: 'task'`, which shows everything the expansion did (summary, acceptance, verify, files, notes, requires, Review, Unclaim) plus depends on, unblocks and the claim. The expansion was removed from `detail.tsx`, so there is one view of a task, not two. The Graph's line (D005) now opens the page too. Rejected: keeping both, which would mean two copies of the same task view to keep in step. **Closed.**

## D009 (2026-11-13, PX-03): Back from a task page goes to detail, and Back from Review goes to the task page

Jumping between tasks keeps no history: Back always returns to the sub-screen the person was on. Review is reached only from a task page now, so its Back returns there. Rejected: a jump history stack, which is more state for little gain. **Closed.**

## D010 (2026-11-13, PX-04): a held launch draws as text with its message, since the surface's Button has no disabled state

A probe test rendered `<Button disabled isDisabled>`: the harness kept only `key` and `label` in its props, and a press still fired the handler. So "disables the button" is done by drawing the launch as dimmed text, "Run (blocked: <first blocking message>)", with a **Check again** button under the pre-flight results. Rejected: a Button whose press does nothing, which looks pressable. **Closed.**

## D011 (2026-11-13, PX-04): run-task's prompt comes from `ws launch argv --agent claude-code`, the last argument

The snapshot's `launches` are a row's (jetbrains_ux D010), so it holds no run-task text, and `src/workstream` is out of scope. `ws launch argv` is the CLI's own builder of that prompt; the JetBrains plugin reads it the same way. The agent is `claude-code`, the one the pane runs inside. It is fetched only after the checks pass. Rejected: a run-task template in the pane, which PX-01 just removed. **Open.** A `launches` list on each snapshot task would let the pane read it as it reads a row's; that is a src/workstream change for the owner to weigh. **Closed.**

## D012 (2026-11-13, PX-04): the pre-flight shows where it was asked, and is cleared on opening a workstream

One `preflight` atom holds the last result with its ws, kind and task. Detail shows a row launch's; the task page shows that task's Run This Task. A held button stays held until **Check again** or opening the workstream afresh, rather than re-checking on every snapshot poll. Rejected: re-running the checks on each poll, which would be a `ws launch check` per launch every 3 seconds. **Closed.**

## D013 (2026-11-13, PX-04): Run This Task is offered for a task not done or deferred, in a workstream whose row has launches

That matches where the row's own launches are offered (open rows only). Rejected: offering it on every task. **Closed.**

## D014 (2026-11-13, PX-05): the Graph's lost nesting is a new task, not a fail of PX-05

The owner saw every check pass, and the Graph draws, but its indentation isn't kept. `graph.tsx` indents with leading spaces inside a Text. The desktop surface collapses them, and `claude plugin test` keeps them, so the tests passed. The fix belongs in `ui/mod/hooks/views/graph.tsx`, which isn't in this task's files. The coordinator adds it as its own task, PX-06. Rejected: holding PX-05 open, which would hold a finished hand check on a code fix. **Closed.**

## D015 (2026-11-13, coordinator): Add PX-06: the Graph's nesting is lost on the desktop surface

PX-05's hand check (D014): leading spaces in a Text are collapsed by the desktop app and kept by claude plugin test, so the tests passed while the owner saw every task one level under PX-01. **Closed.**
