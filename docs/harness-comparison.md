# Harness comparison

How the two workstream harnesses this tool grew out of compare: subsonic-server (Rust, Claude Code) and the Kotlin harness (Kotlin Multiplatform, Copilot CLI). Measured 2026-11-02 from a read of both repos and session transcripts on the author's machine. The decisions in this repo rest on it, so it is kept as written rather than updated.

## Verdict

**subsonic-server has the better system. The Kotlin harness has the better agent ergonomics and is the bigger waster of always-on context.** Neither should be copied wholesale. The tool should use subsonic's engineering as the base and port the Kotlin harness's best ideas into the CLI.

| Dimension | Better | Why |
|---|---|---|
| Prompt clarity | **the Kotlin harness** | a single overriding rule stated up front, verify-don't-trust loop, failure-mode tables, a validation adequacy table |
| Prompt structure | **subsonic** | Clean plan / dispatch / coordinate split, native plan mode, a compact planner |
| Prompt portability | Neither | subsonic's skills are full of repo facts (47 matching lines in the coordinator, including a cargo/GHCR release runbook). The Kotlin harness's skills use Gradle/detekt and Copilot tool names |
| Script engineering | **subsonic** | 2,093 lines with 2,375 lines of tests, against 1,940 lines and no tests found. Has a JSON read model, hash-guarded writes and parallel waves |
| Script ergonomics for agents | **the Kotlin harness** | `clockin` assembles the briefing, `-w <name>` is short, `clockout` gates mechanically, baseline diffing, drift reporting |
| Parallel execution | **subsonic** | Worktree batches, all-or-nothing `claim`, single writer for tracking files. The Kotlin harness is strictly sequential |
| Always-on context | **subsonic** | Rules are path-scoped. The Kotlin harness loads 35 KB into nearly every session |
| Orchestrator context | **the Kotlin harness** | Its loop only spawns and checks. subsonic's orchestrator hand-writes briefs, reads evidence and does the bookkeeping |
| UI | **subsonic** | A working 1,001-line Claude Code mod. The Kotlin harness has none |

## Context cost

**Method.** Static figures are bytes ÷ 4. Measured figures come from transcripts on this machine: 123 subsonic worker runs, 31 subsonic orchestrator sessions and 317 Copilot sessions in the Kotlin harness. The two vendors report tokens differently, so compare within a harness rather than across them.

**The cost model that matters:** anything loaded stays in context and is re-read every turn. A subsonic worker runs a median of 40 turns, so 1k always-loaded tokens means about 40k token-reads per worker. Prompt caching lowers the price but not the room it takes up.

| Measured | subsonic (Claude Code) | the Kotlin harness (Copilot CLI) |
|---|---|---|
| Worker context at turn 1 | 54k median | 42k system + tool definitions (median at session end) |
| Worker orientation | +26k by turn 5 (80k), attribution inferred | Not measured per turn |
| Worker peak | 155k median | Session end: 72k median, 220k max |
| Orchestrator peak | 163k median, 481k max | Not comparable (session total includes workers) |
| Cumulative per worker | About 2.2M (arithmetic: 54k × 40 turns, a floor) | 2.0M median per shift (reported, n=134) |

**What the prompts add per role (static, tokens):**

| Role | subsonic | kotlin |
|---|---|---|
| Always-on | 4.4k `CLAUDE.md` (only ~150 is about workstreams) | **8.8k** workflow file + 1.4k `AGENTS.md` |
| Planner | ~9k | ~14k |
| Worker orientation | ~13–15k | ~21–27k |
| Orchestrator static | ~12k | ~14k |

Both prompt sets are nearly the same total size (83 KB and 85 KB). What differs is when each one loads.

## Where context is wasted

**The Kotlin harness**
1. **`tasks-list-workflow.instructions.md` has `applyTo: '**'`.** Its 35 KB was in the system prompt of **39 of 40** sampled sessions in the Kotlin harness, including work unrelated to workstreams. That is about 350k token-reads per 40-turn shift, and it is the largest single fix available. It also documents rarely used commands (`reset`, `clear`, `close`) in that always-on text.
2. **Rules restated across files.** "One task per shift" appears 20 times across 5 files, sub-agent model inheritance 12 times across 5, scope 17 times across 4. The shift prompt restates its own skill.
3. **Whole `PROGRESS.md` reads.** Files reach 16–22 KB while the skill only needs the latest entry.
4. **`tasks.py` output is 17% of all tool-result tokens**, about 6k per session.
5. **A legacy flow still documented.** `start`/`done` sits beside `clockin`/`clockout` as a second way to do the same thing.

**subsonic**
1. **Protocol copied into every workstream.** `AGENTS.md` is a 12.5–14 KB frozen copy, and only 2 of 20 workstreams have the current single-writer rules. The template also grew from ~146 to 225 lines within weeks, which is the drift pattern this tool must prevent.
2. **The orchestrator does clerical work.** It hand-writes each worker brief (5.7k chars median), reads each evidence file (~1.1k tokens) and renumbers `P<n>` to `D<nnn>`. It also writes `PROGRESS` and the handoff. All of that is mechanical and belongs in a script.
3. **One fact written three times.** Evidence, then a `PROGRESS` summary, then `DECISIONS`. Evidence-path rules appear 15 times across 4 files, decision numbering 16 times across 4.
4. **Plans written twice.** The approved plan is model output, then model output again as `PLAN.md` and `seed.json`: 20–35 KB each time.
5. **Project facts in generic prompts.** The release runbook sits in the coordinator and loads even with `--no-release`.

**Both**
- **Redundancy is paraphrase, not copy-paste.** 8-word phrase overlap between files is at most 4%, so a dedupe script won't find it. It takes a redesign around one home per rule.
- **Code search dominates worker context.** Shell reads and searches are 56% of a subsonic worker's tool and edit traffic; source views and other shell output are about 50% in the Kotlin harness. Trimming prompts helps most at startup, and later turns need the same discipline: bounded command output and targeted reads.
- **Build output is unbounded.** Gradle and cargo logs go straight into context.

**Correction to subsonic's earlier report:** it estimated about 15k tokens of repeated `dispatch-tasks` injection per run. In the 10 largest orchestrator sessions, the skill appears once in 9 and twice in 1. This is not worth prioritizing.

## What to carry over

| From subsonic | From the Kotlin harness |
|---|---|
| Single writer for tracking state, per-task evidence files | `clockin`-style briefing assembled by the CLI |
| `wave`, all-or-nothing `claim`, file-overlap warnings | Baseline recorded at planning; judge "nothing beyond it" |
| Typed `mode` / `requires` / `releaseImpact` | Validation adequacy (task kind → required commands) |
| Immutable plan with `DECISIONS` delta log | Mechanical `clockout` gates and `filesToTouch` diff warning |
| `snapshot` read model, hash-guarded `act`, `review` | Registry drift reporting, `-w <name>`, `close` lifecycle |
| The pane and all CLI tests | "Verify, don't trust" and the no-progress guard |
| Per-task acceptance + verify | "One home per fact" rule, named validation keys |
