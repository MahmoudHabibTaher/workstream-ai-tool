# Gate gaps: plan

## 1. Context

The M6 gate listed four gaps the real pilot found, none of them UI. This closes them before M7.

**Outcome:** a headless worker can run its project's own commands, a worker knows up front what it can't edit, `ws validate` stays readable on an old project, and `ws evidence check` tells the truth about a task that has landed.

**Out of scope:** any UI, the pilot branch's own decisions, and getting past an agent's protection of its own config folder.

## 2. Traps

### T1: core may not name an agent
`tests/test_no_project_literals.py` scans `src/workstream/`. A rule's shape and a protected folder are agent facts, so they go in the adapter TOML.

### T2: never allow a push
The adapter's allow list says so and a test holds it. Rules made from a project's commands must keep to that, including a command that publishes.

### T3: a rule too broad is worse than a denied call
`Bash(make*)` from `make lint` would allow `make deploy`. A rule keeps the command's subcommand.

### T4: the agent's protection stays
Claude Code refuses edits under `.claude/` even with a specific allow rule, retested twice. The tool tells the worker rather than working around it.

## 3. Design

### D-ALLOW: rules from `[commands]`
`ws adapt` adds one rule per command in `[commands]`, using a `command_rule` shape from the adapter. Compound commands give one rule per part. An environment prefix gives both forms, as agents match it literally. A word like `push` or `publish` drops the rule. `ws doctor` reports a rule that's missing. Rejected: allowing whole tools, against T3.

### D-PROTECTED: a line in the brief
The adapter names what a background worker can't edit. `ws brief` names any of a task's files or docs under it, and says to give the exact text under Gotchas instead. Rejected: a validation error, as the task can still run.

### D-QUIET: fewer lines that say nothing
A `commit` warns only if it holds a hash and none resolve, so prose and the import's marker are quiet. More than three missing `files` in one workstream collapse to one line. `ws evidence check` on a done task says it landed rather than re-judging it.

## 4. Tasks

| ID | Title | Blocked by |
|---|---|---|
| GG-01 | Allow a project's own commands | |
| GG-02 | Tell workers what they can't edit | |
| GG-03 | Quiet `ws validate` and fix `ws evidence check` | |
| GG-04 | Docs say what is true | GG-01, GG-02, GG-03 |

All run in the foreground: this session starts no sub-agents unless asked.

## 5. End-to-end verification

`ws adapt` on the pilot branch adds rules for its real commands, and `ws validate` there drops its noise.
