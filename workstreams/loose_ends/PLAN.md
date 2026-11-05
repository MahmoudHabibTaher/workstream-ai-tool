# Loose ends: plan

## 1. Context

`left_open` closed with a list of gaps it found and left alone, under "Left open" in `docs/decisions/0013-left-open.md`. Each was checked against the code during planning, and the CLI ones were reproduced on a sample repo. All eight hold, with one part dropped: `docs/rule-map.md:81` needs no change (T3).

**Outcome:** each gap is closed by its own task and its own fresh worker, and a final foreground task proves them together on a sample repo, with real Claude Code evals and the `.claude/` copies refreshed.

**Out of scope:** Copilot evals, which use paid work-account credits; any change in subsonic-server or the Kotlin harness; reversing a closed decision, including the 4500 brief budget and LO-14's D013; a foreground eval scenario, which `0013` lists under "Not proven" and not under "Left open".

## 2. Traps

### T1: `ws` on the PATH is the main checkout, not your branch
The install is editable, so a bare `ws` in a worktree runs main's code and proves nothing about your branch. Prove a change with `make test TESTS=tests.test_x`, which runs under `PYTHONPATH=src` from your worktree. `ws verify` still runs the task's commands in your worktree, so its record is good.

### T2: the `.claude/` skills are generated, and a background worker can't edit them
`ws adapt claude-code` writes them from `src/workstream/assets/skills/`, and `.workstream/adapters.json` holds their hashes, so a hand edit reads as `edited` (`tests/test_adapt.py:103`). `src/workstream/assets/adapters/claude-code.toml:13` lists `.claude/` under `cannot_edit`. So skill tasks change only the source, and `make test` doesn't need the copies current. LE-10 refreshes them last. Until then a coordinator running this workstream reads the old line 25: on LE-10, the brief wins, as it did for LO-09. Don't change a skill's `description`: always-on on claude-code is 149 of 150.

### T3: the rule map's quotes are tested, and row 81 is still true
`tests/test_rule_map.py:49` checks each skill and protocol row's quote is in that text. `docs/rule-map.md:81` quotes only `Foreground tasks`, and its rule says "the main session", which stays true: the session is the same, working in a worktree. So keep the literals `Foreground tasks`, `Leftovers first` and `Don't merge`. The row that does read against a foreground brief is `docs/rule-map.md:118`.

### T4: the worker rules go into every brief
`src/workstream/brief.py:287` puts `protocol.section("worker")` in background and foreground briefs alike. An exception to `Don't merge` that isn't tied to foreground tells background workers they may land. `ws settle` refuses from a worktree without `--root`, and step 5 of a foreground brief (`src/workstream/brief.py:197`) is the only place that names it.

### T5: the resume path doesn't fit a dead worker
`src/workstream/brief.py:256` enters `_resume_lines` only for `blocked`, and a dead worker's task is `in-progress`. Its words are wrong here too: "Keep the finished work: don't redo or re-check it" suits committed work its author reported, not uncommitted edits nobody checked. So this needs its own section, and the finish step must still use `_resume_evidence`, because `ws evidence new` refuses a file that exists. A fresh claim has a clean worktree and must print nothing new. A live worker that re-runs `ws brief` sees its own edits, so the wording must allow for that. `ws worktree remove` already refuses uncommitted work (`src/workstream/worktree.py:169`). `audit.project_rows` renders these briefs, so cap the file list.

### T6: `is_open` has three callers, and the fix can close something silently
`src/workstream/decisions.py:57` serves `open_entries` (`:68`), `render_entry` (`:91`) and `evidence.problems` (`src/workstream/evidence.py:149`). Today `ws decide --why "the **Open.** mark is quoted"` writes no ending and lists as open (reproduced). Matching the stripped text's ending fixes that, as LO-04 did for the other mark. The cost: `**Open.** Rejected: x`, with text after the mark, now closes. None of this repo's eight logs has any `**Open.**` entry, so no recorded answer changes here. Subsonic-server's logs weren't read.

### T7: a no-op isn't always a clean tree
`src/workstream/tasks.py:522` stamps `updated` on every write, so the same `--verify` on a later day changes the file and commits a date. Catching the "nothing to commit" refusal or comparing bytes misses that day-later case. `act.commit` (`src/workstream/act.py:148`) has other callers, so leave its refusal alone. The same failure is reachable from `_correct` with the same text and decision, since both go through `_commit_queue` (`src/workstream/cli.py:319`).

