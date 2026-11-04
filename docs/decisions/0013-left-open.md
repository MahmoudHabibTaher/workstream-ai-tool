# 0013: The bugs run_feedback left open

`run_feedback` closed with a list of bugs it found and left alone, under "Left open" in `0012-run-feedback.md`. A session in subsonic-server then used the new commands on MBZ-07 and reported five more rough edges (D002). Each got its own task and its own fresh worker in the `left_open` workstream, whose `DECISIONS.md` has the smaller calls. This records what changed, what proved it and what it doesn't prove.

| Task | The bug | The fix |
|---|---|---|
| LO-01 | `test_the_scratch_repo_is_cleaned_up` globbed the shared `TMPDIR`, so another suite's scenario failed it | The test gets a private temp folder, and a second test shows it still sees a leftover |
| LO-02 | `verify.code_tree` could return HEAD's tree for a dirty same-size file | The index copy keeps its mtime (`shutil.copy2`), so git's racy check still fires |
| LO-03 | A landing could put a waiting brief over budget with nothing noticing | Settle measures briefs after the tracking commit and warns, and stop rule 10 covers it |
| LO-04 | `ws decide` doubled the marker when a reason already ended in it | `render_entry` adds the ending only when the stripped body lacks it |
| LO-05 | `ws worktree create` refused a foreground task, and its brief then switched a shared checkout | Every foreground task gets a worktree and lands through `ws --root <integration checkout> settle` |
| LO-06 | `ws next` could name a held-back task | It skips them, and says what holds each when only held tasks remain |
| LO-07 | `ws decisions` in a worktree read the branch's frozen log | It reads the integration checkout |
| LO-08 | `ws show` and the web task screen didn't show `blockedReason` | Both show it, near the status |
| LO-10 | `ws update` couldn't correct a task's summary | `ws update --summary`, which needs `--because` |
| LO-11 | Bare `ws update --commit` worked only with `--acceptance` | It also works with `--verify` and `--notes` |
| LO-12 | Nothing said that a test filter matching nothing still exits 0 | The task schema says to use `expect` on the runner's pass line, and states its two limits. Documentation only: D002 rejected a check |
| LO-13 | The `VAR=x a && b` warning named only `export` | It also offers separate verify entries, and says each must set the variable itself |
| LO-14 | `ws update` always printed the status, whatever it changed | It names what changed, and says when nothing did |

## The answer on the verified-code gate

**Before LO-02, yes, it could be fooled.** `ws verify` could run its commands on an uncommitted same-size edit and record HEAD's tree. If the edit was then discarded, `verification_gates` passed a commit those commands never ran on. The same stale answer reached `record_baseline`'s clean-tree check, the `--key` reuse of earlier results and settle's `same-tree`.

