# Workstream

A tool for running large bodies of work with coding agents: a task graph kept in your repo, executed in clean contexts, verified by commands rather than claims. It works with any project and framework.

**Status:** early development. The CLI runs a workstream end to end, driven by a scripted agent in the tests. Skills, adapters and UIs are not built yet, and no real agent has used it.

## Try it

Needs Python 3.11+ and git. No other dependencies.

```bash
PYTHONPATH=src python3 -m workstream --help
```

```bash
make test
```

## How a workstream runs

```bash
ws init
```

```bash
ws new my_work --title "My work" --summary "The outcome." --prefix MW
```

```bash
ws seed --from-plan approved-plan.md
```

```bash
ws baseline record
```

Commit that, then repeat until `ws wave` exits 2. The coordinator runs these:

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

A project's commands, branches and merge style live in `.workstream/config.toml`; [config.py](src/workstream/config.py) documents every key.

## Layout

| Path | What it holds |
|---|---|
| `src/workstream/` | The `ws` CLI: state, graph, registry, verify, brief, settle, worktrees, snapshot, guarded writes, review |
| `schema/` | JSON Schemas for the files and the `snapshot` read model |
| `docs/plan.md` | The build plan and its milestones |
| `docs/harness-comparison.md` | The comparison this tool's design rests on |
| `docs/decisions/` | Decision records |
| `tests/` | Standard-library `unittest` suite |
