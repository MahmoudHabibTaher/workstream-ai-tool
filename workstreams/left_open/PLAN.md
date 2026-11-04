# Left open: plan

## 1. Context

`run_feedback` closed with a list of bugs it found and left alone, under "Left open" in `docs/decisions/0012-run-feedback.md`. Two came from that list's own trouble: a test that fails when suites overlap, and a landing that broke `make audit` with nothing noticing. Each bug here was checked against the code. The `code_tree` one was reproduced, and it turned out worse than the record says (T3).

**Outcome:** each bug is fixed by its own task and its own fresh background worker, and a final task proves them together on a sample repo, with real Claude Code evals.

**Out of scope:** Copilot evals; any change in subsonic-server; rewriting past decisions or finished tasks, so D013's doubled marker stays as it is; changing the 4500 brief budget, which D013 settled.

## 2. Traps

### T1: `ws` on the PATH is the main checkout, not your branch
The `uv tool` install is editable, so a bare `ws` in a worktree runs main's code and proves nothing about your branch. Prove a change with `make test TESTS=tests.test_x`, which runs under `PYTHONPATH=src` from your worktree. `ws verify` still runs the task's commands in your worktree, so its record is good.

### T2: the scratch-repo test is the only one that globs the shared temp folder
`tests/test_evals.py:70` compares `ws-eval-*` in `TMPDIR` before and after a run, so another suite's scenario shows up as a leftover. `evals/harness.py:417` makes the folder with `tempfile.mkdtemp`, with no way to pass a directory. Asserting less (ignoring new folders) would stop the test proving anything. Patch `tempfile.tempdir` to a private folder for the test instead, and show the test can still fail: with `shutil.rmtree` in the harness patched to do nothing, it must see the leftover. Until LO-01 lands, give any parallel verify a private `TMPDIR`.

### T3: `code_tree` can return HEAD's tree for a dirty file
`src/workstream/verify.py:66` uses `shutil.copyfile`, which gives the index copy a new mtime. Git treats an entry as racy, and rereads the file, only if the entry's mtime is not older than the index's. So a same-size edit in the same second as the index entry is trusted as unchanged once the copy is newer.

Reproduced during planning with git 2.56.0: with a dirty same-size file, `copyfile` gave exactly HEAD's tree, `shutil.copy2` gave the right one, and `git status` showed the file modified. So the record's "two hashes" understates it, and **the answer on the gate is yes, it can be fooled:** `ws verify` can run its commands on an edit while recording HEAD's tree. If the edit is then discarded, `verification_gates` (`src/workstream/gates.py:75`) passes on a commit those commands never ran on. `settle_gates` has no dirty check to catch it, though `ready_gates` does. The same stale answer reaches `record_baseline`'s clean-tree check (`src/workstream/verify.py:283`), the `--key` reuse of earlier results, the false "the commands changed the code they checked" RF-03 saw, and settle's `same-tree` (`src/workstream/settle.py:124`). The `rev` path uses `read-tree`, so it is always right.

Timing makes a test flaky, so don't sleep. With `core.trustctime false` in the test repo, `os.utime` can put the file and the real index at one old time, as the planning probe did: it is deterministic.

### T4: a brief's size depends on tracking files, which `code_tree` leaves out
`audit.project_rows` (`src/workstream/audit.py:197`) renders each open task's brief, including its blockers' gotchas, from evidence and the queue. `code_tree` strips those by design, so `same-tree` at `src/workstream/settle.py:124` is right about the code and silent about this. Rerunning verify after a landing wouldn't fix it: that repeats a 4-minute suite, and a task verifying with `test` alone, like RF-09, still wouldn't look. Don't run a command named `audit` either, as `[commands]` belongs to the project (`tests/test_no_project_literals.py`). `audit.role_rows` runs a whole sample workstream and only measures shipped files, so leave it out.

### T5: the growth only exists after the tracking commit
`_record` (`src/workstream/settle.py:253`) writes status and numbers decisions. Measure after it, where `result["open"]` is computed. `cmd_settle` already prints `result["warnings"]` (`src/workstream/cli.py:831`). A dry run lands nothing, so it measures nothing. Coordinator per task is 147 of 400, and it measures settle's output, which a healthy run leaves the same.