### T8: the mode raise happens out of `cmd_update`'s sight
`src/workstream/tasks.py:509` raises `mode` inside `tasks.update`, and `src/workstream/cli.py:422` prints only what was given. Report a real change only: a task already foreground, or `--mode` given as well, must say nothing new. Bare `--commit` refuses `--requires`, so `_commit_verify_or_notes` is unaffected. D013 says only status and commit print a value; the raise is a consequence nobody gave, so it gets words of its own rather than `mode=foreground`.

### T9: every backticked `ws` command in a skill must parse
`tests/test_protocol.py:66` parses them, and D007 hit it: `--summary` must appear with its arguments, as a whole command.

### T10: `ws` can't stop the shell backgrounding a long verify
LO-11 and LO-13 saw it at 180s even with `BASH_MAX_TIMEOUT_MS` at 3600000 in `.claude/settings.json`, so more configuration won't fix it. `run_command` (`src/workstream/verify.py:88`) already enforces its own limit (`verify_timeout`, 3600s, `src/workstream/config.py:79`) on `time.monotonic`, which is why LO-10 recorded 294.7s across 1h55m of sleep. So a worker never needs to judge a hang. Name no OS tool or agent in core: `tests/test_no_project_literals.py`.

### T11: tasks sharing a file must be chained
The wave moves on as soon as a lower phase has nothing actionable, even with tasks in progress. So `blockedBy` carries the order, not the phase.

## 3. Design

### D-FOREGROUND: the skill and the protocol say what the brief says
`ws-run` line 25 becomes: run in this session, one at a time, after the batch; claim it alone and follow its brief yourself, landing step included; no checkout changes branch. `PROTOCOL.md`'s worker rule keeps `Don't merge, and don't switch to the integration branch` and adds that the one exception is the landing step a foreground brief gives, which names the integration checkout and switches nothing. `docs/rule-map.md:118` says the same in a few words. Tests in `tests/test_protocol.py`, beside `test_the_schema_does_not_say_foreground_means_no_worktree`: `ws-run` no longer says to return to the integration branch, and the worker section ties the exception to foreground. Rejected: dropping the rule from foreground briefs, which makes the rules section differ by mode for one line.

### D-LEFTOVER: the brief tells a fresh worker what it found
`_pickup_lines` in `src/workstream/brief.py`: for an `in-progress` task whose worktree has uncommitted files (`worktree.uncommitted`) or commits since `baseCommit`, a `## Picking up` section lists them, capped at 10 with `(N more)`. It says that unless these are your own edits, an earlier worker stopped here, so check them against the acceptance items and keep what is right. `existing_evidence` also comes from `_resume_evidence` here. `ws-run` step 2 gains the middle route: gates fail but the worktree holds work, so start a fresh worker with the usual prompt on the same worktree, and don't claim again. Requeueing stays for a worktree with nothing to keep. Step 4's "treat it as blocked" points to step 2 instead. Tests in `tests/test_brief.py`, using `ResumeTests`' helpers (`:214`): uncommitted edits are listed; commits are counted; a fresh claim prints no section; existing evidence changes the finish step. Rejected: the skill alone, with extra lines in the worker's prompt as D016 did, because a prompt is unchecked text and the whole prompt is meant to be `ws brief`; and reusing `## Resuming` (T5).

### D-OPENMARK: only the ending marks an entry open
`is_open` becomes `text.rstrip().endswith(OPEN_MARK)`. `PROTOCOL.md`'s worker rule says to end the proposal with the mark. Tests in `tests/test_decisions.py`: a body quoting the mark mid-text renders with the closed ending and isn't in `open_entries`; one ending in it stays open, with or without trailing whitespace; a proposal quoting it mid-text with no `Rejected:` is now reported by `evidence.problems`. Rejected: last mark wins, which leaves `ws decide --why "quoting **Open.**"` open; and skipping backticked marks, since the log quotes in other ways too.

### D-NOOP: `_commit_queue` notices nothing changed
After `change()`, `_commit_queue` compares the queue before and after, ignoring `updated`. If they match, it restores the bytes and returns None, and both callers print `<id>: nothing changed` and exit 0, as a bare `ws update` does. HEAD doesn't move. Tests in `tests/test_tasks.py`: the same `--verify`, the same `--notes`, a queue dated earlier (T7), and the `--summary` path; a real change still commits. A plain update without `--commit` keeps LO-14's line. Rejected: catching the commit refusal (T7).

