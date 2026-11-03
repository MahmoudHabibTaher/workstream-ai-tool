# 0011: The web UI

Decided while building M8. The workstream's own `DECISIONS.md` has the smaller calls, and [the guide](../../ui/web/README.md) has how to use it.

**There's no build step.** The page is plain ES modules and CSS in `src/workstream/assets/web/`, shipped as package data, and the source is what's served. So there's no Node at runtime or at build time, no new dependency, and no generated folder to keep current. If Node is there, `make test` also runs the helpers' tests; otherwise they skip. Rejected: a bundler and a framework, for five screens. If the page outgrows this, adding a build is a later and separate decision, and it should be the user's. The plan's layout puts this under `ui/web`, which now holds the guide and the JS tests, because a package can't ship files from outside itself.

**A localhost server that can commit needs real guards.** It binds 127.0.0.1 with no option to change that. Every request must name it in Host, which stops DNS rebinding. Every request needs a cookie set by a token in the printed address, which stops other accounts on the machine, and the write also needs a same-origin Origin and a JSON body. Repo text only becomes text nodes, and a strict CSP is the second line.

**The hashes are taken when the confirm box opens.** Live updates would otherwise defeat the guard: a redraw just before a click would pass `ws act`'s check for something the person never saw. The page warns when they've moved, and pressing Confirm is still refused by `ws act`.

**`ws review` gained `--checks` and `--queue`, additively.** A reviewer's facts belong in Python: the gates `ws settle` would run, each acceptance item beside its proof, and evidence read from the task's branch, which `ws review` alone missed before it merged. "Reviewed" isn't a tracked fact. The queue's "seen" marks live in the browser, keyed by commit.

**Commit checks are one git call per queue.** `ws validate` ran one `git rev-parse` per done task: 203 on the Rust project, and 2.0 seconds of every snapshot. It's 0.43 now, which helps every surface.

**Stale data can't arrive by SSE.** The stream only says something changed, and clients fetch again through the same routes, so there's one read path. The watcher stats files once a second, and the server's git calls take no optional locks, so it can't get in the way of someone's own git.

## Rules for changing it

- **One writer.** `api.js` holds the page's only POST, to `ws act`. A new kind of write starts in `ws act`.
- **The page decides nothing.** A new fact goes in Python with a test. `logic.js` only arranges what the server sends.
- **No `innerHTML`, ever.** Elements come from `h()` in `dom.js`. `tests/test_web.py` holds that, and that nothing loads from another host.
- **The asset folder is flat.** The server's listing is one directory, so no request's path ever reaches the disk.
- **Names no project.** The literals test covers these files.

## What was shown

All of this ran in the desktop app's browser pane, on macOS and Python 3.14.

| Check | Result |
|---|---|
| Installed from a wheel into a clean venv, with no `node` on the server's PATH | Served from the venv's site-packages; 18 web files in the wheel; no child process |
| Each screen on a sample project built with the real CLI, from that wheel | Registry, lanes, task, documents, queue, a review on a branch and a landed one, health and budget all drew |
| A write from the page | `committed f9f8f80: reports: pause (ws act)`, and the status changed on screen. Unclaim from Health also landed in an earlier build |
| A stale write from the page | With the box open, a commit from a shell changed the registry. The box warned, and Confirm showed `Refused: stale view: the registry changed since it was drawn; re-snapshot`. HEAD didn't move, and the tree stayed clean |
| Live updates | That shell commit reached the open page with no reload |
| Repo text as an attack | A title, a summary, a proof and a diff holding `<script>` or `<img onerror>` drew as text, no script ran, and a `javascript:` link stayed text |
| Token | A cookie from the previous launch got the "open the printed address" page |
| Over real HTTP in `tests/test_serve.py` | Wrong Host, missing token, foreign or missing Origin, non-JSON and traversal are each refused, with nothing written |
| Real projects, read-only | The Rust project's registry, queue, a 16-file landed review, lanes, a document and health all drew. Its HEAD, status, refs and registry were the same afterwards. This repo drew on a task branch, with health saying writes are disabled |
| Light and dark, and phone width | Both schemes looked right. Phone width was seen on one review screen |

## Not proven

- **A write to a real project through the page.** They only ran on the sample, by design. `ws act` is the same code either way.
- **A real task still on a branch, on a real project.** The Rust project's queue holds only landed work, and viewing the gates would have written loose git objects there. This repo's own in-progress task drew correctly, as did the sample's.
- **Any other browser, or another OS.** One browser pane, on macOS. The browser checks ran on Python 3.14. On 3.11, the oldest the project allows, the server and page-file tests pass, and no browser has been pointed at it.
- **A successful copy.** This pane doesn't grant clipboard access, so the one Copy button pressed fell back as designed, to showing the text with "Copy this yourself".
- **A project outside git.** `ws init --no-git` projects have no test here.
- **A long session.** Runs lasted minutes. Long-lived streams, sleep and wake, and a large queue haven't been tried.
- **Who it's for.** Nobody but the session that built it has reviewed real work with it.

## For M9

`frame-ancestors 'none'` forbids framing, and a cross-site frame wouldn't get the Lax cookie. A VS Code webview will need its own explicit way in, not a looser default.
