# Agent adapters: plan

## 1. Context

M5 of `docs/plan.md`. The skills exist but no real agent can find them. `ws adapt` generates what each agent reads, from the one source.

**Outcome:** one command installs the skills, a worker agent and an optional guard for Claude Code or Copilot CLI, drift is reported, and an eval harness runs real agents against a sample repo and judges them by what the repo ends up holding.

**Out of scope:** the mod (M7), migrating real repos (M6), other agents, and any handling of an agent's login.

## 2. Traps

### T1: agent names must stay out of the Python and the skills
`tests/test_no_project_literals.py:13` scans every `.py` and `.md` under `src/workstream/`, and forbids agent names. So the engine stays generic and each agent is a data file, as profiles are.

### T2: the always-on budget is nearly spent
`ws audit context` reports 142 of 150. Per-agent notes go in skill bodies, never descriptions, and the coordinator's count must include them, so the audit has to measure per agent.

### T3: a hook can stop all work
Copilot treats a crash or any non-zero exit as a denial, and if `ws` isn't on PATH every matched edit fails. Claude Code blocks only on exit 2. So `ws hook` must exit 0 on its own errors, the hook stays opt-in, and doctor checks `ws` is on PATH.

### T4: hook payloads differ
Claude Code sends `tool_name` and `tool_input.file_path`, and blocks on exit 2 with stderr. Copilot sends `toolName` and `toolArgs`, which may be an object or a JSON string, and denies with JSON on stdout. It also has an `apply_patch` form with paths inside the patch text.

### T5: built-in worktree isolation starts from the wrong commit
Claude Code's `isolation: worktree` branches from the default branch, not the claim commit, and refuses commands outside it. Workers must use what `ws worktree create` made, and the note in `ws-run` must say so.

### T6: a worker agent can't rely on the project's instructions
Copilot subagents skip custom instructions unless told otherwise. Claude Code subagents inherit every tool unless limited, including spawning more. The agent body must stand alone and its tool list must be explicit.

### T7: generated files are copies
Copies drifting is what broke subsonic's per-workstream protocol. One copy per repo is far better than one per workstream, but it still needs a manifest of hashes, `ws adapt --check`, and a doctor warning.

### T8: settings files belong to the user
`.claude/settings.json` holds other people's hooks and rules. Merge only what we add, leave the rest byte-equivalent as data, and refuse rather than overwrite invalid JSON. The pointer goes in a marked block for the same reason.

### T9: a real run is not free, and accounts matter
The login is the user's, and on this machine one CLI is on a work account. The harness must take a spend cap, use a scratch repo with synthetic content only, and run nothing by default. `make test` must never start a real agent.

## 3. Design

### D-ADAPTER: agents are data
`src/workstream/assets/adapters/<agent>.toml` holds paths, per-skill notes, worker frontmatter, the hook's settings and permissions. `adapt.py` is the engine. Rejected: subclasses per agent, which T1 rules out.

### D-MANIFEST: `.workstream/adapters.json`
Records each generated file's hash and the tool version. `ws adapt` refreshes unchanged files, refuses a hand-edited one without `--force`, and `--check` exits 1 on anything stale, edited or missing. Rejected: skills as one-line stubs calling `ws skill <name>`, which never drift but spend a turn on every use and depend on the model following the stub.

### D-HOOK: `ws hook pre-edit --format <agent's format>`
Reads the payload, finds the path, and denies an edit to a tracking file with a reason naming the command to use. A worker's evidence stays writable, and `PLAN.md` is writable until it is filled in. It only sees file tools: a shell redirect gets past it and is caught by `settle`.

### D-EVAL: judge by the repo, not the transcript
`evals/` holds scenarios with a prompt and a check over final repo state. It builds a scratch repo, runs `ws adapt`, starts the agent with a spend cap, and reports. A stub agent proves the harness in `make test`. Real runs are `make eval AGENT=...`.

## 4. Tasks

| Id | Title | Blocked by |
|---|---|---|
| AA-01 | `ws adapt`, manifest and drift check | |
| AA-02 | Worker agent, per-agent notes and audit | AA-01 |
| AA-03 | `ws hook` and its settings | AA-02 |
| AA-04 | Eval harness, proven with a stub agent | AA-03 |
| AA-05 | A real small workstream on each agent | AA-04 |

They share `adapt.py` and `cli.py`, so they are a chain. AA-05 needs the user: logins and a decision about which account runs.

## 5. End-to-end verification

AA-05 runs the full-workstream scenario on each agent: real agent, real sample repo, judged by final state, plus scenarios that tempt it to chain tasks, widen scope, skip verify and edit tracking files.
