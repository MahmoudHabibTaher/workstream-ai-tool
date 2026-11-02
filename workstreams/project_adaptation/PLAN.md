# Project adaptation: plan

## 1. Context

M4 of `docs/plan.md`. Until now a project had to write its own `[commands]`, and `ws init` wrote an empty config. Adopting the tool should be one command that finds out what works by running it.

**Outcome:** `ws init` detects a stack, proposes commands from a profile, runs each on a clean tree, and records what already fails. `ws doctor` says what is wrong with a setup. Small work can use a `lite` tier and releasing work a `full` one.

**Out of scope:** migrating subsonic or the Kotlin harness (M6), installing skills for an agent (M5), config schema files, combining several profiles in one repo.

## 2. Traps

### T1: stack names must stay out of the Python
`tests/test_no_project_literals.py:13` forbids names like cargo and npm in core `.py` and `.md` files, and decision 0002 is why. Node's choice of runner, or whether lint is configured, can't be coded as branches. Profiles must be data with generic conditions; the engine knows no stack. `.toml` isn't scanned, on purpose.

### T2: tests edit the default config's text
`config.py:198` `render_default` output is edited by `tests/helpers.py:101` (`[commands]\n`, `[adequacy]\n`) and many tests (`max_workers = 3`, `merge = "no-ff"`, `mode = "none"`). A profile with nothing to propose must render those tables exactly, or hundreds of tests fail for no reason.

### T3: the project baseline has no reader
`verify.py` `verify_task` calls `baseline.load(project.folder(ws))`, a per-workstream file. A baseline taken at init would be ignored by every task. It needs a fallback that a workstream's own record overrides.

### T4: a command can pass by changing the tree
`verify_task` already refuses a command that rewrites what it checks (`changedTree`). A formatter proposed as lint would do that at init too, and would then never pass a task. Init must compare the code tree before and after, and not write such a command.

### T5: a red command under the exit-code parser can never pass
Decision 0005 left this to M4. `baseline.judge` always fails it, so writing it to config would block every task that names it. It must not become an active key, but silently dropping it hides a broken build. Keep it visible as a commented line with the reason.

### T6: the release rule ignores tiers
`tasks.py` `validate_tasks` requires `releaseImpact` whenever `config.release_mode != "none"`, and `cli.py` `cmd_status` prints the bump on the same test. Tests at `tests/test_tasks.py:465` depend on it. A `full` tier that "adds release" needs this keyed on the tier, or a lite workstream in a releasing project demands a field it can't use.

### T7: doctor must not write
`registry.reconcile` saves when it finds an unknown queue, and `registry.sync` always saves. A health check that changes files would dirty the tree it is judging. Use `validate_all`, which only reads.

### T8: the always-on budget is nearly spent
`ws audit context` reports 142 of 150 for always-on. New skill text goes in bodies, never descriptions.

## 3. Design

### D-PROFILE: profiles are data
`src/workstream/assets/profiles/<name>.toml`: `markers`, and `[[command]]` entries of `key`, `run` and conditions (`if_files`, `if_regex`), plus `[adequacy]`, `[baseline.<key>]` and `[worktree]`. `profiles.py` is the engine: it loads files, picks by markers in a fixed order, and returns candidates per key in order. Rejected: Python per stack, which T1 rules out, and a plugin system, which nothing needs.

### D-INIT: never write a command unverified
For each key, try its candidates in order until one passes, or fails only with findings its parser understands. A tool not on PATH isn't run. Results become active keys or `# key = "..."` comments with the reason. `--no-run` writes everything as comments. Findings go to `.workstream/baseline.json`, which workstream baselines override. Refuses a dirty tree unless `--no-run`. Rejected: asking the user to confirm each command, since running it answers the question.

### D-TIER: three sizes
`lite`: plan, queue and evidence, with a shorter plan template. `standard`: adds decisions, progress and handoff. `full`: adds release, so `releaseImpact` is required and `ws status` and `ws close` report the bump. `ws new --tier full` is refused without a `[release]` runbook.

### D-DOCTOR: a read-only check
`ws doctor` prints gates: Python, git, identity, config, branches, whether the config is committed, whether each command's tool exists, stray adequacy or baseline keys, and registry validity. `--run` also runs commands against the baseline, which is the on-demand form of the start-of-session check removed in decision 0006.

### D-TEST: stubs and real tools
Fixture repos for all six profiles use stub tools on PATH, so CI needs no toolchains. Tests with real cargo, npm and gradle run where installed and skip otherwise. Output samples test each profile's regex.

## 4. Tasks

| Id | Title | Blocked by |
|---|---|---|
| AD-01 | Profiles and config rendering | |
| AD-02 | `ws init` runs and records commands | AD-01 |
| AD-03 | Tiers | AD-02 |
| AD-04 | `ws doctor` | AD-03 |
| AD-05 | End-to-end proof on all six profiles | AD-04 |

All share `cli.py`, so they are a chain, and all run in the foreground because this session has no workers.

## 5. End-to-end verification

AD-05 runs `ws init` on a fixture repo per profile, including one whose lint already fails, then takes one through plan, claim, verify and settle with the fake agent. Real toolchains run where they exist. This workstream itself going from plan to close through `ws` is the first real-agent use.
