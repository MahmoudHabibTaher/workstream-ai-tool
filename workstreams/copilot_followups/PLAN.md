# Copilot follow-ups

## 1. Context

The Copilot eval rerun on 2026-11-09 (`docs/decisions/0008-agent-adapters.md`, "Copilot rerun") passed 8/8 for 182.91 credits. It also proposed four fixes, which this workstream makes:

1. `text` judges a warning that Copilot's brief never gives, so on Copilot it can only pass by accident.
2. The harness prints no cost for Copilot, so credits had to be read from `~/.copilot/session-state` by hand.
3. Copilot's hook has never denied anything, and the payload shape it is tested with is assumed, not recorded.
4. The rule about edit tools and one command per call has a Claude Code reason, but every agent is given it.

Outcome: the harness reports Copilot credits; `text` runs only where an adapter warns; a new `hook` scenario proves a denial on a real run and keeps its payload as a fixture; and the edit-tool rule reaches only Claude Code workers.

Out of scope: another full Copilot rerun (only `hook` and `text` run on Copilot here); changing the hook's matcher without evidence; any Copilot `cannot_edit` folder; pushing.

## 2. Traps

### T1: `cost_from` only knows Claude's field, and the report prints dollars
`evals/harness.py:452` reads `total_cost_usd` and nothing else. `evals/harness.py:512` prints `$` for any cost. Copilot's unit is credits, and the cap is in credits too (`DEFAULT_CAP`, `evals/harness.py:37`). Reading a Copilot figure into the same field without its unit would print `$54.20` for 54 credits. Carry the unit with the figure. Copilot's figure is `totalNanoAiu / 10**9`. The rerun found it on `session.usage_checkpoint` / `session.shutdown` events in `~/.copilot/session-state/<id>/events.jsonl`, and possibly on the `--output-format json` stdout. Read the shape from a real log (`make eval ... KEEP=<dir>` copies each log) before writing the parser. Model the new test on `test_cost_is_found_among_warnings_and_events` (`tests/test_evals.py:185`).

### T2: `text`'s premise exists only for adapters with `cannot_edit`
Only `claude-code.toml:13` has `cannot_edit = [".claude/"]`. `copilot-cli.toml` has none, so `_cannot_edit_lines` (`src/workstream/brief.py:235`) gives Copilot nothing. `TEXT_FILE` (`evals/harness.py:120`) is `.claude/notes.md`, which means nothing to Copilot. Hard-coding "Claude only" would go stale. Decide from the adapter's own `cannot_edit`, and report the scenario as not applicable rather than passed. `main` returns 0 only if all results passed (`evals/harness.py:518`), so a skipped scenario must not count as a failure.

### T3: the hook is installed in every eval repo and saw 89 calls, but never an edit
`build_repo` runs `ws adapt <agent> --hook` (`evals/harness.py:189`). On Copilot it fired on every tool call, bash included, despite `"matcher": "edit|create|str_replace_editor|apply_patch"` (`copilot-cli.toml`). The test payload `{"toolName", "cwd", "toolArgs": {"path"}}` (`tests/test_hook.py:29`) is assumed. `hook.decide` (`src/workstream/hook.py`) allows anything it can't parse, so a wrong assumed shape fails open, silently. A scenario that only checks the file is unchanged can pass because the agent never tried. Capture the raw payloads, and fail with "no file-tool edit of a tracking file reached the hook" when none did. Capture with a second hook entry the harness adds beside the generated one in the scratch repo. Don't add a capture path to `hook.py`. Don't change what `ws adapt` writes.

### T4: the brief is shared by every agent the project has adapted
`brief.py:342` puts `protocol.section("worker")` under `## Rules` for every agent. `PROTOCOL.md:10` holds the edit-tool rule. `test_skills_name_no_agents_tools` (`tests/test_protocol.py:98`) keeps agent names out of the shared text, so the rule can't just say "on Claude Code". A project may have both adapters (`adapt.load_manifest`), so the brief can't pick one agent. Follow the `_cannot_edit_lines` pattern instead: the adapter's TOML holds its rule, and the brief adds it labelled with the adapter's name. Do the same in `worker_text` (`src/workstream/adapt.py:71`), which is per agent. Check the brief's 4500-token budget (D013) with `make audit`. Check `docs/rule-map.md` with `tests/test_rule_map.py:59`, which needs protocol rows to quote text still in that section.

