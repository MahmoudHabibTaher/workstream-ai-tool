# Workstream

A tool for running large bodies of work with coding agents: a task graph kept in your repo, executed in clean contexts, verified by commands rather than claims. It works with any project and framework.

**Status:** early development. Core CLI only; skills, adapters and UIs are not built yet.

## Try it

Needs Python 3.11+ and git. No other dependencies.

```bash
PYTHONPATH=src python3 -m workstream --help
```

```bash
make test
```

## Layout

| Path | What it holds |
|---|---|
| `src/workstream/` | The `ws` CLI: state, graph, registry, snapshot, guarded writes, review |
| `schema/` | JSON Schemas for the files and the `snapshot` read model |
| `docs/plan.md` | The build plan and its milestones |
| `docs/harness-comparison.md` | The comparison this tool's design rests on |
| `docs/decisions/` | Decision records |
| `tests/` | Standard-library `unittest` suite |
