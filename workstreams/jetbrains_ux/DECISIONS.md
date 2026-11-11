# Decisions: JetBrains UX redesign

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-10, user): scope approved

The owner (2026-11-10) finds the other workstream plugin's UI better and asked for our UIs to favour it. It is another workstream plugin: ideas only, no code or text.
Master-detail: a list plus Tasks/Graph/Overview detail; Review, Health and Budget stay as their own tabs.
Launch targets: Terminal, Copilot Chat and Air. Air is reached by guarded reflection into non-public classes, falling back to the clipboard; an exception to 0018's no-internal-API rule.
Launch options: agent presets (agent, effort, permissions) that ws maps to flags from the adapter TOMLs, plus pre-flight checks, a task pin and an editable prompt.
Ruled out: porting the other workstream plugin's raw tasks.py commands; any write other than ws act. **Closed.**

## D002 (2026-11-11, JX-02): baseline is `{keys: [...], errors: [...]}`, one entry per key with `exit` and a `findings` count as its result

The plan names "key, result, recorded-at". A recorded key holds an exit code and a list of known findings, so the result is given as those two facts (`exit`, `findings` as a count), not a derived word like "clean", which would be a judgement a UI could also make differently. Each entry also carries `source` (`project` from `ws init`, or `workstream` from `ws baseline record`), `parser`, `command`, and its record's `recordedAt` and `commit`: the two records are stamped at different times, so recorded-at is per key, and the merge follows `baseline.load_for` (the workstream's key wins). A `baseline.json` that can't be read is named in `errors` and the other record still draws, so one broken file can't break `ws snapshot`. A key no record holds is simply absent (no "not recorded" entries); pre-flight can compare against `baseline.keys_to_record`.
Rejected: a single `result` string field; the top-level `recordedAt` of the merged record only (wrong for inherited keys); raising on a broken baseline file. **Closed.**

## D003 (2026-11-11, JX-02): unblocks are direct dependents, waitingOn is unfinished direct blockers

`unblocks` matches what `ws show` prints (tasks naming this one in `blockedBy`, in priority order, whatever their status), not `graph.dependents`' transitive closure. `waitingOn` is `blockedBy` minus done ids, the same test `graph.actionable` and `graph.why_not_actionable` use, so an id naming no task counts as waiting. Both come from `graph.blocked_by_graph`, so ill-typed `blockedBy` gives empty lists. `graph.py` itself is unchanged (it isn't in the task's file list); the reverse edges are built in `snapshot.task_graph_facts`.
Rejected: transitive unblocks; adding a new function to graph.py. **Closed.**

## D004 (2026-11-11, JX-02): scope is the queue's scope with only well-typed fields, or null

`scope` is always present under `-w`: null when the queue has none (or it isn't an object), else `inScope`/`outOfScope`/`rule` as present and well-typed. The schema closes it. Neither `scope` nor `baseline` appears without `-w`.
Rejected: omitting the key when absent (a UI would have to tell "missing" from "old CLI"). **Closed.**

## D005 (2026-11-11, JX-03): `validate` checks this workstream only, through `registry.validate_entry`

The same call `ws validate -w <id>` makes. Another workstream's broken queue doesn't stop a launch on this one; the message gives the first error and points to `ws validate -w <id>` for the rest.
Rejected: `registry.validate_all`, which would let any workstream's error block every launch. **Closed.**

## D006 (2026-11-11, JX-03): the command exits 0 whenever the checks ran; the verdict is in the JSON

`ws launch check` exits 0 even when a blocking check fails, so a UI reads each check's `ok`/`blocking` rather than treating a nonzero exit as "the CLI failed". Exit 1 is kept for what the caller got wrong (unknown workstream, `run-task` without `--task`, `--task` with another kind, a task the queue doesn't hold) and for argparse errors (an unknown `--kind`). The text form ends with `blocked` or `ready to launch`. `launch.blocked(result)` gives the verdict to Python callers.
Rejected: exit 1 on a blocking failure (a UI would have to tell it apart from a real error). **Closed.**

## D007 (2026-11-11, JX-03): only the checks that apply to the kind are listed; `skills` only with `--agent`

`run` gets validate, wave, claim, dirty, baseline; `run-task` gets the same minus wave; coordinate/close/abandon get validate, dirty, baseline. `skills` is added when `--agent` is given. Every check carries `blocking` even when it passes, so a UI can show how each would count.
Rejected: listing every check for every kind with a "not applicable" state (a fourth state the schema and UIs would have to draw). **Closed.**

## D008 (2026-11-11, JX-03): `run-task` is accepted as a kind before its prompt exists

`launch.KINDS` is `snapshot.LAUNCH_PROMPTS`' keys plus `run-task`, de-duplicated, so JX-04 adding the `run-task` prompt changes nothing here. For `run-task` the claim check names the pinned task when it's the one already claimed ("AL-01 is already claimed"); either way it's a warning, as D-PREFLIGHT says.
Rejected: waiting for JX-04's prompt, or a second list of kinds. **Closed.**

## D009 (2026-11-11, JX-03): a check that can't read its input fails, it doesn't raise

An unreadable queue fails wave/claim/baseline with `cannot read the queue: ...` (keeping each check's own blocking), a broken `baseline.json` or adapters manifest fails its check with the read error, and a git failure fails `dirty` (blocking). The other checks still run, as D002 does for the snapshot.
Rejected: raising, which would hide every other check behind one broken file. **Closed.**
