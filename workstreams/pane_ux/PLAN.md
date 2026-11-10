# pane_ux: plan

## 1. Context

Bring the same design to the Claude Code pane (M7, decision 0010) as far as the pane allows. It's narrow, runs on mobile, and draws buttons and text only. It can only fill Claude Code's own prompt box, so it gets no other launch targets. It depends on `jetbrains_ux` for the facts.

**Outcome:** a workstream's detail gets **Tasks**, **Graph** and **Overview** sub-screens. A task opens its own page: summary, depends-on and unblocks as buttons that jump, files, acceptance, verify, notes and the claim. Run, Run This Task, Coordinate, Close and Abandon first show the `ws launch check` results, then fill the box with the snapshot's prompt. A blocking check fills nothing.

**Out of scope:** Terminal, Copilot Chat and Air targets. Agent presets. Submitting a prompt (0010: never `$.prompt.submit`).

## 2. Traps

### T1: the pane still holds a copy of the prompts
`ui/mod/hooks/views/detail.tsx:78` `promptText` duplicates `snapshot.py:42`. Read the row's `launches` instead, and delete `promptText`, together with its test in `ui/mod/tests/detail.test.tsx`.

### T2: state shapes are tagged
New screens and fields are added to `$.state` atoms in `ui/mod/types/index.d.ts:106` (`screen`), with the shape tag bumped (0010's rules). A missing bump leaves an old shape in place after `/reload-plugins`.

### T3: the mod's tests need the agent CLI
`make test-mod` runs only locally. `tests/test_mod_files.py` runs the real `ws` with each command the mod sends, so `ws launch check` must be added there.

## 3. Design

### D-SCREENS: sub-screens and a task page
`hooks/views/detail.tsx` gains a Tasks/Graph/Overview button row, and `hooks/views/task.tsx` is the task page, one file per screen, in the shared look from `style.tsx`. The Graph is an indented list of buttons.

### D-PREFLIGHT: checks before filling the box
`hooks/data.ts` runs `ws launch check`. The detail screen shows the result inline, and a blocking check disables the button with its message.

## 4. Tasks

| id | title | blocked by |
|---|---|---|
| PX-01 | Read launches from the snapshot; drop promptText | – |
| PX-02 | Tasks, Graph and Overview sub-screens | PX-01 |
| PX-03 | Task page with jump buttons | PX-02 |
| PX-04 | Pre-flight before filling the prompt, and Run This Task | PX-03 |
| PX-05 | Prove it in the desktop app | PX-04 |

## 5. End-to-end verification

PX-05, with the owner. Run `/reload-plugins` and open `/workstreams` on the sample in the desktop app. Then the sub-screens draw, a task page's dependency jumps, a blocking check disables Run with its message, and Run This Task fills the box with the snapshot's text and sends nothing. `make test` and `make test-mod` pass, and 0019 gains the pane's results.
