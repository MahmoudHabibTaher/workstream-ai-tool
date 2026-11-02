# Pilots: plan

## 1. Context

M6 of `docs/plan.md`, and the decision gate before any UI work. M5 proved agents can finish a toy workstream. This proves, or disproves, that the tool saves context on real work.

**Outcome:** `ws import` brings both older formats onto the tool, `ws audit usage` measures real transcripts, one real project runs a real piece of work on a branch, and a report says whether the targets were met: worker growth from turn 1 to turn 5 falls from about 26k to at most 8k, and coordinator peak falls from about 163k to at most 80k.

**Out of scope:** any UI, merging the pilot branch, adopting the tool in the Kotlin harness's repo, and pushing anywhere.

## 2. Traps

### T1: core may not name a project or an agent
`tests/test_no_project_literals.py:13` scans every `.py` and `.md` under `src/workstream/`. Formats are named by their shape, and where transcripts live goes in the adapter TOML.

### T2: work content must not enter this repo
One of the two harnesses belongs to a work project. Fixtures are synthetic and written by hand. Nothing from that repo's tasks, plans or transcripts is quoted here: only aggregate numbers, as `docs/harness-comparison.md` already does.

### T3: `ws audit usage` reads private transcripts
They hold whole conversations. It prints numbers only, never message text, paths outside the project, or tool arguments, and a test plants a secret in a fixture and checks the output doesn't carry it.

### T4: transcripts count context differently
One agent's usage block is per API message and repeats across content blocks, so count each message id once. A worker lives in a subagent file or a session of its own. The other reports per call in a usage record. Compare within an agent, never across.

### T5: old queues hold finished work
Old done tasks have no verification record and no kind, so running today's checks on them fails. `tasks.py:118` refuses any other schema version, so the import must convert them all, and closed work must stay readable and valid without being re-judged.

### T6: the real checkout has the user's uncommitted files
The real project has untracked files on its integration branch. The migration runs in its own git worktree on its own branch and never switches that checkout.

### T7: spend on real work is the user's call
A real worker on a real codebase costs far more than the sample. Which work runs, on which agent and under what cap is decided by the user, and any further Copilot spend on the work account needs asking again.

## 3. Design

### D-USAGE: `ws audit usage` reads transcripts through two format readers
New `usage.py`. Adapter TOML gains `[transcripts]`, with the root directory and a reader name: `message-lines` or `event-lines`. Each reader yields sessions of per-call context sizes and a role: `worker` for a subagent or a session opened with a `ws brief` prompt, `coordinator` for one that started workers. Reports for each role the count and the medians of turn 1, turn 5, growth, peak and cumulative context, with `--since`, `--until`, `--json` and `--project <path>`. Rejected: copying transcripts anywhere, or a database. Tested with synthetic transcripts in both shapes.

### D-IMPORT: `ws import` converts in place, by shape
New `importer.py`, dry run by default and `--write` to apply. `folder-registry` has `workstreams/workstreams.json`, a queue with `statusValues` and a frozen `AGENTS.md`. `root-registry` has `workstreams.json` at the root, a `<path>/tasks_list.json`, `pending`/`in_progress` statuses, `validation` arrays and a `SESSION_HANDOFF.md`. Both convert to schema v3. Statuses and fields are mapped, closed work is marked so validation leaves it alone, a frozen protocol copy in an open workstream is removed since the CLI now serves it, and running it twice changes nothing. Rejected: teaching `tasks.load` the old versions, which would keep the old shapes alive for good.

### D-REPORT: one results file, updated as measurements arrive
`docs/pilot-results.md` holds before and after numbers and how they were made, and the gate goes in `docs/decisions/0009-pilot-gate.md`.

## 4. Tasks

| ID | Title | Blocked by |
|---|---|---|
| PI-01 | `ws audit usage` | |
| PI-02 | `ws import` for both shapes | |
| PI-03 | Before numbers from real transcripts | PI-01 |
| PI-04 | Migrate the real project on a branch and run a real pilot | PI-01, PI-02, PI-03 |
| PI-05 | Replay on the Kotlin harness's repo in a scratch clone | PI-02, PI-03 |
| PI-06 | Measure, and report the gate | PI-04, PI-05 |

All run in the foreground: this session starts no sub-agents unless asked. PI-04 and PI-05 need the user.

## 5. End-to-end verification

PI-06 runs `ws audit usage` over the pilot's real transcripts and compares it with PI-03, against the targets. If a target is missed, it says so and proposes revised budgets on that evidence.
