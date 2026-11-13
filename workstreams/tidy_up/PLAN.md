# Tidy up

## 1. Context

Every workstream is closed. Two decision records still list small things that were left open. This workstream closes the ones worth doing:

- **From `docs/decisions/0015-mbz-feedback.md`:**
  - a brief-trimming test pins a fixed `--max-chars`;
  - two modules call private helpers in other modules;
  - the tracking-file warning names `ws settle` as the writer even for `baseline.json`;
  - `ws-coordinate` doesn't show `--expect`;
  - no test covers a brief that has both `## Open decisions` and `## Changed since the plan`.
- **From `docs/decisions/0017-vscode-extension.md`:** D029. The VS Code extension and the JetBrains plugin find a workstream's tasks file by guessing from the order of `watch`. The snapshot should name it in `paths.tasks`.

**Out of scope:**
- D010 (`@types/node`): D034 already accepted and closed it, so nothing is left to do.
- The `###` text-to-apply marker: it stays as mbz_feedback's D-TEXT designed it, by the owner's choice.
- The 0015 note about `ws settle` printing old wording: it happens only in the run that lands the fix.
- Copilot evals, because they use paid work-account credits.
- `ui/web` and `ui/mod`: they read `paths` only through fixed document names.
- Anything in subsonic-server or the Kotlin harness.

## 2. Traps

### T1: the trim test's limit must follow the brief, not a constant
`tests/test_settle.py:957` passes `--max-chars 3400` and asserts the result is under 3500. MF-02 and MF-08 each had to raise that number when a worker rule made the brief longer. Instead, derive the limit:
1. Render the same brief with no `DECISIONS.md` and take its length.
2. Add enough room for a few entries.
3. Assert the trimmed result fits that limit, still ends with the `more:` pointer, keeps `call 39` and drops `call 1`.

`test_trimming_never_cuts_the_task` (`:963`) passes `--max-chars 10` on purpose: leave it alone.

### T2: the private helpers have callers in other modules
- `evidence._text_problem` (`src/workstream/evidence.py:156`) is called at `evidence.py:197` and `handoff.py:76`.
- `decisions._mentions` (`src/workstream/decisions.py:47`) is called at `decisions.py:58` and `brief.py:366-367`.

Rename them to `text_problem` and `mentions`, and update every caller. No test imports either name today, so a leftover call would only fail at runtime: grep `src/` for `_text_problem` and `_mentions`, and expect 0 hits.

### T3: the warning's writer differs per file, and a test pins the old text
`tasks.tracking_file_warnings` (`src/workstream/tasks.py:380`) says "`ws settle` writes it after evidence must pass" for every file. `baseline.json` is written by `ws baseline record`, and the queue by `ws add`, `ws update`, `ws claim` and `ws settle`. `hook.WRITERS` (`src/workstream/hook.py:36`) is "the one list of tracking files", so the writer for each file goes beside it, not in a second list in `tasks.py`.

Tests that pin the wording:
- `TrackingFileWarningTests.WARNING` (`tests/test_tasks.py:1343`) pins the full text;
- `:1407` pins a two-file item: `names DECISIONS.md, PROGRESS.md:`.

Keep one warning per item, and keep the ending "so the item should ask for the evidence or a proposed decision". `tests/test_tasks.py:1421` patches `hook.WRITERS` with a new `NEW.md` and expects a warning. So a file that has no `WRITTEN_BY` entry must fall back to a generic "written by `ws`", not raise a `KeyError`.

### T4: the `.claude` copy of a skill is generated
The skill's source is `src/workstream/assets/skills/ws-coordinate/SKILL.md`. `.claude/skills/ws-coordinate/SKILL.md` is written by `ws adapt claude-code`, and `.workstream/adapters.json` records its hash. Edit only the source. The last task regenerates the copy, and `ws adapt claude-code --check` must say OK.

`test_coordinate_names_both_corrections_a_decision_can_make` (`tests/test_protocol.py:104`) pins the exact `--acceptance` command. Change that test with the skill. The coordinator budget has room: 1778 of 3000.

### T5: the two brief sections are tested apart, with different fixtures
- `## Open decisions` is tested at `tests/test_brief.py:243-251`. It needs an open decision on a task this one waits on.
- `## Changed since the plan` is tested at `:439-468`. It needs a closed decision with `--changes` naming this task.

`render` (`src/workstream/brief.py:338-339`) adds open decisions first, then changes. The new test builds both conditions for one task and asserts:
- both headings appear, in that order;
- each section holds its own entry and not the other's.

Reuse those classes' helpers; don't build a new fixture.

### T6: JetBrains turns every string in `paths` into a document
`Snapshots.view` (`ui/jetbrains/src/main/kotlin/dev/workstream/jetbrains/Snapshots.kt:138-139`) maps every string entry of `paths` into `docs`. `tasksFile` (`:125`) then returns the first `watch` path after the registry that isn't in `docs.values`. If `paths.tasks` appears, the tasks file lands in `docs`, so the guess skips it. Open Tasks would then open the handoff, or nothing. So the snapshot change and the JetBrains reader land in **one task**: main never holds one without the other.

`tasksFile` comes from `paths.tasks`, and the watch guess goes. These tests must still pass:
- `WorkstreamsViewTest.kt:206-212`;
- `WsActionsTest.kt:322`.

### T7: the snapshot's `paths` is a closed schema
`schema/snapshot.schema.json:326-348` sets `additionalProperties: false`. Add `tasks` there, or the schema test (`tests/test_snapshot.py:349`) fails. `_paths` (`src/workstream/snapshot.py:395`) lists a file only if it exists. Do the same for `tasks`: an invalid workstream can lack the file, and `test_paths_name_only_files_that_exist` (`:295`) is the pattern to follow.

