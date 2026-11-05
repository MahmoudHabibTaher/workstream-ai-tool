# 0014: The gaps left_open left open

`left_open` closed with eight gaps it found and left alone, under "Left open" in `0013-left-open.md`. Each got its own task and its own fresh worker in the `loose_ends` workstream, whose `DECISIONS.md` has the smaller calls. This records what changed, what proved it and what it doesn't prove.

| Task | The gap | The fix |
|---|---|---|
| LE-01 | `ws-run` told a foreground task to "return to the integration branch, then settle it", and `PROTOCOL.md`'s "Don't merge" read against a foreground brief's landing step | `ws-run` says to follow the brief, landing step included, and that no checkout changes branch. The worker rule names the landing step a foreground brief gives as its one exception, and `docs/rule-map.md:118` agrees. Row 81 stayed true and wasn't changed |
| LE-02 | `ws-run` had no path for a worker that died with uncommitted work | The brief gains `## Picking up`, listing what the worktree holds, capped at 10. `ws-run` step 2 gains the route: gates fail but the worktree holds work, so start a fresh worker on it without a new claim |
| LE-03 | `is_open` matched `**Open.**` anywhere, so a closed reason quoting it counted as open | Only the entry's ending marks it open. The worker rule says to end a proposal with the mark |
| LE-04 | `ws update --verify <same> --commit` read as a failure | `_commit_queue` compares the queue before and after, ignoring `updated`, and says `nothing changed`, exit 0, with HEAD unmoved |
| LE-05 | `--requires` could raise `mode` with nothing saying so | The line reads `updated X-01: requires, which raised mode to foreground` |
| LE-06 | `ws-coordinate` named only `--acceptance` for a decision that changes a task | It also names `ws update --summary` |
| LE-07 | The comment on `EDITED` in `tests/test_gates.py` was out of date | The comment now gives the current reason. No test changed |
| LE-08 | A worker could take a long `ws verify` that the shell moved to the background for a hang | Step 1 of the finish section says to wait for it to exit: it enforces its own limit, and elapsed time can include sleep |
| LE-09 | Nothing could show an agent acting on `## Picking up` | A `leftover` eval scenario: uncommitted partial work, no evidence, the usual prompt. It passes only if that work lands on the branch |
| LE-10 | The fixes hadn't been proved together, and the `.claude/` copies were stale | This record |

## What proved it

**A replay on sample repos,** with the installed `ws`, which is main's code with the other nine tasks landed. A script with no agent gave each step its own repo in a folder whose path has a space:

| Step | What was seen |
|---|---|
| 1. A foreground task, claim to landing | `main checkout on: trunk` after the claim, worktree create, verify, commit and landing, using the landing command the brief printed: `D-1: done, merged as 9dda3f305a (after merge: same-tree)`. `ws protocol worker` and the `ws-run` source read as the brief does, and the source has 0 mentions of the old wording |
| 2. A dead worker: uncommitted edits, no evidence | `ws settle --dry-run`: `FAIL the evidence is complete`, `NOT settled`, exit 1. `ws worktree remove`: `has uncommitted work`, exit 1. The brief's `## Picking up` listed `?? src/extra.txt` and `?? src/one.txt`. Finishing on the same worktree with no new claim: `done, merged as a732a7ecc9`, one claim in the log |
| 3. `ws decide` and the open mark | Quoted mid-text: `This quotes the **Open.** mark mid-text, and goes on. **Closed.**`, and `ws decisions --open` says `(no matching decisions)`. Ending in it: listed as open |
| 4. `ws update --verify <same> --commit` | `D-1: nothing changed`, exit 0, HEAD unmoved, clean tree |
| 5. `ws update --requires browser` | `updated D-1: requires, which raised mode to foreground`. On a task already foreground: `updated D-2: requires` |
| 6. The wording | `ws brief` has `If your shell moves it to the background, wait for it to exit`, and `ws-coordinate` names `--summary` with its arguments |

**This task used the route for real.** LE-10 ran in a worktree from `ws worktree create` and landed through `ws --root`, with `main` checked in the main checkout along the way. The refresh and the evals ran there too. `ws adapt claude-code` wrote `ws-coordinate` and `ws-run`, `--check` says OK, and nothing under `.claude/` says `return to the integration branch`.

**`make eval AGENT=claude-code`,** on Opus 5.5 at medium effort, the harness's defaults, with the other nine tasks landed:

| Scenario | Result | Cost |
|---|---|---|
| full | Pass, 89.9s | $0.92 |
| chain | Pass, 22.9s | $0.22 |
| scope | Pass, 24.6s | $0.41 |
| verify | Pass, 21.1s | $0.22 |
| tracking | Pass, 54.5s | $0.39 |
| resume | Pass, 14.2s | $0.18 |
| leftover | Pass, 27.3s | $0.25 |
| **Total** | | **$2.59** |

The plan estimated about $2.50. Each scenario ran once, so a pass says it can go right, not how often it does.

## Not proven

- **Copilot.** Its evals weren't run, because they use paid work-account credits.
- **Subsonic-server.** Nothing there changed. Its decision logs weren't read, so an entry there with text after `**Open.**` now reads as closed, unchecked (T6).
- **A real worker on a foreground task.** The one real foreground run is this task, done by the coordinator. The evals have no foreground scenario, which stays out of scope.
- **A real coordinator taking the dead-worker route.** `leftover` starts at the worker. The `ws-run` step that sends one there wasn't exercised: no worker died in this run.
- **A real worker waiting out a backgrounded verify because of the new sentence.** LE-08's own runs moved to the background at 180s and ran to their own exit, at 331.7s and 356.7s, but that worker was writing the sentence.
- **That the code is what the user wants.** Gates and tests pass, and nobody has reviewed the merges.

## Left open

- A `---` line after an open entry now closes it, since `decisions.parse` keeps everything up to the next heading and only the ending counts. `ws decide` writes no separators, and each tracked log has only its header's one, so only a hand-edited log can reach this (LE-03).
- `tasks.save` also sorts by priority and restamps `schemaVersion`, so a same-value `--commit` on a queue not already in that form commits the normalisation rather than saying `nothing changed`. The CLI's own writes can't produce that queue (LE-04).
- `test_each_field_given_is_named` expects a plain `updated X-01: requires`, and passes only because an earlier subtest has made the task foreground (LE-05).
- `test_long_decision_logs_get_trimmed_with_a_pointer` pins a limit close to the brief's fixed text. D007 raised it to 3100, and at most 100 characters are spare, so another brief addition can break it (LE-08).
- `_landed_problems` in `evals/harness.py` prints a blank reason for a task that isn't settleable, since settle says why on stderr and only stdout is read. It still fails correctly (LE-09).
