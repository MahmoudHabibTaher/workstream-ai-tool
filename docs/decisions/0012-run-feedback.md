# 0012: Fixes from the first real run

The first real runs of `ws`, on subsonic-server's MBZ-06, surfaced a set of bumps. Each got its own task and its own fresh worker in the `run_feedback` workstream, whose `DECISIONS.md` has the smaller calls. This records what changed, what proved it and what it doesn't prove.

| Task | The issue | The fix |
|---|---|---|
| RF-01 | The gotcha cap cut text anywhere and lost short later entries | Briefs keep whole entries and say `(N more in <path>)` |
| RF-02 | The handoff showed a worker's `P` numbers, not the decision numbers | Parsed gotchas are renumbered too |
| RF-03 | Changing a doc the task names counted as out of scope | Docs a task names are in scope |
| RF-04 | Citations resolved only to headings, and nothing said so early | Table rows resolve, and seed and validate warn |
| RF-05 | A `VAR=x a && b` verify sets the variable only for the first command | Validate warns |
| RF-06 | Settling a blocked task overwrote the planner's notes | A separate `blockedReason` field |
| RF-07 | A worktree read the queue as of its claim | Briefs and task definitions read from the integration checkout |
| RF-08 | The wave hid blocked tasks and offered tasks sharing their files | It lists them and holds those back, and `ws claim --commit` refuses |
| RF-09 | `ws decide` left a commit for the coordinator to make | `ws decide --commit` |
| RF-10 | A decision could never be closed | `ws decide --closes` and `ws decisions --open` |
| RF-11 | Acceptance couldn't be corrected once a decision changed it | `ws update --acceptance`, which needs `--because` |
| RF-12 | Open decisions didn't come up where they matter | Briefs, settle, the handoff and a new stop rule |
| RF-13 | A resumed worker was told to start evidence that already exists | A `## Resuming` section and matching finish steps |
| RF-14 | Nothing checked that a result matched the one asked for | `expect` on an acceptance item |
| RF-16 | RF-15's brief outgrew the shared 2500 budget, failing `make audit` on main | Briefs have their own 4500 budget (D013) |

RF-16 wasn't planned. Each landing adds its gotchas to the briefs of the tasks waiting on it, and RF-15 waits on all of them. **The user chose to raise the budget.** Rejected: capping the section in `brief.py`, which the coordinator and the planning session both recommended and which would stop the growth instead of allowing for it. RF-15's brief ended at 3,831 of 4,500, so the budget now holds this queue and a longer chain could reach it again.

## What proved it

**A replay on a sample repo,** with the installed `ws`, scripted with no agent: an open decision named by settle and shown in the next brief, then closed; acceptance corrected and seen from the worktree; a block that holds back a task sharing its file; a resume to a landing; and an `expect` mismatch stopping settle. Every step behaved as the plan says.

**`make eval AGENT=claude-code`,** on Opus 5.5 at medium effort, with a new `resume` scenario:

| Scenario | Result | Cost |
|---|---|---|
| full | Pass, 87.0s | $0.87 |
| chain | Pass, 21.9s | $0.21 |
| scope | Pass, 22.1s | $0.40 |
| verify | Pass, 19.4s | $0.21 |
| tracking | Pass, 53.1s | $0.37 |
| resume | Pass, 14.0s | $0.18 |
| **Total** | | **$2.24** |

The stub tests show `resume` can fail: discarding the first attempt, requeueing and stopping short are each caught.

## Not proven

- **Copilot.** Its evals weren't run, because they use paid work-account credits.
- **Subsonic-server.** Nothing there changed and MBZ-07 hasn't run on this version, so the original complaints haven't been retested where they arose.
- **A real resume.** In the eval, the harness sets up the block, on a one-file task, so this is one pass on a trivial case. The one real resume in this workstream, RF-10, came before RF-13 landed, and took a merge of main and a hand-written prompt.
- **Open decisions with a real agent.** Stop rule 9 never fired: no worker raised an open decision here, and the replay had no agent in it. The same goes for a real coordinator following the new `ws-run` text after a block.
- **Whether workers obey `## Open decisions`.** The brief shows the section; no scenario tests what a worker does with it.
- **Whether `expect` catches a real mistake.** The replay stops a planted mismatch, and D-EXPECT says it can't stop a worker who changes what a test prints.
- **That the code is what the user wants.** Gates and tests pass, and nobody has reviewed the merges.

## Left open

- `test_the_scratch_repo_is_cleaned_up` fails when another suite runs at once, because it globs the shared `TMPDIR`. Workers got past it with a private `TMPDIR`.
- `verify.code_tree` can give one tree two hashes after a same-size edit in the same second (seen by RF-03).
- A landing can break `make audit` with nothing noticing: settle's post-merge check said `same-tree` for RF-08, and the audit reads tracking files. RF-09 didn't catch it either, as it verifies with `test` alone.
- `ws worktree create` refuses a foreground task, and its brief then says to switch the main checkout's branch. RF-15 and RF-16 used a plain `git worktree add`, and `ws` followed it.
- `ws next` can name a held-back task, `ws decisions` reads the current checkout from a worktree, and `ws show` and the web task screen don't show `blockedReason`.
