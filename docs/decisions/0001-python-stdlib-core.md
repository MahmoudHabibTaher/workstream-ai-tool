# 0001: Python stdlib core

**Decision.** The `ws` CLI is Python 3.11+ with no runtime dependencies.

**Why.** It reuses about 4,000 lines of tested harness logic, adds nothing to install in the target project, and can ship as a single `.pyz` committed to a repo. `tomllib` (3.11) lets the config stay TOML without a dependency.

**Rejected.** A Rust binary needs no runtime but means a full rewrite and per-OS builds. TypeScript would share a language with the UIs but forces Node on every Rust or Kotlin project.