**Now it refuses that case.** In the replay the command saw `after!`, the edit was discarded, and settle said `FAIL the verified code is what would land`. Verifying the committed code let the same settle land. `CodeTreeTests` fail with `copyfile` put back (LO-02's evidence).

`code_tree` is now as good as git's own stat check, and no better. An edit git itself can't see, because the size, mtime and ctime all match and the entry isn't racy, stays invisible. Starting from an empty index would catch it, and the plan rejected that because it rehashes every file on every call.

## What proved it

**A replay on sample repos,** with the installed `ws`, which is main's code with the other 13 tasks landed. A script with no agent gave each step its own repo in a folder whose path has a space:

| Step | What was seen |
|---|---|
| 1. Two `make test TESTS=tests.test_evals` at once, shared `TMPDIR` | Both still running after 2s, then `Ran 19 tests in 44.560s` / `OK` and `Ran 19 tests in 44.445s` / `OK` |
| 2. A same-size edit verified, then discarded | `the command saw: after!`, then `FAIL the verified code is what would land: code changed since`, `NOT settled`, exit 1. After verifying the commit: `done, merged` |
| 3. A landing's gotchas push a waiting brief over | `brief T-2  4378 of 4500  ok`, then `warning: brief T-2 is 4632 of 4500: make audit fails until this is dealt with`, then `FAIL: over budget: brief T-2`, exit 1 |
| 4. A foreground task with `requires`, claim to landing | `main checkout on: trunk` after the claim, worktree create, verify, evidence, commit and landing, using the landing command the brief printed |
| 5. `ws next` with a held task | Named T-3 and not the higher-priority held T-2, then `(no actionable task: every candidate is held back)` and `T-2  shares src/code.txt with T-1`, exit 0 |
| 6. `ws decide --why "... **Closed.**"` | One marker. A reason quoting it mid-text still gets its own ending |
| 7. `ws decisions` from a worktree | The branch's own log has 0 mentions of the entry, and `ws decisions --open` shows it |
| 8. A blocked reason | `ws show`: `blocked: needs the user to name the shared wording; evidence on task/t-1`. The web task screen, seen in a browser, shows `Blocked:` with the same text beside the status, with no console errors |

**LO-10 to LO-14 went beyond their tests.** D002 left them to their own tests, and the plan's end-to-end section doesn't name them. They ran with the real CLI too: a summary corrected with `--because` and refused without it; `--notes` and `--verify` with bare `--commit`; the update line naming what changed, and `nothing changed`; the two-way `VAR=x` warning; and the schema's `expect` wording.

**This task used the new route for real.** LO-09 is foreground with `requires: browser`. It ran in a worktree from `ws worktree create` and landed through `ws --root`, with `main` checked in the main checkout along the way.

**`make eval AGENT=claude-code`,** on Opus 5.5 at medium effort, the harness's defaults, with all 13 other tasks landed:

| Scenario | Result | Cost |
|---|---|---|
| full | Pass, 82.4s | $0.85 |
| chain | Pass, 22.8s | $0.39 |
| scope | Pass, 26.5s | $0.23 |
| verify | Pass, 21.0s | $0.21 |
| tracking | Pass, 57.6s | $0.39 |
| resume | Pass, 19.3s | $0.22 |
| **Total** | | **$2.29** |

## Not proven

- **Copilot.** Its evals weren't run, because they use paid work-account credits.
- **Subsonic-server.** Nothing there changed and MBZ-07 hasn't been rerun on this version, so its five reports haven't been retested where they arose.
- **The racy edit arising naturally.** The replay and the tests build it by setting times, with `core.trustctime false`. Nobody has seen the gate catch one in real work.
- **What a coordinator does with the over-budget warning.** Stop rule 10 never fired in this run, as no landing here went over. Only the planted one warned.
- **A real worker on a foreground task.** The one real foreground run is this task, done by the coordinator. The evals have no foreground scenario.
- **Whether `expect` guidance changes what planners write.** LO-12 is documentation, and D002's limits stand: an expect of a bare test name can match an echoed command.
- **That the code is what the user wants.** Gates and tests pass, and nobody has reviewed the merges.

## Left open

- The `ws-run` skill still says a foreground task should "return to the integration branch, then settle it" (`src/workstream/assets/skills/ws-run/SKILL.md:25` and its `.claude/` copy), which contradicts the brief LO-05 made. `docs/rule-map.md:81` quotes that rule, and `PROTOCOL.md`'s "Don't merge" reads against a foreground brief's landing step. LO-09 followed the brief.
- The `ws-run` skill has no path for a worker that dies mid-task with uncommitted work. Its leftovers step offers landing or requeueing, and its resume step is for a blocked task. LO-08's worker died in a network outage, and a fresh worker on the same worktree, without a new claim, finished it. Nothing but this record says to do that.
- `is_open` matches `**Open.**` anywhere, so a closed reason quoting that mark counts as open. It's the same quoting problem LO-04 fixed for the other mark.
- `ws update <id> --verify <same value> --commit` says `refused: commit failed, tracking files restored: nothing to commit, working tree clean`. Nothing is harmed, but a no-op reads as a failure, where a bare `ws update` says `nothing changed`.
- `--requires` can raise `mode` to foreground, and the `ws update` line doesn't report it.
- The `ws-coordinate` skill names `ws update --acceptance` for a decision that changes a task, and not `--summary`.
- The comment on `EDITED` in `tests/test_gates.py:11` says a same-size edit can look clean to `code_tree`, which is out of date.
- `ws verify` runs about 5 minutes here, and the shell moves it to the background at 180s. The Mac slept through some of LO-10's run: about 1h55m elapsed against 294.7s recorded. A worker judging a hang by elapsed time could kill a healthy run.
