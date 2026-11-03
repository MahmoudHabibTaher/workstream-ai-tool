# Workstreams pane

A Claude Code mod that shows a project's workstreams in a pane beside the chat: the registry, each queue by phase and wave, the narrative files, a health panel and per-task review. It sits on `ws snapshot`, `ws act` and `ws review`, which own every fact it draws and every write it makes.

## Install

It needs `ws` on the PATH and Claude Code 2.1.309 or newer, as the mod API is early access. The tool's repo root is a folder marketplace, so from there:

```bash
uv tool install --editable .
```

```bash
claude plugin marketplace add "$PWD"
```

```bash
claude plugin install workstreams-pane@workstream --scope user
```

Then run `/reload-plugins` in a running session, or start a new one. The entry is a relative path, so the plugin is read from this folder as it stands: on a branch without this folder, the pane doesn't load.

## Use

`/workstreams` opens the pane for the project the session runs in, at the checkout holding its integration branch, as `ws root` reports it. A session in a task's worktree still sees the live queue. `/workstreams <path>` points it at another project. In a folder that isn't a project, or with no `ws` to run, the command says so and opens nothing.

**Registry.** Open workstreams with their status, `done/total` and `dependsOn`, and a red count of health errors. **Show done** adds the closed ones, and **Refresh** reads the snapshot again. Pressing a row opens its detail.

**Detail.** The wave line, then tasks grouped by phase in priority order, with their badges: `★ ready`, `FG`, `needs decision`, `waits on X` and `claimed <age>`. Pressing a task expands its summary, acceptance list, verify commands, files, notes and requires.

Detail also has **Run**, **Coordinate**, **Close…** and **Abandon…**, which only fill the prompt box: nothing is sent until you press Enter. **Pause** or **Resume** shows for a status that allows it, and a task's **Unclaim** only when a health finding offers it.

**Health.** The workstream's findings by level, and those about the whole checkout, with the actions each one lists. **Sync** shows when the registry's progress is out of date.

**Review.** A task's evidence, its diff range and its diffstat as file buttons. Pressing a file draws its diff in the evidence's place, cut at a hunk boundary and marked when it runs over the cap. **Evidence** goes back.

**Writes.** Pause, Resume, Unclaim and Sync first ask, naming the commit and the integration branch. Confirm runs `ws act` with the hashes of what the pane drew, and `ws act` alone decides. A refusal, say on a dirty tracking path or a stale view, shows in red and nothing is committed.

**Feed.** Handoff, Progress, Decisions and Plan as Markdown, about 120 lines a page. Decisions opens on its last page.

While the pane is open it checks the mtimes of the files the snapshot lists under `watch` every 3 seconds, and reads the snapshot again when one changes.

## Checks

`make test-mod` runs `claude plugin validate` and `claude plugin test`, with `ws` stubbed. It needs the `claude` CLI, so it's local, like `make eval`. `tests/test_mod_files.py` runs in `make test`: it holds that the mod names no project, and that the real `ws` answers the commands the mod sends.

The rules for changing it are in [the decision](../../docs/decisions/0010-claude-pane.md).
