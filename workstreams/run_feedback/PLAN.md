# Run feedback: plan

## 1. Context

The first real runs of `ws` on subsonic-server's MBZ-06 surfaced eight bumps and several rough edges. An assessment confirmed each one against the code, the live MBZ queue or a throwaway repo, and found one more: settling a blocked task overwrites the planner's notes.

**Outcome:** each issue is fixed by its own task, worked by its own fresh background worker, and a final task proves the fixes together with real agents.

**Out of scope:** any change in subsonic-server (its toolchain pin, its MBZ-07 acceptance and contact value follow once this lands, as separate work), Copilot evals, and rewriting past decisions or finished tasks.

## 2. Traps

### T1: `ws` on the PATH is this checkout, not your branch
The `uv tool` install is editable and points at the main checkout's `src/`. So a bare `ws` in a worktree runs main's code, and proves nothing about your branch. Prove a change with tests: `make test TESTS=tests.test_brief` runs part of the suite under `PYTHONPATH=src`, from your worktree. Every merge also changes `ws` for the next worker and the coordinator, so a bad merge can break `ws settle` itself; settle's post-merge check is what guards that.

### T2: `.claude/` holds generated copies
`.claude/skills/*` come from `src/workstream/assets/skills/*`. Edit the assets. A background worker can't edit `.claude/`. The copies go stale as RF-10 to RF-14 land, so the new `ws-run` rules don't reach the coordinator until RF-15 runs `ws adapt claude-code`.

### T3: the docs are executed
`tests/test_protocol.py:15` finds every `ws ...` command in the protocol and skills and parses it with the real parser. A new flag and the docs naming it land in the same task.

### T4: the prompt budgets are close
`make audit` shows always-on at 149 of 150, so leave `POINTER.md` alone. Coordinator per task is 147 of 400 and measures `ws settle`'s output. A task that changes `PROTOCOL.md` or a skill has kind `prompts` and verifies with `audit` too.

### T5: the gotcha cap cuts anywhere
`src/workstream/brief.py:51` slices at 400 characters. On the live MBZ-07 brief that drops the toolchain and contact gotchas, the two that task most needs. Only the first line of a multi-line gotcha is indented. The brief's total is still bound by the worker budget.

### T6: the handoff reads the evidence before it is renumbered
`src/workstream/settle.py:221` rewrites P numbers in the evidence file, but `out["parsed"]` keeps the old text and `src/workstream/handoff.py:62` prints that. So the handoff said "the P1 fix" while the brief said D015.

### T7: empty `files` means "no check"
`out_of_scope` in `src/workstream/gates.py:45` returns nothing when `files` is empty. Simply joining `docs` to `files` would start warning on a task that only lists docs. It is called twice, at `src/workstream/gates.py:111` and `src/workstream/gates.py:135`.

### T8: citations only resolve to headings, and validate has been noisy before
`find_section` in `src/workstream/plan.py:64` reads headings, so `G7`, a table row in an imported plan, is reported missing only when a worker reads its brief. `docs/decisions/0009-pilot-gate.md` records `ws validate` going from 42 lines to 3 after noise on an old project: report one line per workstream, not one per citation.

### T9: not every `VAR=x` prefix is a mistake
`VAR=x cmd` alone is fine, and so is `export VAR=x && a && b`. Only a leading assignment on a command followed by `&&`, `||`, `;` or `|` leaves the rest without it. It is a warning, never an error.

### T10: `notes` is the planner's field
`src/workstream/settle.py:269` overwrites it with the block reason. The handoff (`src/workstream/handoff.py`, its Blocked list) and the web task screen (`src/workstream/assets/web/task.js:33`) show it. `schema/tasks.schema.json` has `additionalProperties: false`, so a new field goes there too.

### T11: a worktree reads the queue as of its claim
That is `src/workstream/worktree.py`'s documented design, and it makes `ws brief` stale from a worktree (reproduced). `_at_task` in `src/workstream/cli.py:559` must still open the worktree for commands and evidence: only the task's definition should come from the integration checkout. Otherwise `ws verify` runs an old `verify` list and `ws settle` reads a new one, and they disagree. `integration_checkout` (`src/workstream/worktree.py:44`) falls back to the current checkout when none is on the integration branch, as with a foreground task on its branch in the main checkout.

### T12: the wave's shape is pinned in several places
`compute_wave` (`src/workstream/graph.py:115` picks its candidates) feeds `schema/snapshot.schema.json:81`, with `additionalProperties: false`, and `src/workstream/assets/web/lanes.js:22`. `tests/test_tasks.py:342` compares the exact dict. `tests/test_tasks.py:348` is the deliberate fall-through past a `blockedBy` and must keep passing. `tests/test_tasks.py:511` asserts no warning across phases, and has to change with `src/workstream/tasks.py:364`. `batch_problems` runs only on `ws claim --commit` (`src/workstream/act.py:220`). `file_overlaps` matches exact strings, not folders or globs.

