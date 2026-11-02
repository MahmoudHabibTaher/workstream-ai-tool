# 0008: How agents get the skills

Decided while building M5. The workstream's own `DECISIONS.md` has the smaller calls.

**Agents are data files.** `src/workstream/assets/adapters/<agent>.toml` holds paths, per-skill notes, the worker's frontmatter and the hook's settings, and `adapt.py` names none of them. Adding an agent means adding a file.

**Generated files are copies, tracked by hash.** There is one copy per repo, not one per workstream, and `.workstream/adapters.json` records each file. `ws adapt --check` exits 1 on anything stale, edited or missing, and `ws doctor` warns. Rejected: one-line skills that call `ws skill <name>`. They can't drift, but they spend a turn on every use and depend on the model following the stub.

**A file we didn't write is refused.** A hand edit, or a skill already at that path, needs `--force`. Text in a shared file goes in a marked block, and settings are merged key by key.

**Always-on now counts what each agent really loads.** That means the block markers and the worker's description too. Counting them went over 150, so each skill description lost a few words instead of the limit being raised. It is at 149 of 150 on both agents.

**Workers don't use an agent's built-in worktree isolation.** One agent's starts from the default branch rather than the claim commit. `ws worktree create` already made the right one, and the generated notes say so.

**The hook is opt-in and fails open.** It needs `ws` on PATH wherever the agent runs, and one agent treats any hook failure as a denial, which would stop all editing. So every failure of its own means "allow", argument errors included. It sees file tools only: a shell redirect gets past it, and `ws settle` catches that.

**Evals judge the repo, not the transcript.** What an agent says it did is the thing being tested. A stub proves the harness can tell good from bad in `make test`, which never starts a real agent.

**Real runs have guards.** A scratch repo holds only synthetic content, every command carries a spend cap and an allowlist, login is checked first, and a Copilot run must name the account it should use. Copilot on the machine this was built on is logged in to a work account, and this project is kept separate from work.

## What real agents found

These are the runs that met the done-when, on Opus 5.5 at medium effort, in scratch repos with synthetic content. Claude Code's cost is its own list-price figure.

| Scenario | Claude Code | Copilot CLI |
|---|---|---|
| `full` | Pass, $0.79 | Pass, 53 credits |
| `chain` | Pass, $0.21 | Pass, 20 credits* |
| `scope` | Pass, $0.23 | Pass, 19 credits* |
| `verify` | Pass, $0.22 | Pass, 19 credits* |
| `tracking` | Pass, $0.37 | Pass, 23 credits* |

\* Before the brief moved to `ws commit`. Those four weren't rerun, to save work-account credits. `full` covers the new brief on Copilot, but not under these pressures.

Earlier runs failed, and each failure changed the tool. None of this showed up in 630 tests with a scripted agent:

- **Invalid YAML dropped three skills and the worker on Copilot, silently.** Their descriptions had a `: ` in them. Claude Code accepted it. A test now checks every generated frontmatter.
- **Background workers on Claude Code couldn't commit.** Their shell returns to the main checkout after each call, and `cd <worktree> && git ...` and `git -C` both need approval they can't ask for. Allowing `git -C *` would also allow a push, so `ws commit` commits on the task's branch from anywhere, and refuses tracking files.
- **`ws verify` and `ws evidence` used whichever checkout the shell was in.** Evidence landed on the integration branch, where it then blocked `ws worktree create`. Both now follow a task to its worktree, and `ws evidence new` refuses on the integration branch.
- **A worker marked its own task done.** Told to, it found `ws update --status done` and used it. The same prompt had passed one run earlier, so this can go either way. `ws update` now refuses a commit that isn't on the integration branch.
- **`ws seed` left `ws reconcile` failing,** so a careful coordinator stopped before starting, and a less careful one on Sonnet ignored it. `seed` and `add` now refresh the registry.
- **A spend cap the agent can see changes what it does.** Copilot said "Given limited credits" and did the workers' jobs itself. Its first call on Opus costs about 15 credits and it refuses a cap below 30, so the default is 80.

The hook refused a real direct edit on Claude Code. Agents in both CLIs picked `ws-run` from its description alone.

Not proven: Copilot's hook has never fired, since no Copilot agent tried a direct edit. Nothing has run interactively, on a real project, from the Claude Code plugin, or with both adapters in one repo, where Copilot may see each skill twice. A Copilot coordinator stopped short of `ws close`, and `full` doesn't require it.
