# 0020: tidy_up closes what mbz_feedback and the VS Code extension left open

Workstream `tidy_up`, 2026-11-13. It closes the items left open in [0015](0015-mbz-feedback.md) and the D029 item in [0017](0017-vscode-extension.md). Scope was approved by the owner as D001. Nothing else changes behaviour.

## Each item, and what proved it

- **The trim test pins a fixed `--max-chars`** (0015, MF-08). TU-01: `test_long_decision_logs_get_trimmed_with_a_pointer` now measures the brief without a decision log and gives room for five entries and half of one more (D003). A rule that grows the brief no longer breaks it. Proved by `make test`.
- **Private `_text_problem` and `_mentions` called across modules** (0015, MF-03, MF-04). TU-02: they are now `evidence.text_problem` and `decisions.mentions`, and every caller is updated. A grep for the old names in `src/workstream` finds nothing. Proved by `make test`.
- **The tracking-file warning names the wrong writer** (0015, MF-07). TU-03: each file is named with its own writer, so `baseline.json` gets `ws baseline record`. When an item names several files they are joined with ", and " (D002). On a fresh sample, `ws validate` gave: "acceptance 1 names baseline.json, written by `ws baseline record`, not the worker, so the item should ask for the evidence or a proposed decision".
- **`ws-coordinate` shows `--acceptance` without `--expect`** (0015, MF-08). TU-04: the skill shows `--expect "<literal>"` and says in prose that it is optional. Brackets fail the command-parsing tests (D005). `ws adapt claude-code --check` says OK after the copy was regenerated.
- **No test for a brief with both open decisions and changes** (0015, MF-06). TU-05: `OpenDecisionTests.test_open_decisions_come_before_changes_and_each_holds_only_its_own` in `tests/test_brief.py`. Proved by `make test`.
- **D029: the tasks file is found from the order of `watch`** (0017). TU-06: the snapshot gains `paths.tasks` (schema, CLI), and the JetBrains plugin reads it, dropping only `tasks` from its documents (D004). TU-07: the VS Code extension reads it too (D006). `ws snapshot -w` on a sample gave `paths.tasks` = `…/workstreams/demo/tasks_list.json`. Proved by `make test-jetbrains` and `make test-vscode`.

## The whole run

- `make test`, `make audit`, `make test-vscode` and `make test-jetbrains` pass on main with TU-01 to TU-07 merged (TU-08's `ws verify`).
- `make eval AGENT=claude-code` passes all nine scenarios on Opus 5.5 at medium effort: full, chain, scope, verify, tracking, resume, leftover, text and hook. It cost $2.76.

## Still unproven, or left as is

- `brief._with_decisions` counts only entry texts against `--max-chars`, so a brief can run about 80 characters over it (found by TU-01, not changed under the scope rule).
- The `###` text-to-apply marker stays as D-TEXT designed it (D001).
- Copilot evals were not run: they use paid work-account credits (D001).
- D010 (`@types/node`) stays accepted by D034.
- 0015's line about `ws settle MF-01 MF-02` printing the old wording describes that run; it has nothing to close.
