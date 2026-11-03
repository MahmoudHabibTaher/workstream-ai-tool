# Web UI: plan

## 1. Context

M8 of `docs/plan.md`. The pane proved the contract inside one agent's app. This is the surface that stands alone, and the one M9 and M10 will wrap: `ws serve` and a browser UI with no Node at runtime.

**Outcome:** `ws serve` opens a localhost page with the registry, wave lanes, task detail, review (evidence and diff), health and context budget. It updates live over SSE. A write that's current lands, and a stale one is refused by `ws act`.

**Out of scope:** the IDE wrappers (M9, M10), drag-and-drop, embedded terminals, starting agents, a hosted mode, and any new kind of write.

## 2. Traps

### T1: a localhost server that commits is reachable from any web page
A page on the open web can POST to 127.0.0.1, and DNS rebinding can make it same-origin. Another account on the machine can reach the port too. Check Host, require a per-launch token, and require same-Origin JSON on the one write.

### T2: repo text is untrusted
Titles, evidence and diffs come from files in a repo, and may come from an agent. Draw them as text nodes only, never `innerHTML`. A strict CSP is the second line, not the first.

### T3: SSE keeps the view fresh, which could hide a stale write
If a confirm box took its hashes at click time from the latest snapshot, a redraw between reading and confirming would make the guard pass on something the user never saw. Pin the revisions when the box opens.

### T4: pre-merge evidence is on the branch
`ws review` only looks in the integration checkout, so a task still on its branch reads as having no evidence, exactly when review matters most. Read it at the branch.

### T5: the UI must not decide
Settling and closing aren't actions. Buttons for them copy a command or prompt. Pause, Resume and Sync show on the same rules as the pane, and Unclaim only where a finding offers it.

### T6: `ws audit context` redirects stdout in-process
It uses `redirect_stdout`, which is process-wide and would swallow output from other request threads. Run it as a subprocess.

### T7: polling git can fight the user's git
A background `git status` may take the index lock. Set `GIT_OPTIONAL_LOCKS=0` for everything the server runs, and only run git when a stat changed.

## 3. Design

### D-STATIC: no build step
Plain ES modules and CSS in `src/workstream/assets/web/`, shipped as package data. The source is what's served. Rejected: a bundler and a framework, which would add Node at build time and a generated folder to keep current, for five screens. `ui/web/README.md` is the guide, beside `ui/mod`.

### D-REVIEW: two additions to `ws review`
`--checks` adds `checks`: the gates settling would run (read-only, against the branch, or the landed commit), each acceptance item beside its quoted proof, proposed decisions, gotchas and the evidence text. `--queue` lists what's reviewable across open workstreams: on a branch first, then landed newest first, with size and a `revision` that changes when the work does. The facts sit in Python with tests, and the schema stays additive.

### D-SERVE: stdlib server
`src/workstream/serve.py`: `ThreadingHTTPServer` on 127.0.0.1 only, with no host option. Reads the integration checkout, as `ws root` says. Routes: `/`, `/static/*` (a listing, never a path), `/api/snapshot`, `/api/review`, `/api/queue`, `/api/doc`, `/api/budget`, `/api/events`, and `POST /api/act`, which calls `act.act` and answers a refusal with 409 and its line. The port is stable per project unless it's taken, so a browser's marks survive a restart.

### D-SSE: one watcher, notifications only
One thread stats the snapshot's `watch` files for every workstream, evidence folders, and git's HEAD, index, refs and worktrees, once a second. A change sends an event, and clients fetch through the same API. Data never travels over the stream, so there's one read path.

### D-UI: small modules, whole redraws
`dom.js` builds nodes from text, `logic.js` holds pure helpers, `markdown.js` parses to a tree of blocks, and each screen has a file. A redraw happens only when the fetched JSON differs, and restores scroll. "Seen" in the review queue lives in `localStorage` keyed by `revision`: it's a per-browser convenience, never project state.

## 4. Tasks

| ID | Title | Blocked by |
|---|---|---|
| WU-01 | `ws review` gains checks and a queue | |
| WU-02 | `ws serve`: guards, API, SSE | WU-01 |
| WU-03 | The shell, registry, wave lanes and task detail | WU-02 |
| WU-04 | The review screens | WU-03 |
| WU-05 | Health and context budget | WU-03 |
| WU-06 | Prove it in a browser, and write down what's true | WU-04, WU-05 |

All run in the foreground, one at a time: this session starts no sub-agents.

## 5. End-to-end verification

On a sample project built with the real CLI: each screen in a real browser, a write that lands and a stale write that's refused, with `ws serve` run from an installed wheel and no Node on its PATH. The tool's own repo and the Rust project are viewed read-only.
