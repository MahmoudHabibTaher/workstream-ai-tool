# {{TITLE}}: plan

**Immutable once approved.** If it turns out to be wrong, record that in `DECISIONS.md` with the evidence.

Written {{DATE}} against `{{INTEGRATION}}` at `{{BASE}}`.

## 1. Context

{{CONTEXT: why this work, why now, what was checked against the tree.}}

**Outcome:** {{SUMMARY}}

**Out of scope:** {{NON_GOALS: what this workstream deliberately does not do.}}

## 2. Traps

{{TRAPS: T1, T2, ... each a `### Tn: <one line>` heading: what makes the obvious change wrong, with file:line, and what to do instead. Tasks cite them in `findings`.}}

## 3. Design

{{DESIGN: one `### D-<NAME>: <one line>` section per unit of design, naming files, functions and rejected alternatives. Include how it is tested.}}

## 4. Tasks

{{TASK_TABLE: id, title, blocked by. Say which tasks share files and which must run in the foreground.}}

## 5. End-to-end verification

{{E2E: how the last task proves the whole outcome for real.}}