### T13: `act.commit` can't commit a new file
It uses `git commit --only` (`src/workstream/act.py:148`), which refuses an untracked path. A lite workstream has no `DECISIONS.md` until the first decision: `_record` in `src/workstream/settle.py` runs `git add` for that case. `check_checkout` (`src/workstream/act.py:58`) refuses dirty tracking paths, so restore the bytes on any failure.

### T14: decisions are append-only
The file's own header says "Append, never rewrite", so closing can't edit the old entry. `is_open` (`src/workstream/decisions.py:51`) tests one entry's text, so open-or-closed has to be worked out across the log.

### T15: evidence pairs with acceptance by number
`evidence.problems` (`src/workstream/evidence.py:125`) and `paired_items` match items by position. Replacing an item is safe; inserting or removing one would shift every proof after it. The plan stays immutable, and a done task's record stays as it landed.

### T16: harmless open decisions exist
D014 on the MBZ run stayed open and hurt nothing, so refusing a claim on any open decision would be too strict. `relevant` (`src/workstream/decisions.py:41`) covers direct blockers only, so MBZ-07 doesn't see MBZ-05's D015: open decisions need the whole closure of what a task waits on.

### T17: the resume path lands today but the brief misleads
`tests/test_settle.py:623` proves a blocked task can finish later. But the brief's finish steps tell the worker to run `ws evidence new`, which `cmd_evidence` (`src/workstream/cli.py:652`) refuses when the file exists. `ws unclaim` isn't resuming: it requeues. The branch's own copy of `DECISIONS.md` predates anything decided after the block.

### T18: a check outside the record isn't a gate
`run_problems` (`src/workstream/verify.py`) is what `verification_gates` and `ws settle` read. An `expect` failure must be in that record, or the gates won't see it. `ws verify --key` runs a subset, and acceptance item objects have `additionalProperties: false` in `schema/tasks.schema.json:120`.

## 3. Design

### D-GOTCHA: whole gotchas, and say what was left out
In `_builds_on`, split a blocker's gotchas into top-level bullets and keep whole ones up to 1,200 characters per blocker, indenting every line. If any are left out, end with `(N more in <evidence path>)`. A single entry over the limit is cut at its last sentence end, with the same pointer. Rejected: no cap, since a brief that grows with the project is the cost this tool removes.

### D-IDS: renumber the parsed gotchas too
In `_number_decisions`, apply `evidence.rewrite_ids` to `out["parsed"]["gotchas"]` with the same mapping. Rejected: re-reading the file, which means a second parse of the same text.

### D-DOCS: docs named by the task are in scope
Both gates check `files + docs`, only when `files` is non-empty. The worker's brief already treats a `docs` path as editable (`_cannot_edit_lines`). The `files` and `docs` rows of `ws protocol task-schema` say so. Rejected: moving such paths to `files`, which would mark them as overlaps.

### D-CITE: table rows count, and validate says early
`find_section` falls back to a table row whose first cell starts with the ref as a whole word, returned as a section holding that row. `registry._queue_problems` warns once per workstream, listing refs on open tasks that nothing in `PLAN.md` resolves, and `seed_from_plan` adds the same warning. A missing or placeholder `PLAN.md` is skipped. Rejected: an error, since imported plans carry these.

### D-ENV: warn on a prefix that stops at the first command
`validate_tasks` warns for an open task whose resolved verify command starts with `NAME=value word` and later has `&&`, `||`, `;` or `|`, naming the variable.

### D-REASON: a `blockedReason` field
A new runtime field, default null, in `TASK_FIELD_DEFAULTS`, `FIELD_TYPES`, `RUNTIME_FIELDS` and the schema. Settling a blocked task writes it and leaves `notes` alone; landing and `ws unclaim` clear it. The handoff's Blocked list shows it. `SCHEMA_VERSION` stays 3, because an absent field reads as its default. Rejected: appending to `notes`, because then `notes` has two writers and no clean way to remove the text afterwards.

### D-SOURCE: tracking facts come from the integration checkout
`cmd_brief` opens the project at `worktree.integration_checkout` for everything it reads. `_at_task` keeps returning the worktree's project and takes the task's definition from the integration checkout's queue. Uncommitted tracking there is visible, which is the current truth. Rejected: merging the integration branch into each worktree, which would add commits to the task's diff.

### D-WAVE: blocked is visible, and shared files hold a task back
`compute_wave` removes a candidate sharing a `files` path with an in-progress or blocked task, and reports it as `heldBack: [{id, by, path}]`. If nothing is left the state is `stuck`. `ws wave` lists blocked tasks with their reason beside the leftovers, and held tasks with their cause, and so does `lanes.js`. `batch_problems` refuses the same overlap on a claim. `tasks.py` drops the same-phase condition on its overlap warning, since a wave can move past a phase. Rejected: treating a blocked lower phase as a barrier, which would stop unrelated work; and folder-aware overlaps, kept out to stay small.

