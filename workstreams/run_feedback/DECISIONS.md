# Decisions: Run feedback

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-04, user): scope approved

The user asked for each issue to be handled by its own agent, instead of grouped steps. So there is one task per issue, each worked by a fresh background worker, plus one final proof task. Subsonic-server's own fixes stay out of this queue. RF-14 (expected output on acceptance items) was offered as the one to drop, and the user kept it. Claude Code eval spend is approved for RF-15; Copilot evals are not. **Closed.**

## D002 (2026-11-04, RF-01): an entry that doesn't fit is skipped, and later shorter ones are still kept

D-GOTCHA says to keep whole entries up to the cap but not whether to stop at the first that doesn't fit. Going on keeps more at the same cost, and T5's complaint was short late gotchas being lost. So an entry is cut only when no entry fits whole; alongside one that fits, an over-limit entry is left out and counted. Rejected: stopping at the first entry that doesn't fit, since one long bullet would hide every short one after it. **Closed.**

## D003 (2026-11-04, RF-01): a cut entry counts as one in `(N more in <path>)`

D-GOTCHA asks for the same pointer on a cut entry, and `(0 more ...)` would say nothing was left out. So N counts entries not shown whole, and a lone cut entry reads `(1 more in <path>)`. Rejected: a different wording for the cut case, which D-GOTCHA rules out. **Closed.**

## D004 (2026-11-04, RF-04): only a line with a leading pipe is a table row, and the first cell is read literally

`find_section` skips rows inside code fences, and doesn't read `G7 | text` (no leading pipe) or `| **G7** | text |` (bold) as G7. D-CITE says the first cell starts with the ref, and a loose match could turn prose into a citation. Those forms still get the warning, so nothing is hidden. Rejected: stripping emphasis markup and accepting pipeless rows. **Closed.**

## D005 (2026-11-04, RF-04): a blank PLAN.md counts as not written

`citation_warning` skips an empty or whitespace-only `PLAN.md` as it does a placeholder one, since it has nothing to cite yet. Rejected: warning about every ref in a file that has no plan in it. **Closed.**

## D006 (2026-11-04, RF-05): operators inside quotes or after a backslash don't count, and a bare assignment doesn't warn

D-ENV says "later has `&&`, `||`, `;` or `|`". Read literally, `A=1 sh -c 'a && b'` and `A=1 find . -exec rm {} \;` would warn, though the variable reaches everything that runs. So quoted strings and escaped characters are masked before the search. `A=1 && b` has no command word after the assignment, so it sets a shell variable that lasts, and it doesn't warn. A prefix with several assignments names them all.

Rejected: a literal substring search, for the false warnings above; `shlex`, because in POSIX mode it strips the quotes, so `\;` and `"&&"` look like real operators, and in non-POSIX mode it splits `A="x y"`. **Closed.**

## D007 (2026-11-04, RF-06): the handoff falls back to notes, then the title, when a blocked task has no reason

A task blocked before this change has its reason in `notes`, and `ws update --status blocked` records no reason, so those blocks would otherwise lose their explanation in the handoff. The cost is that a hand-blocked task can show a planner's hint in the reason's place.

Rejected: reason or title only, because older queues' reasons would disappear from the handoff. **Closed.**

## D008 (2026-11-04, RF-06): any status change away from blocked clears blockedReason, inside tasks.update

D-REASON names landing and `ws unclaim`. Landing goes through `tasks.update`, so the clear lives there, and `ws update --status todo` or `in-progress` can't leave a stale reason on a task that is no longer blocked. `unclaim` and `reset` write the task directly and clear it themselves.

Rejected: clearing only in settle's landing path, which leaves the `ws update` route stale. **Closed.**

## D009 (2026-11-04, RF-07): `_at_task` returns the opened checkout's registry row, not the integration checkout's

The folder paths in the returned row must fit the checkout that will write evidence, and a row changed on the integration branch since the claim might not. Only the task itself comes from the integration checkout, as D-SOURCE says. Rejected: returning the integration checkout's row, which is simpler but could point a worktree's evidence at a path its branch doesn't have. **Closed.**

## D010 (2026-11-04, RF-08): `ws wave` and the lanes screen use the handoff's reason chain

A blocked task shows `blockedReason`, then `notes`, then its title, as D007 does for the handoff, so older queues' reasons still appear. Rejected: reason only, which would show nothing for a hand-blocked task. **Closed.**

## D011 (2026-11-04, RF-08): `heldBack` has one entry per task, holder and path

A task held by two tasks, or on two paths, gets one entry each, so every cause is visible and each must clear. The schema's `{id, by, path}` shape can't hold more than one cause per entry. Rejected: first cause only, which hides what else must land. **Closed.**

## D012 (2026-11-04, RF-08): the claim test and lanes test sit outside the listed test files

The `ws claim --commit` test is in `tests/test_protocol.py`, beside the other batch refusals and their git setup. The lanes test is in `ui/web/tests/logic.test.mjs`, the only place JS runs, which needed `waveNotes` exported from `lanes.js`. Rejected: calling `batch_problems` directly from `tests/test_tasks.py`, which wouldn't prove the command refuses. **Closed.**

## D013 (2026-11-04, user): briefs get their own 4500-token budget, separate from worker orientation

RF-15's brief went over the shared 2500 worker budget at RF-08's settle (2873 at RF-10's claim) because its Builds on section repeats every earlier task's gotchas, and that failed make audit for every task verifying with audit. The user chose to raise the budget. 4500 allows for about 310 tokens per landing across the five remaining tasks, the fastest growth seen. Worker orientation stays at 2500. Rejected: capping Builds on in brief.py (the coordinator's recommendation), and exempting RF-15. This adds RF-16. **Closed.** **Closed.**
