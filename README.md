# Workstream

A tool for running large bodies of work with coding agents: a task graph kept in your repo, executed in clean contexts, verified by commands rather than claims. It works with any project and framework.

**Status:** early development. The CLI runs a workstream end to end, and real Claude Code and Copilot CLI agents have each completed a small sample workstream through it. On a real Rust project it landed five tasks with workers carrying 60% less context over a session ([the results](docs/pilot-results.md)). Copilot CLI has only run the sample. Four UIs exist: [a pane for Claude Code](ui/mod/README.md), [a web UI](ui/web/README.md), [a VS Code extension](ui/vscode/README.md) and [a JetBrains plugin](ui/jetbrains/README.md) for IntelliJ IDEA and Android Studio.

## Try it

Needs Python 3.11+ and git. No other dependencies.

```bash
PYTHONPATH=src python3 -m workstream --help
```

```bash
make test
```

`make test-real` also adopts small real projects with whichever toolchains you have installed.

## Set up your agent

`ws` must be on your PATH, for example with `uv tool install .` from this repo. Then, in your project:

```bash
ws adapt claude-code
```

```bash
ws adapt copilot-cli
```

Add `--hook` to deny direct edits to tracking files.

Claude Code ignores a project's `.claude/settings.json` until someone has accepted the trust dialog there, so open the project interactively once before running it headless. Without those rules, background workers are denied the commands they need.

`make eval AGENT=<agent>` runs real agents against a sample repo, under your own login and with a spend cap per scenario. It defaults to Opus 5.5 on medium effort, which took about $0.90 for the full scenario on Claude Code, and 53 Copilot credits when that last ran. All seven scenarios took $2.59 on Claude Code. [Decision 0008](docs/decisions/0008-agent-adapters.md) has the results, and [decision 0014](docs/decisions/0014-loose-ends.md) the latest run.

A project with older workstream files can bring them across with `ws import`, a dry run until you add `--write`.

`ws audit usage` reads your agents' own transcripts and reports what sessions really carried, per role, as numbers only.

[The pane](ui/mod/README.md) shows a project's workstreams beside the chat in Claude Code, through `/workstreams`. `ws root`, `ws snapshot`, `ws review` and `ws act` are what it runs, and what any other UI should.

[The web UI](ui/web/README.md) is the same view in a browser, with review screens first:

```bash
ws serve
```

It needs nothing but `ws`: no Node, no build. It listens on localhost only, and writes only through `ws act`, which refuses a stale write.

[The VS Code extension](ui/vscode/README.md) shows the same facts in VS Code's own trees, Problems panel and diff editor, and starts your agent in a terminal. Install it with `make vsix` and `code --install-extension ui/vscode/workstreams.vsix`.

## How a workstream runs

```bash
ws init
```

That detects the stack, runs its likely commands on your clean tree, and writes to the config only what it saw work. Existing lint findings are recorded so they don't block anyone, and anything broken stays as a comment with the reason. `ws doctor` checks the setup at any time.

```bash
ws new my_work --title "My work" --summary "The outcome." --prefix MW
```

```bash
ws seed --from-plan approved-plan.md
```

```bash
ws baseline record
```

A small job can use `--tier lite`, and one that ships a release `--tier full`. Commit that, then repeat until `ws wave` exits 2. The coordinator runs these:

```bash
ws claim --commit MW-01 MW-02
```

```bash
ws worktree create MW-01 MW-02
```

Each worker is told one thing: run `ws brief MW-01` and follow it. The brief says where to work and how to finish, with `ws verify`, `ws evidence new` and `ws evidence check`. When the workers report:

```bash
ws settle MW-01 MW-02
```

That checks each task's evidence and verification, merges it, re-runs its checks if other work landed first, and numbers proposed decisions. It then updates the queue, progress log, handoff and registry, and cleans up. Close the workstream with `ws close`.

The rules agents follow are in the skills and in `ws protocol`, and `ws audit context` fails if any role grows past its limit. A project's commands, branches and merge style live in `.workstream/config.toml`; [config.py](src/workstream/config.py) documents every key.

## Layout

| Path | What it holds |
|---|---|
| `src/workstream/` | The `ws` CLI: state, graph, registry, verify, brief, settle, worktrees, snapshot, guarded writes, review |
| `src/workstream/assets/` | The protocol and the four skills |
| `src/workstream/assets/web/` | The web UI's files, served as they are |
| `schema/` | JSON Schemas for the files and the `snapshot` read model |
| `docs/plan.md` | The build plan and its milestones |
| `docs/harness-comparison.md` | The comparison this tool's design rests on |
| `docs/rule-map.md` | Where every rule from the source harnesses went |
| `docs/decisions/` | Decision records |
| `ui/` | The UIs' guides, and the Claude Code pane |
| `tests/` | Standard-library `unittest` suite |