### T6: "foreground" has meant two things
`PROTOCOL.md` says foreground is "for what a worktree can't do", yet RF-15 was foreground only because a background agent can't edit `.claude/`, and a worktree served it well. `src/workstream/worktree.py:107` refuses; `src/workstream/brief.py:100` then says `git switch -c` in whatever checkout it is, and `src/workstream/brief.py:188` says `git switch main`, both moving a checkout other sessions share. `tests/test_protocol.py:226` and `tests/test_settle.py:900` pin the old behaviour and must change. `ws settle` refuses from a worktree (`check_checkout`), so landing must name the integration checkout: `worktree.integration_checkout` gives the path, and `--root` exists on every command.

### T7: `graph.actionable` must keep returning held tasks
`src/workstream/cli.py:444` calls it directly, so `ws next` ignores holds. Filtering inside `actionable` would look tidy, but `compute_wave` needs held tasks in it to report `heldBack`, and `claim`'s readiness check at `src/workstream/tasks.py:562` has its own wording for them. Filter in `cmd_next` with `graph.file_holds`. Keep `next`'s rule of lowest priority across phases: don't reuse the wave, which picks a phase first.

### T8: `ws decisions` is one of many `_queue` readers
`src/workstream/cli.py:690` reads through `_queue`, so from a worktree it reads the branch's frozen log. `_tracking` (`src/workstream/cli.py:56`) is the existing answer. Don't touch `cmd_decide`, which writes, or the other readers. D023's full-path pointer in the Resuming section stays right and stays.

### T9: the doubled marker comes from `render_entry`, which three paths share
`src/workstream/decisions.py:86` appends ` **Closed.**` unless the body is open. `ws decide`, settle's numbering and `plan.py`'s scope entry all come through it, and the plan template's own scope line ends in the marker. Fix it there, on the stripped body's ending only: a reason merely quoting the marker mid-text still gets its own.

### T10: the web page has one tested place
`ui/web/tests/logic.test.mjs` is the only place JS runs (D012), and `src/workstream/assets/web/task.js` draws without a test. `_for_display` (`src/workstream/snapshot.py:318`) spreads the task, so `blockedReason` already reaches the page; no server change is needed. Put the choice in `logic.js`, test it there, and draw it from `task.js`. `_print_task` serves `ws next` too, so the new line appears there as well, which is fine. D007 and D010's fallback chain is for one-line lists: `notes` and the title already show on these screens, so show `blockedReason` alone.

### T11: tasks sharing a file must be chained, and phases don't wait by themselves
The wave moves to the next phase as soon as a lower one has nothing actionable, even while its tasks are in progress. So each task's `blockedBy` carries the order, not its phase.

## 3. Design

### D-TMP: the scratch test gets a private temp folder
Change only `tests/test_evals.py`. A helper patches `tempfile.tempdir` to a folder the test owns, which `harness.run_scenario` then uses; the test asserts the folder is empty afterwards. A second test patches the cleanup out and asserts the leftover is seen. Rejected: a `base` parameter on `run_scenario`, as production code changing for a test's sake.

### D-INDEX: the index copy keeps its mtime
`shutil.copy2` at `src/workstream/verify.py:66`, so git's racy check sees what it would see on the real index. Stat-cache speed stays, since only racy entries are reread. Rejected: starting from an empty index, which rehashes every file on every call. Tests in `CodeTreeTests` (`tests/test_verify.py:159`), set up as in T3: the working-tree hash differs from HEAD's; two calls agree; and `ws verify` with a discarded racy edit leaves a record that `verification_gates` refuses. Each must fail with `copyfile` put back, and the evidence says so. The evidence also states the answer on the gate from T3.