### D-COMMIT: `ws decide --commit`
Like `ws claim --commit`: check the checkout, write, commit `DECISIONS.md` as `<id>: <Dnnn>`, restore on failure, and print the short hash. Stage a new file first (T13). Without the flag it behaves as today.

### D-CLOSE: closing is a new entry
`ws decide "..." --why "..." --closes D015,D014` adds a `Closes: D015, D014.` line to the entry. An unknown or already-closed id is refused. `decisions.open_entries` returns entries with the open mark and no later entry closing them. `ws decisions --open` lists them. The `ws-coordinate` skill names both. Rejected: `ws decide` editing the old entry, which breaks append-only.

### D-ACCEPT: replace an item, naming the decision
`ws update <id> --acceptance <n> <text> --because <Dnnn>`: both required, `n` must exist, the decision must exist, and a done or deferred task is refused. It keeps the item's `kind` and appends `(changed by Dnnn)`. `--commit` commits the queue, as in D-COMMIT. `ws-coordinate` names it. Rejected: free editing with no reason, since the plan and the queue would then disagree silently.

### D-OPEN: open decisions come up where they matter
`ws brief` puts any open decision from the closure of the task's blockers right after Acceptance, as id and title with `ws decisions --open`, under a line telling the worker to check its acceptance against them first and report blocked if one changes it. `ws settle` prints `open: Dnnn: title` for each it numbers, naming the tasks waiting on that task, and the handoff lists all open decisions. `ws protocol stop` gains a rule: an open decision with tasks waiting on it goes to the user before those tasks are claimed. Rejected: refusing the claim (T16).

### D-RESUME: the brief knows it is a resume
For a `blocked` task the brief opens with a `## Resuming` section: the reason, the number of commits on the branch, the evidence path, and decisions the branch's `DECISIONS.md` doesn't have. It says to keep finished work, and the finish steps say to update the existing evidence instead of `ws evidence new`. `ws-run` documents the path: once the user answers, start a fresh worker with the same prompt on the same worktree, and never `ws unclaim`. Rejected: a new `ws resume` command, since nothing about the state needs to change.

### D-EXPECT: an acceptance item can name its output
`{"text": "...", "expect": "72/5/16"}`. `verify_task` searches this run's logs, after stripping ANSI, and records any literal not found in the run, so `run_problems` reports it and every gate sees it. A `--key` subset checks only once all keys have results on one tree. `manual` with `expect` is refused. `ws protocol task-schema` and `ws-plan` get one clause each. This doesn't stop a worker who changes what a test prints, only an item whose result differs from what was asked. Rejected: reading the evidence for meaning, which the evidence module rules out.

## 4. Tasks

| ID | Title | Blocked by |
|---|---|---|
| RF-01 | Briefs keep whole gotchas | |
| RF-02 | The handoff uses decision numbers | |
| RF-03 | Docs a task names are in scope | |
| RF-04 | Plan citations resolve, and validate warns early | |
| RF-05 | Validate warns about a verify prefix that stops short | |
| RF-06 | Blocking a task keeps its notes | RF-02, RF-05 |
| RF-07 | Briefs and task definitions read from the integration checkout | RF-01 |
| RF-08 | The wave shows blocked tasks and holds back shared files | RF-05, RF-06, RF-07 |
| RF-09 | `ws decide --commit` | RF-08 |
| RF-10 | Decisions can be closed | RF-09 |
| RF-11 | Acceptance can be corrected, citing a decision | RF-07, RF-10 |
| RF-12 | Open decisions surface in briefs, settle and the stop rules | RF-10, RF-11 |
| RF-13 | Resuming a blocked task | RF-06, RF-07, RF-12 |
| RF-14 | Acceptance items can name expected output | RF-03, RF-11, RF-12 |
| RF-15 | Prove it end to end | all |

One worker per task. RF-01 to RF-05 share no files, so up to `max_workers` run together, as do RF-06 and RF-07, and RF-13 and RF-14. The rest are chained because they share `cli.py`, `tasks.py` or `brief.py`. RF-15 runs in the foreground.

## 5. End-to-end verification

RF-15, on a sample repo through the real CLI with this version installed, replays the MBZ-06 story: a task lands leaving an open decision; settle names it, and the next brief shows it after acceptance; `ws decide --closes` clears it; `ws update --acceptance` corrects the next task, and a brief run from its worktree shows the correction; a worker blocks, the wave lists it and holds back a task sharing its file; a resume brief leads to a landing; and an `expect` mismatch stops settle. Then `make eval AGENT=claude-code` passes, including a new resume scenario.
