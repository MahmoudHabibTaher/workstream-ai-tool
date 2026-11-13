# 0015: The rough edges the MBZ run found

The agent that ran subsonic-server's MBZ-08 to MBZ-10 reported five rough edges in `ws`. Checking them against the code and the run's records confirmed four, found the fifth partly wrong because `expect` already existed, and turned up two more. The `mbz_feedback` workstream fixed them, one fresh worker per task, and its `DECISIONS.md` has the smaller calls. This records what changed, what proved it and what it doesn't prove.

| Task | The gap | The fix |
|---|---|---|
| MF-01 | The settle warning printed the check's name, `the diff stays within the task's files`, which reads as a pass | The scope gate's detail names the files, and settle prints the detail: `warning: files outside the task's list: b.txt`. The doctor's `warn <name>: <detail>` form stays |
| MF-02 | Text for a file a worker can't edit went under Gotchas, in whatever form the worker chose | Evidence ends with `## Text to apply`, a line of `` ### `path` `` then the text. `evidence.problems` rejects a section with no file, a file with no text, and an absolute or `..` path |
| MF-03 | Nothing tracked that text, so it could be lost | `ws settle` prints `to apply:`, the handoff lists it, and `ws close` warns, until the text is in the file, whitespace collapsed. `ws-run` makes it the coordinator's to apply before the next round |
| MF-04 | One long decision hid every shorter one after it, and an old decision naming the task could be trimmed first | Entries naming the task come first, and one that doesn't fit no longer ends the loop |
| MF-05 | Nothing said which tasks a decision changes, and a second correction erased the first's mark | `ws decide --changes T1,T2`, a warning at either claim path until the task carries a mark, and merged marks: `(changed by D002, D003)` |
| MF-06 | A brief could quote a superseded plan number with nothing saying so | `## Changed since the plan`, listing each settled decision that changes the task, never trimmed |
| MF-07 | Acceptance could name a file `ws settle` writes after evidence must pass | `tasks.tracking_file_warnings`, at `ws validate`, `ws seed`, `ws add` and `ws update --acceptance`. A warning by the user's choice |
| MF-08 | A result that differed from acceptance could pass unremarked, and a correction lost its `expect` | A worker rule: a difference goes under Proposed decisions too. `ws update --acceptance N "text" --expect "literal" --because D` |
| MF-09 | Nothing showed a real agent using the new section | A `text` eval scenario, which passes only if the worker leaves the file alone and the section names it with the line |
| MF-10 | The fixes hadn't been proved together, and the `.claude/` copies were stale | This record |

## What proved it

**A replay on sample repos,** with the installed `ws`, which is main's code with the other nine tasks landed. A script with no agent gave each step its own repo in a folder whose path has a space (`mf10 replay.*/step N`):

### 1. A task touching a file outside its list

```
$ ws settle D-1 -w demo
D-1: warning: files outside the task's list: src/b.txt
D-1: done, merged as 53961ecb9c (after merge: same-tree)
```

### 2. Two tasks leave text for one file, and a third depends only on the second

```
$ ws settle D-1 D-2 -w demo
D-1: done, merged as fb7eabd6a6 (after merge: same-tree)
D-2: done, merged as e81a74864c (after merge: ran)
to apply: D-1: .claude/rules/enrichment.md (evidence/D-1.md)
to apply: D-2: .claude/rules/enrichment.md (evidence/D-2.md)
$ ws close -w demo --dry-run
demo: 3 task(s), closing removes nothing
warning: to apply: D-1: .claude/rules/enrichment.md (evidence/D-1.md)
warning: to apply: D-2: .claude/rules/enrichment.md (evidence/D-2.md)
```

Settling D-3 printed both lines again. The handoff listed both under `**Text to apply:**`. Then both were applied and committed, the first reflowed across two lines, and `ws handoff` was run:

```
$ grep -c 'to apply' session_handoff.md
0
$ ws close -w demo --dry-run
demo: 3 task(s), closing removes nothing
```

### 3. `ws decide --changes` on a todo task

D-1 and D-2 were both changed by D002, with six longer, newer decisions by `user` after it.

```
$ ws claim -w demo --by replay D-1
warning: D-1: D002 changes it, and its summary and acceptance don't say so yet: ws update D-1 --summary "..." --because D002
$ ws brief D-1 -w demo --max-chars 4000
## Changed since the plan
These outrank the plan and the summary where they differ. Read them with `ws decisions --for D-1 -w demo`.
- D002: The count is 700, not 500
## D002 (2026-11-05, coordinator): The count is 700, not 500
Changes: D-1, D-2.
6 more: `ws decisions --for D-1 -w demo`
```

D-1 was corrected and unclaimed, then both were claimed on the `--commit` path:

```
$ ws update D-1 -w demo --summary "Create src/one.txt, counting 700." --because D002
$ ws claim --commit -w demo --by replay D-1 D-2
warning: D-2: D002 changes it, and its summary and acceptance don't say so yet: ws update D-2 --summary "..." --because D002
$ ws show D-1
Create src/one.txt, counting 700. (changed by D002)
```

A second correction, `--because D003`, gave `(changed by D002, D003)`. `ws decide --changes D-9` said `refused: no task D-9 to change`, exit 1.

