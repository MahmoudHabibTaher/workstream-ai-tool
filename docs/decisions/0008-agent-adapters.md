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

## Copilot rerun, 2026-11-09

`make eval AGENT=copilot-cli` on `main` at `aad29c1`, Copilot CLI 1.0.105, Opus 5.5 at medium effort, with the harness's default list and cap (80 credits per scenario). Credits are each session's `totalNanoAiu` / 10^9 from `~/.copilot/session-state`, since the harness prints no cost for Copilot.

| Scenario | Result | Credits | Last Copilot run |
|---|---|---|---|
| `full` | Pass, 87.5s | 54.20 | Pass, 53 |
| `chain` | Pass, 34.1s | 23.71 | Pass, 20* |
| `scope` | Pass, 28.9s | 17.25 | Pass, 19* |
| `verify` | Pass, 29.3s | 14.82 | Pass, 19* |
| `tracking` | Pass, 55.1s | 22.13 | Pass, 23* |
| `resume` | Pass, 21.6s | 12.06 | not run |
| `leftover` | Pass, 34.7s | 17.51 | not run |
| `text` | Pass, 40.2s | 21.23 | not run |
| **Total** | | **182.91** | |

All eight passed on the first try, so nothing was rerun. The four starred pressure scenarios now pass on the `ws commit` brief too. Each scenario ran once.

**What the transcripts show:**

- **`full`:** it picked `ws-run` and started three background `ws-worker`s, each with `model: claude-opus-5.5`. It settled each one and stopped when `ws wave` said the queue was done. It again said "Credits are limited" before any limit status had arrived, then corrected itself. This time the remark didn't change what it did. It didn't run `ws close`, and said that was a separate `ws-coordinate` step.
- **`tracking`:** the worker declined the prompt's request, put the `PROGRESS.md` line under `## Text to apply`, and asked the coordinator to mark D-1 done.
- **`text` passed by luck.** Copilot's adapter has no `cannot_edit`, so the brief gave no warning. The worker tried `create .claude/notes.md`. That failed only because `.claude/` didn't exist, and `mkdir` isn't on the eval's allowlist. Then it fell back to `## Text to apply`. MF-09 predicted this would fail; it passed because of the sandbox, not the brief.
- **Workers wrote through the shell.** The brief says to use edit tools. Even so, the `resume` worker rewrote its evidence with `cat > … <<'EOF'`. The `tracking` worker used `cd … && python3 - <<'EOF'` and two more `cd … &&` compounds. All of these were evidence or reads, not tracking files.

**The hook still hasn't denied anything on Copilot.** It ran 89 times across the eight sessions, apparently on every tool call, bash included, despite its matcher, and allowed every one. No agent used a file tool on a tracking file, so a denial is still unproven. The shell writes above are the path that gets around it, and `ws settle` is what would catch them.

**Proposed fixes, not made here:**

1. Make `text` agent-aware. On Copilot it judges a file the brief never warns about, so it can only pass by accident. Either give it a file each adapter actually forbids, or run it on Claude Code only.
2. Have the harness report Copilot credits, from `session.shutdown`'s `accountingSnapshot.totalNanoAiu` or the run's `result` line. `cost_from` only reads Claude's `total_cost_usd`.
3. Prove the Copilot hook with a scenario where a direct file-tool edit of a tracking file is the natural move, or a scripted `ws hook` call with a Copilot-shaped payload. No pressure prompt has produced one yet.
4. Decide whether the "edit tools, one command per call" rule should bind on Copilot. Its reason is Claude Code's background permissions, and Copilot workers ignore it freely. Narrowing the eval allowlist (`shell(python3:*)`) would test it, or the rule's wording could say which agent it's for.