### D-RAISED: the update line reports a raised mode
`cmd_update` compares the task's mode before and after and adds it to the line: `updated X-01: requires, which raised mode to foreground`. Tests in `tests/test_tasks.py`, near `:486` and `:1192`: a forcing value says so; a task already foreground, a value that forces nothing, and an explicit `--mode` don't. Rejected: changing `tasks.update`'s return, which has other callers.

### D-SUMMARY: `ws-coordinate` names both corrections
Its "changes what a task must prove" line also names `ws update <task> --summary "<text>" --because <Dnnn> --commit -w <id>`, for a decision that changes what a task must do. A test in `tests/test_protocol.py` asserts it, and T9's test parses it.

### D-COMMENT: the comment states the current reason
`tests/test_gates.py:11`'s value stays and its comment goes or changes: since LO-02 `code_tree` is as good as git's stat check, so a same-size edit no longer looks clean in these tests. No test changes.

### D-WAIT: the brief says a long verify isn't a hang
Step 1 of `_finish_lines` (`src/workstream/brief.py:187`) adds: if your shell moves it to the background, wait for it to exit; it enforces its own time limit, and elapsed time can include the machine sleeping, so don't kill it. A test in `tests/test_brief.py` asserts the sentence, and `make audit` must still pass. Rejected: progress output or a heartbeat, which wouldn't stop a shell backgrounding it and adds output to a command built to stay short (T10).

### D-EVAL: a scenario for the dead worker
`evals/harness.py` gains `leftover`, modelled on `resume` (`:320`): setup leaves uncommitted partial work in the claimed worktree with no evidence, the prompt is `WORKER_PROMPT`, and the check is that the partial work survives and settle would land it. `evals/stub_agent.py` gets good and bad behaviours, and `tests/test_evals.py:30` covers the checks with the stub, spending nothing. This is the only way to see an agent act on `## Picking up` from the brief alone.

## 4. Tasks

| Id | Title | Blocked by | Notes |
|---|---|---|---|
| LE-01 | `ws-run` and the protocol agree with a foreground brief | | Shares `ws-run` with LE-02, `PROTOCOL.md` with LE-03, `tests/test_protocol.py` with LE-06 |
| LE-04 | `--commit` with an unchanged value isn't a failure | | Shares `cli.py` and `tests/test_tasks.py` with LE-05 |
| LE-07 | Correct the comment in `tests/test_gates.py` | | |
| LE-02 | A fresh worker can pick up a dead worker's worktree | LE-01 | Shares `brief.py` and `tests/test_brief.py` with LE-08 |
| LE-03 | `is_open` reads only an entry's ending | LE-01 | |
| LE-05 | `ws update` reports a mode that `--requires` raised | LE-04 | |
| LE-06 | `ws-coordinate` names `--summary` | LE-01 | |
| LE-08 | The brief says a long verify isn't a hang | LE-02 | |
| LE-09 | An eval for a dead worker's worktree | LE-02 | Stub only: no spend |
| LE-10 | Prove it end to end | all | Foreground, for `.claude/` |

## 5. End-to-end verification

LE-10 runs in the foreground, in a worktree, and lands through the brief's `--root` step. On sample repos, with the installed `ws`, which is main with the other nine landed:

1. A foreground task from claim to landing, with the main checkout's branch checked along the way. `ws protocol worker` and the `ws-run` skill read the same as the brief.
2. A dead worker: uncommitted edits and no evidence. `ws settle --dry-run` refuses, `ws worktree remove` refuses, `ws brief` lists the files, and finishing on the same worktree without a new claim lands them.
3. `ws decide --why` quoting `**Open.**` mid-text gets the closed ending and `ws decisions --open` doesn't list it. One ending in the mark is listed.
4. `ws update --verify <same> --commit` says `nothing changed`, exits 0, and HEAD doesn't move.
5. `ws update --requires <forcing value>` names the raise.
6. `ws brief` has the long-verify sentence, and `ws-coordinate` names `--summary`.

Then `ws adapt claude-code`, with `--check` saying OK and no `return to the integration branch` left under `.claude/`; and `make eval AGENT=claude-code` on Opus 5.5 at medium effort, all seven scenarios, with the cost recorded. Copilot stays out. `docs/decisions/0014-loose-ends.md` records each fix, what proved it and what stays unproven, and the README's eval line is brought up to date.