### D-BUDGET: settle warns when a landing puts a brief over budget
After `_record` in `settle()`, `audit.project_rows(project, ws)` for this workstream; each row over budget adds a warning such as `brief LO-09 is 4600 of 4500: make audit fails until this is dealt with`. It is a warning because the merge is already committed and the code is sound, and the fix is the user's call, as D013 was. Add stop rule 10 to `## stop` in `PROTOCOL.md`: `ws settle` says a brief is over budget. Rejected: a blocking gate, which would refuse good code over another task's brief; and rerunning verify (T4). Check for an import cycle: `audit` imports `brief`, and its `cli` import is local.

### D-FOREGROUND: every foreground task gets a worktree (the user's choice)
Remove the refusal at `src/workstream/worktree.py:107`, including for tasks with `requires`. `_start_lines` for a foreground task with no worktree says `ws worktree create <task> -w <ws>`; for any task with one it says what it says now. `_finish_lines` step 5 becomes `ws --root <integration checkout> settle <task> -w <ws>`, with the path from `worktree.integration_checkout`. `PROTOCOL.md`'s `mode` row says foreground means a task needing a session to itself, not one without a worktree. `batch_problems` still keeps it alone. Rejected: keeping the refusal for tasks with `requires`, which leaves them switching a shared checkout.

### D-NEXT: `ws next` skips held tasks
In `cmd_next`, drop candidates named by `graph.file_holds`. If that leaves none but some were held, print each held task with what holds it, in `_print_held_and_blocked`'s words, and exit 0 as the empty case does.

### D-MARK: no second marker
`render_entry` adds the ending only when the stripped body doesn't already end with `**Closed.**`. D013 stays as written.

### D-DECISIONS: `ws decisions` reads the integration checkout
`cmd_decisions` uses `_tracking` in place of `_project` and `_queue`, so `--open` and `--for` both see what was decided since the claim.

### D-REASON: `ws show` and the web task screen show the reason
`_print_task` prints `blocked: <reason>` when `blockedReason` is set. `logic.js` gains a small helper for it and `task.js` draws it high on the screen, near the status.

## 4. Tasks

| Id | Title | Blocked by | Notes |
|---|---|---|---|
| LO-01 | The scratch-repo test survives parallel suites | none | Alone first, so later verifies stop tripping on it |
| LO-02 | `code_tree` sees a same-size edit | LO-01 | |
| LO-03 | Settle warns when a brief goes over budget | LO-01 | |
| LO-04 | `ws decide` doesn't double the marker | LO-01 | |
| LO-05 | Foreground tasks get a worktree | LO-03 | Shares `PROTOCOL.md` and `tests/test_settle.py` |
| LO-06 | `ws next` skips held-back tasks | LO-01 | |
| LO-07 | `ws decisions` reads the integration checkout | LO-04, LO-06 | Shares `cli.py` and `tests/test_decisions.py` |
| LO-08 | `ws show` and the web screen show `blockedReason` | LO-07 | Shares `cli.py` |
| LO-09 | Prove it end to end | all | Foreground, by the new route, with evals |

Every task but LO-09 gets one fresh background worker, on Opus 5.5 at medium effort.

## 5. End-to-end verification

LO-09 runs in the foreground through `ws worktree create`, which is itself the first real use of LO-05. It uses the installed `ws`, which is main's code by then, on a sample repo, with output quoted:

1. Two `make test TESTS=tests.test_evals` at once, on the shared `TMPDIR`, both pass.
2. A same-size edit is verified and then discarded, and `ws settle` refuses it. (Set up as in T3.)
3. A landing whose gotchas push a waiting brief over budget: settle warns and names the brief, and `ws audit context` fails.
4. A foreground task, claim to landing, with `git branch --show-current` in the main checkout saying the integration branch at every step.
5. `ws next` skips a held task, and says so when only held tasks remain.
6. `ws decide --why "... **Closed.**"` leaves one marker.
7. From a worktree, `ws decisions` shows an entry recorded on the integration branch after the claim.
8. `ws show` shows a blocked reason, and the web task screen does too, seen in a browser.

Then `make eval AGENT=claude-code`, as the user approved: about $2.24 last time at the default $1 per scenario. Copilot stays out. `docs/decisions/0013-left-open.md` records each fix, the answer on the gate, and what stays unproven.