### T8: VS Code compares two snapshots to find the file
`tasksFileOf(rootSnapshot, wsSnapshot)` (`ui/vscode/src/logic/health.ts:102`) takes the first path in the workstream's `watch` that isn't in the root's. Its one caller is `ui/vscode/src/views/health.ts:94`. Its test is `ui/vscode/test/logic/health.test.ts:50-53`.

The new reader takes only the workstream snapshot and returns `paths.tasks` when it's a string. Remove the root argument from the caller, and update the comment that describes the old order rule. `WsSnapshot.paths` is already `Record<string, unknown>` (`ui/vscode/src/logic/registry.ts:42`).

## 3. Design

### D-TRIM-TEST: the limit comes from the brief's own length
In `tests/test_settle.py`, measure the brief without the log, then set `--max-chars` to that length plus room for about five of the 39 entries. Assert the result is no longer than the limit. Keep the existing `more:`, `call 39` and `call 1` asserts. Tested by itself under `make test TESTS=tests.test_settle`.
Rejected: a constant with more headroom, which only delays the next raise.

### D-PUBLIC: `evidence.text_problem` and `decisions.mentions`
Drop the leading underscore. Update every caller in `evidence.py`, `handoff.py`, `decisions.py` and `brief.py`. No behaviour changes, so the existing settle, handoff and brief tests are the proof, plus a grep showing 0 private uses.
Rejected: wrapping each one in a new public function, which leaves two names for one thing.

### D-WRITER: each tracking file names its own writer
Add `WRITTEN_BY` beside `WRITERS` in `hook.py`, keyed the same way:

| File | Written by |
|---|---|
| tasks | `ws add`, `ws update`, `ws claim` and `ws settle` |
| baseline | `ws baseline record` |
| `DECISIONS.md` | `ws decide` and `ws settle` |
| `PROGRESS.md` | `ws settle` |
| handoff | `ws settle` and `ws handoff --note` |

A test asserts `WRITTEN_BY` and `WRITERS` have the same keys.

The warning becomes: `X-01: acceptance 1 names baseline.json, written by `ws baseline record`, not the worker, so the item should ask for the evidence or a proposed decision`. When an item names several files, list each with its writer.

Tests in `TrackingFileWarningTests`:
- the handoff case, with its new text;
- a `baseline.json` case naming `ws baseline record`;
- the two-file case.

Rejected: taking the wording from `WRITERS`' sentences, which are written for the hook's deny message.

### D-EXPECT: `ws-coordinate` shows the `--expect` form
In the source skill, the acceptance-correction line shows `--expect "<literal>"` as optional. It says that leaving it out drops the old literal, as `ws protocol task-schema` already says. `tests/test_protocol.py` pins the new command. `make audit` stays within budget.

### D-BOTH: one brief with both sections
Add a test in `tests/test_brief.py` for a task waiting on a task with an open decision, where a closed decision `--changes` it. Both headings appear, `## Open decisions` comes first, and each section holds only its own entry.

### D-PATHS-TASKS: the snapshot names the tasks file, and JetBrains reads it
- `_paths` adds `tasks: str(project.tasks_path(ws))` when that file exists. `_paths` takes what it needs to do this.
- The schema allows `tasks`.
- In JetBrains, `Snapshots.tasksFile(snap)` returns `paths.tasks`, and `view` leaves `tasks` out of `docs`, so documents stay the four `DOC_NAMES`.

Tests:
- `tests/test_snapshot.py` asserts `paths["tasks"]` and that it passes the schema;
- the Kotlin tests cover `tasksFile` reading `paths.tasks` and being null without it;
- `make test-jetbrains` passes.

Rejected: a top-level `tasksFile` key (D029 asked for `paths.tasks`); keeping the watch guess as a fallback.

### D-VSCODE-TASKS: VS Code reads `paths.tasks`
- `tasksFileOf(wsSnapshot)` returns `paths.tasks` when it is a string.
- `views/health.ts` passes only the workstream snapshot.
- `health.test.ts` covers present and absent.
- `make test-vscode` passes, including the integration suite's quick fix that opens the tasks file.

## 4. Tasks

| Id | Title | Blocked by |
|---|---|---|
| TU-01 | The trim test derives its limit from the brief | — |
| TU-02 | Public `text_problem` and `mentions` | — |
| TU-03 | The tracking-file warning names each file's own writer | — |
| TU-04 | `ws-coordinate` shows `--expect` | — |
| TU-05 | A test for a brief with both open decisions and changes | — |
| TU-06 | The snapshot names the tasks file, and JetBrains reads it | — |
| TU-07 | VS Code reads the tasks file from `paths.tasks` | TU-06 |
| TU-08 | End to end: adapt, every suite, evals, the record | TU-01 to TU-07 |

No two of TU-01 to TU-06 share files. TU-08 runs in the foreground: it runs real agents through `make eval` and regenerates `.claude/`.

## 5. End-to-end verification

TU-08 runs on `main` with every other task merged:

1. Run `ws adapt claude-code`, then `ws adapt claude-code --check`, which says OK.
2. Run `make test`, `make audit`, `make test-vscode` and `make test-jetbrains`; all pass.
3. Grep `src/` for `_text_problem` or `_mentions`: 0 hits.
4. On a sample workstream:
   - `ws validate` with an acceptance item naming `baseline.json` prints the new warning, naming `ws baseline record`;
   - `ws snapshot -w <id>` shows `paths.tasks`.
5. Run `make eval AGENT=claude-code` on Opus 5.5 at medium effort, about $3; it passes.
6. Write the results to `docs/decisions/0020-tidy-up.md`, with what stays unproven. The "Left open" sections in 0015 and 0017 then point to it.
