# 0002: No project or agent facts in core

**Decision.** Nothing under `src/workstream/` names a stack, a build tool, a branch model or an agent. Those live in `.workstream/config.toml` and in generated adapters. `tests/test_no_project_literals.py` enforces it.

**Why.** Both source harnesses hard-coded their project (`develop`, detekt, cargo) and that is what stopped them being reused.

**Exception.** `config.py` holds the defaults a fresh project starts from.
