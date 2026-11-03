# Pilot results

M6's measurements: what real sessions carried before this tool, and what they carry on it. Every figure comes from `ws audit usage`, which reads each agent's own transcripts and reports numbers only. Tokens are the context in each model call, and the two agents count differently, so compare within an agent and never across.

## Before

Measured on 2026-11-02, up to 2026-11-01, so nothing here ran on this tool. Figures are medians per session.

**Claude Code on the Rust project:**

```bash
ws audit usage --agent claude-code --project <path> --until 2026-11-01
```

| Role | Sessions | Turns | Turn 1 | Turn 5 | Growth | Peak | Highest | Cumulative |
|---|---|---|---|---|---|---|---|---|
| Worker | 121 | 41 | 53,806 | 79,058 | 25,110 | 155,432 | 406,710 | 5,054,896 |
| Coordinator | 35 | 77 | 71,876 | 85,851 | 13,663 | 172,724 | 481,101 | 9,184,985 |

**Copilot CLI on the Kotlin project:**

```bash
ws audit usage --agent copilot-cli --project <path> --until 2026-11-01 --worker-marker 'clockin|shift'
```

| Role | Sessions | Turns | Turn 1 | Turn 5 | Growth | Peak | Highest | Cumulative |
|---|---|---|---|---|---|---|---|---|
| Worker | 28 | 17 | 60,806 | 71,775 | 10,698 | 94,795 | 160,765 | 1,306,702 |

Copilot has no coordinator row because that harness ran its shifts one at a time, with no session that started workers. Only 63 of its sessions on that project have per-call figures, since older ones don't record them, and the 28 workers are picked out by a rough text match on their opening prompt. Treat that row as approximate.

## How this differs from the first comparison

[The comparison](harness-comparison.md) estimated these by hand. Most of it held up:

- **Worker turn 1, growth and peak match:** 54k, 26k and 155k then, and 54k, 25k and 155k now.
- **Coordinator peak is higher:** 173k rather than 163k, over 35 sessions rather than 31. The ≤ 80k target is unchanged.
- **Cumulative cost was underestimated:** about 2.2M per worker was labelled a floor, and the median is 5.05M. Later turns carry much more than the first.
- **Copilot growth can now be measured:** the comparison had no per-turn figure, and it's about 11k by turn 5.

## After

Measured on 2026-11-03, on the Rust project's migrated branch: five real tasks from its one planned workstream, on Claude Opus 5.5 at medium effort. All five landed, and the branch's tests and lint pass. The last task's replay tally is 71/5/17 rather than the plan's 74/2/17: its worker recorded the three albums that moved and left that for the user to decide.

```bash
ws audit usage --agent claude-code --project <worktree> --transcripts <only the finishing runs>
```

| Role | Sessions | Turns | Turn 1 | Turn 5 | Growth | Peak | Highest | Cumulative |
|---|---|---|---|---|---|---|---|---|
| Worker, last four tasks | 4 | 23 | 14,675 | 65,118 | 50,472 | 119,057 | 183,340 | 1,999,531 |
| Worker, all five | 5 | 25 | 14,682 | 60,634 | 46,023 | 110,358 | 183,340 | 2,177,467 |
| Coordinator | 2 | 16 | 43,872 | 48,310 | 4,437 | 58,305 | 61,233 | 833,882 |

The first task's worker took over from one that had been stopped, so its figures aren't typical, and the first row leaves it out. Two earlier workers that were stopped by the problems below aren't counted either.

**Against the same project before, for a worker:** cumulative context fell 60%, peak fell 23%, turn 1 fell 73% and model calls fell 44%. Context at turn 5 fell 18%.

**Growth went up, and it measures something else now.** It doubled, because workers now read several files in one model call, so turn 5 comes after most of the reading rather than during it. The tool's own part is the step from turn 1 to turn 2, which holds the brief: 4,181 to 4,763 in these four tasks, median 4,718. The rest is the code each task needs.

