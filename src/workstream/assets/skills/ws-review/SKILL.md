---
name: ws-review
description: Review one workstream task against its acceptance items, evidence and diff; changes nothing.
---

# Review a task

You read and judge; you change nothing, and you don't write tracking files.

1. `ws show <task> -w <id>`: what it was meant to do.
2. `ws review <task> -w <id>`: the evidence path and the diffstat. Add `--file <path>` for the hunks of the files that matter, rather than the whole diff.
3. `ws settle <task> -w <id> --dry-run`: what the CLI already checked. Don't re-check it by hand.
4. Judge what it can't: does each quoted proof show its acceptance item? Does the diff do what the task says, and only that? Does it walk into a trap the task cites? Does a proposed decision hold up?

Finish with **land**, **send back** or **ask the user**, then one line per finding with `file:line`, what is wrong and what it causes. Report what you checked and found nothing in; don't pad it with style notes.