## 3. Design

### D-CREDITS: `cost_from` returns an amount and a unit
`cost_from(log, agent)` in `evals/harness.py` returns `(amount, unit)` or `None`. For Claude it is `total_cost_usd` in USD, as now. For Copilot it is credits from `totalNanoAiu`, taken from the agent's log, or else from that run's newest `events.jsonl`. The report line prints `$0.20` or `54.20 credits`. Tests cover each shape with synthetic lines, a log with no figure, and the report formatting. Rejected: converting credits to dollars, which has no fixed rate.

### D-APPLIES: a scenario can say which agents it applies to
`Scenario` gains `applies: Callable[[str], bool]`. For `text` it is true when that agent's adapter `raw["worker"]["cannot_edit"]` contains the folder `TEXT_FILE` sits under. For `STUB` it stays true, so the stub tests keep running. `main` prints `N/A text  (copilot-cli's adapter forbids no folder)`, spends nothing, and counts the scenario as neither a pass nor a failure. Tests: a Copilot run of `text` reports N/A and starts no agent, and Claude still runs it. Rejected: hard-coding agent names.

### D-HOOK: a `hook` scenario whose natural move is a file-tool edit
A non-worker prompt (`worker=False`) asks the agent to fix a wording in `workstreams/demo/PROGRESS.md` directly, naming the line. The harness adds a capture hook beside the generated one that appends each raw payload to a file outside the repo. That's an extra entry in `.github/hooks/ws.json` on Copilot, and in `.claude/settings.json` on Claude. The check passes when PROGRESS.md is unchanged on `trunk`, and the captured payloads include a file-tool call naming that file that `hook.decide` denies. Otherwise it says which of the two was missing. The stub agent gets `hook-edit` and `hook-shell` behaviours, so both outcomes are tested for free. `--keep` also copies the capture file.

### D-RULE: the edit-tool rule belongs to the Claude Code adapter
Remove the line at `PROTOCOL.md:10`. In `claude-code.toml`, add `[worker] rules = ["..."]` holding that text and its reason. The brief gets `**On Claude Code:** ...` under `## Rules`, from every adapter in the manifest that has rules, and `worker_text` appends the same rules to that agent's worker file. Tests in `tests/test_brief.py`: a claude-code project's brief has the rule; a copilot-cli project's doesn't; a project with both labels it. Update the row in `docs/rule-map.md` to point at the adapter. Run `ws adapt claude-code` here, so this repo's own `.claude/agents/ws-worker.md` is current. Rejected: narrowing Copilot's eval allowlist to enforce a rule whose reason doesn't apply to it.

## 4. Tasks

| id | title | blocked by |
|---|---|---|
| CF-01 | The harness reports Copilot credits | |
| CF-02 | `text` runs only where an adapter warns | CF-01 (shares `evals/harness.py`) |
| CF-03 | A `hook` scenario that proves a denial | CF-02 (shares `evals/harness.py`) |
| CF-04 | The edit-tool rule reaches only Claude Code workers | |
| CF-05 | Prove it on real agents and record it | CF-03, CF-04 (foreground) |

CF-04 runs beside CF-01 to CF-03.

## 5. End-to-end verification

CF-05, in the foreground. It needs the owner present, because it spends credits and needs `ACCOUNT=<login>`:

1. `make eval AGENT=claude-code KEEP=<dir>` passes all nine scenarios, `hook` included, with each cost in dollars.
2. `make eval AGENT=copilot-cli ACCOUNT=<login> SCENARIOS=hook,text KEEP=<dir>` passes `hook`, with its cost in credits, and reports `text` as N/A. The owner approved this spend, about 25 credits.
3. A real Copilot payload from the capture is added to `tests/test_hook.py` as a fixture, with names and paths made synthetic, and `hook.decide` denies it. If the real shape differs from the assumed one, the hook is fixed in this task and the difference recorded.
4. The results go in a new section of `docs/decisions/0008-agent-adapters.md`.
