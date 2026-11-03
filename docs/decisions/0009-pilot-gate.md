# 0009: The pilot gate

Decided at the end of M6, which had to end with "targets met, or budgets revised on evidence before any UI work". [The results](../pilot-results.md) hold every figure and how it was made.

**Result: passed, with one measure replaced.** The tool saves context on real work. One of the two targets was missed, and it turned out to measure the wrong thing. UI work may start when the user says so.

| Measure, Claude Code on the Rust project | Before | After | Target | Verdict |
|---|---|---|---|---|
| Worker growth, turn 1 to turn 5 | 25,110 | 50,472 | ≤ 8,000 | Missed, and replaced below |
| Coordinator peak | 172,724 | 58,305, highest 61,233 | ≤ 80,000 | Met, on runs of up to three tasks |
| Worker cumulative | 5,054,896 | 1,999,531 | none | 60% lower |
| Worker peak | 155,432 | 119,057 | none | 23% lower |
| Worker at turn 1 | 53,806 | 14,675 | none | 73% lower |

## What changed

**Worker growth is replaced by two measures.** The target assumed a worker reads one thing per model call, so turn 5 would fall during its orientation. Real workers read several files in one call, so turn 5 falls after most of their reading, and they need 44% fewer calls to finish. A higher figure there came with a lower total.

| New measure | Target | Measured | Why this number |
|---|---|---|---|
| Worker first step, turn 1 to turn 2: what the brief brings in | ≤ 8,000 | 4,718 | Keeps the old limit, on the part this tool controls |
| Worker cumulative, the median across a workstream | ≤ 2,500,000 | 1,999,531 | Holds most of the gain and leaves room for harder tasks: one of these five reached 4,419,595 |

`ws audit usage` now reports the first step as `step 1`. Rejected: keeping the old target and telling workers to read one file per call, which would raise the number of calls and the total to improve one figure. Also rejected: dropping it with no replacement, which would leave nothing watching what the brief adds.

**The coordinator target stays.** It's met, but only on runs of up to three tasks, because blocked tasks split the run into separate sessions. The longest rose 17,448 over three tasks. At that rate a coordinator reaches 80,000 at around six, so the next long run should check this.

**The static budgets stay.** All of them pass, and real briefs fit: about 2,400 tokens on the Rust project and about 1,440 at the median on old Kotlin queues, against a budget of 2,500.

## Not proven

- **Copilot on real work.** The Kotlin project got an import only, by the user's choice, because a replay would spend paid work-account credits. All 21 old queues convert, but no agent ran on them, and the hook has still never fired on Copilot.
- **A coordinator holding a whole workstream.** See above.
- **Why turn 1 fell.** The worker's short tool list is the likely reason, but the Claude Code version and the model changed too.
- **That the settings file carries the two long-run variables.** Setting them in the shell is proven, and that is how the pilot did it.
- **That the work is comparable.** The "before" figures cover 121 workers on all kinds of tasks, and the "after" figures cover four tasks from one workstream.
- **That the code is what the user wants.** Gates passed and tests pass, but nobody has reviewed the branch, and two decisions on it are still the user's. It hasn't been merged.

## Left to fix, none of it UI

Found by the pilot, and the first is the one a new user would hit soonest:

1. `ws adapt` allows none of a project's own commands, so a headless worker can't run its build tools: 24 denied calls across seven workers.
2. Workers can't edit under `.claude/`, even with an allow rule, so a note there comes back as a follow-up.
3. `ws validate` warns on old `commit` fields holding prose, on the marker `ws import` itself writes, and on files a task will create, which is 40 lines on an old project.
4. `ws evidence check` on a task that has already landed reports its checks as never run.

**Cost of finding this out:** $14.54 at list price, of a $25 cap, with $4.76 of it on two runs that stopped early. Every problem that stopped a run came from real tasks taking longer than a sample's: 636 scripted tests and five evals hadn't hit them.
