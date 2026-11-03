# Web UI

The project's workstreams in a browser: the registry, wave lanes, task detail, review, health and context budget. It's `ws serve`, plain files and the Python standard library, so there's nothing to install beyond `ws`, and no Node.

```bash
ws serve
```

That opens the page. `--no-open` only prints its address, and `--port` picks the port. Run it from any checkout of the project: it reads the one holding the integration branch, as `ws root` reports it.

## Screens

**Queues.** Open workstreams with their status and progress, and closed ones behind a toggle. Opening one shows its wave and a lane per phase, with `★ ready` on what can start, and what each task waits on. Plan, Progress, Decisions and Handoff are tabs there. A task's page has its acceptance items, verify commands, files, notes and facts.

**Review.** Start here. The queue lists work still on a branch, oldest first, then what has landed, newest first, each with its size. Opening one shows, side by side:

- What the CLI checked: the gates `ws settle` would run, or the commit it landed as.
- Each acceptance item with its quoted proof beneath it, and **Nothing quoted.** where there's none.
- Proposed decisions, gotchas and the whole evidence file.
- The diff, a file at a time. A long file is cut at a hunk boundary and says so, with a button for the rest.

`j` and `k` move between files, `n` and `p` between tasks, and `s` marks a task seen. **Seen** is kept in that browser, by commit, so new work on a branch reads as unseen again. It isn't project state, and nothing else reads it.

**Health.** Findings by level, with only the actions each one lists, and Sync where a row's progress is out of date. On any branch but the integration one, it says writes are disabled, and `ws act` refuses them.

**Budget.** What each role costs against its limit, from `ws audit context`, including each open task's brief. It re-measures while it's open, which takes a few seconds.

## Writes

Pause, Resume, Unclaim and Sync are the only writes, and each asks first, naming the commit and the branch. The box keeps the hashes of what you were looking at when it opened. If something changes while it's open, it warns you, and pressing Confirm is refused by `ws act` with nothing changed.

Landing, closing and abandoning aren't writes here. Their buttons copy a command or a prompt for your own terminal or agent, and nothing is sent. The page can't start an agent.

## Safety

It listens on 127.0.0.1 only, and there's no option to change that. The address it prints carries a token that lasts until it stops, so another account on the machine, or a web page in your browser, can't read or write through it. An old tab needs the new address after a restart. The page updates by itself while the files change, and a dot at the top right shows when it has lost the server.

Each open tab holds one of the browser's connections to the server, so about six tabs on one project will stall.

## Changing it

The files are in [`src/workstream/assets/web/`](../../src/workstream/assets/web/), and what's there is what's served: there's no build step. The rules are in [the decision](../../docs/decisions/0011-web-ui.md).

`make test` holds the rules that can be checked. The tests in [`tests/`](tests/) cover the pure helpers. They run under Node where it's installed, and skip otherwise.