**The coordinator's peak has a limit to it.** No run held all five tasks: the longest held three, rising 17,448 from its start, about 2,500 of that from reading one brief it didn't need. These runs say nothing about a coordinator holding ten tasks.

**What caused the turn 1 drop is inferred:** the new worker agent has six tools and the old ones had all of them, but the Claude Code version and the model changed as well.

## What the real run found

The evals never hit any of these, because their tasks finish in seconds.

| Found | Result | Now |
|---|---|---|
| A worker put `ws verify` in the background and ended its turn, which killed the check and then the run | Nothing landed, $2.34 | The brief says to wait for it, and `ws adapt` raises the limit on a foreground command |
| A headless run stops background workers 10 minutes after the coordinator's last turn | Nothing landed, $2.42 | `ws adapt` writes the setting that turns this off. Only setting it in the shell is proven |
| The brief called a task's docs "Read first", so a worker loaded about 16,000 tokens of them whole | Context at turn 5 was 107,055, and 83,566 on the same task once fixed | The brief says to search them |
| A project in a linked checkout was reported as a leftover, and `ws unclaim` left the registry behind the queue | `ws doctor` warned, and `ws reconcile` differed | Fixed, with tests |
| `ws adapt` allows none of a project's own commands, so a headless worker can't run its build tools | 24 denied calls across the seven workers | `ws adapt` allows each command in `[commands]`, by subcommand. Others stay denied |
| Claude Code denies edits under `.claude/` even with an allow rule | A trap note couldn't be written by its worker | Stays, as the agent's own protection. `ws brief` warns up front, and someone adds the text |
| Old `commit` fields holding prose, and files a task will create, each warn in `ws validate` | 42 lines from `ws validate` | Down to 3 on the same branch |

**What went right:** when a task needed a contact it hadn't been given, and when a change moved one album's data, the worker stopped and the coordinator asked rather than guessing. Every task landed through `ws settle`.

**Cost:** $14.54 at list price, of the $25 the user set, including the $4.76 on the two stopped runs. The last run's three tasks cost $6.02 together, about $2 each with their share of the coordinator.

## Import on the Kotlin project

Run on 2026-11-03, in a scratch clone with no remote, with no agent and no credits. The clone was deleted afterwards, and only these counts came back. No Copilot "after" figures exist, because no agent ran.

| Check | Result |
|---|---|
| The tree as it stands: 6 closed rows | All convert, and `ws validate`, `ws reconcile` and `ws doctor` pass |
| Queues from history, across every branch | 21 queues and 272 tasks all convert, more than the 17 the comparison counted |
| Those queues at their first version | 271 pending and 1 done |
| Those queues at their last version | 218 done, 51 pending, 2 blocked and 1 in progress |
| A dry run | Changes nothing |
| A second `--write` | Changes nothing |
| A brief for each of the 54 open tasks | All render: median about 1,440 tokens, largest about 2,177, budget 2,500 |

Only each queue file was restored, not its plan, so a real brief would carry more than this. Sizes here are characters ÷ 4.

**What `ws validate` still reports, and it's right to:** verify keys aren't in `[commands]` until someone declares them, as nothing was run. There are 20 distinct keys, reported 847 times on first versions and 271 on last. With those declared, 3 tasks have a kind that needs commands they don't name, and 1 queue is empty.

**One small bug, since fixed:** a done task with no commit gets a marker saying so, and `ws validate` warned that the marker wasn't in the repository.

## Targets

From the plan, for Claude Code on comparable work:

| Measure | Before | Target | After |
|---|---|---|---|
| Worker growth, turn 1 to turn 5 | 25,110 | ≤ 8,000 | 50,472: missed |
| Coordinator peak | 172,724 | ≤ 80,000 | 58,305, highest 61,233: met, on runs of up to three tasks |

[The gate](decisions/0009-pilot-gate.md) replaces the first target and says why.