### 4. An acceptance item naming a tracking file

```
$ ws add -w demo --id D-2 ... --acceptance "DECISIONS.md records the call"
added D-2
warning: D-2: acceptance 1 names DECISIONS.md: `ws settle` writes it after evidence must pass, so the item should ask for the evidence or a proposed decision
$ ws validate -w demo
  - demo: D-2: acceptance 1 names DECISIONS.md: ...
OK: demo, no integrity problems (3 warning(s))
```

Exit 0 from both.

### 5. `ws update --acceptance --expect`

```
$ ws update D-1 -w demo --expect "count 700" --because D002
refused: --expect goes with --acceptance: it pins the item being corrected
$ ws update D-1 -w demo --acceptance 1 "src/one.txt holds count 700" --expect "count 700" --because D002
updated D-1: acceptance 1, D002; commit it
$ ws verify D-1 -w demo      # the file says "ok count 500"
  PASS python3 show.py  0.0s
  PASS test  0.0s
  FAIL acceptance 1: expected output not in the logs: count 700
FAIL: 1 problem(s)
$ ws verify D-1 -w demo      # the file says "ok count 700"
  PASS python3 show.py  0.0s
  PASS test  0.0s
OK
```

**The first tries at this script failed on its own mistakes, not on `ws`.** It named D001 where `ws new` had already taken that number for the scope decision, so D-1 carried the wrong mark and rightly still warned. Step 4's sample had an unfilled plan, so `ws validate` rightly failed on the placeholders. The output above is from the corrected script.

**The refresh.** `ws adapt claude-code` wrote `ws-coordinate`, `ws-plan` and `ws-run`, and left the other four files unchanged. `ws adapt claude-code --check` says `OK`.

**`make eval AGENT=claude-code`,** on Opus 5.5 at medium effort, the harness's defaults, with the other nine tasks landed:

| Scenario | Result | Cost |
|---|---|---|
| full | Pass, 83.9s | $0.88 |
| chain | Pass, 22.7s | $0.39 |
| scope | Pass, 24.0s | $0.22 |
| verify | Pass, 19.0s | $0.21 |
| tracking | Pass, 51.4s | $0.34 |
| resume | Pass, 17.4s | $0.20 |
| leftover | Pass, 29.3s | $0.24 |
| text | Pass, 18.9s | $0.21 |
| **Total** | | **$2.69** |

The plan estimated about $3. Each scenario ran once, so a pass says it can go right, not how often it does.

## Not proven

- **Copilot.** Its evals weren't run, because they use paid work-account credits. `text` is in the default list, and Copilot's adapter has no `cannot_edit`, so a Copilot worker gets no warning and may fairly edit the file and fail (MF-09).
- **Subsonic-server.** Nothing there changed and nothing ran there, so the MBZ run's own cases were reproduced on sample repos, not on its records.
- **A real coordinator acting on `to apply:`.** No worker in this run left text, so no `to apply:` line printed outside the replay, and the new `ws-run` wording hasn't been followed by a real coordinator. This run's coordinator also held the old skill until this task refreshed it.
- **A real background worker refused on `.claude/`.** The `text` eval runs the worker as the top-level `claude -p` in `acceptEdits`, not as a background subagent, and the run's transcript wasn't kept. The pass shows the worker left the file alone and used the section, not that the edit would have been refused.
- **A real coordinator correcting a task after the claim warning.** The replay did it by script. No decision in this run used `--changes`.
- **Workers proposing a difference because of the new rule.** MF-02 and MF-08 proposed their out-of-list change, but neither result differed from an acceptance item, so nothing exercised the rule as written. No mechanical check backs it, by the user's choice.
- **That the code is what the user wants.** Gates and tests pass, and nobody has reviewed the merges.

## Left open

The workstream `tidy_up` closed five of these; [0020](0020-tidy-up.md) records what proved each one. The `###` marker stays as D-TEXT chose it.

- `ws settle MF-01 MF-02` printed MF-02's warning in the old wording, because that process had loaded the code before MF-01 merged. `ws settle MF-08 MF-09` printed the new wording. Only a run that lands the fix itself sees this.
- `test_long_decision_logs_get_trimmed_with_a_pointer` pins a fixed `--max-chars`. MF-02 and MF-08 each had to raise it because a worker rule grew the brief. Deriving the limit from the brief's length would end that (MF-08). Closed by tidy_up TU-01.
- A line of only `###` and a backticked path inside text to apply is read as a new file, so text holding one can't be carried whole. That is the marker D-TEXT and T4 chose (MF-02).
- `handoff.texts_to_apply` calls the private `evidence._text_problem`, and `_with_decisions` the private `decisions._mentions`, because those modules weren't on the tasks' file lists (MF-03, MF-04). Closed by tidy_up TU-02: both are public now.
- The tracking-file warning says `ws settle` writes the file, but `ws baseline record` writes `baseline.json` (MF-07). Closed by tidy_up TU-03.
- `ws-coordinate` still shows the `--acceptance` correction without `--expect`. It stays valid (MF-08). Closed by tidy_up TU-04.
- No test covers a brief with both `## Open decisions` and `## Changed since the plan` (MF-06). Closed by tidy_up TU-05.
