# Decisions: MBZ feedback

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-05, user): scope approved

The user chose a warning rather than a refusal for acceptance items naming a tracking file, because all 3 such items among this repo's 274 are legitimate.
The user ruled out automatic comparison of results against worded acceptance.
Text left for a file a worker can't edit is printed as `to apply:` rather than the `open:` first suggested, because `open:` already means an open decision, which is a stop condition. **Closed.**

## D002 (2026-11-05, MF-02): Text to apply is shielded from the rest of the evidence handling

Everything before the section is what parse, the placeholder check and `rewrite_ids` work on. Otherwise a `## Acceptance` in the text would overwrite the real section in `_sections`, a double-brace template in the text would fail the check as an unfilled placeholder, and settling would rewrite a `P1` in the text, so it would no longer be exact. Rejected: leaving the placeholder check and `rewrite_ids` reading the whole file, which is less code but breaks the exactness D-TEXT asks for. **Closed.**

## D003 (2026-11-05, MF-02): The first `## Text to apply` heading at the start of a line opens the section

The text under it may quote the heading, as text about this very section would. Rejected: the last such heading, which would cut that text short. The cost is that an earlier section can't hold the heading at the start of a line, which would already split it in `_sections`. **Closed.**

## D004 (2026-11-05, MF-03): Text naming a path the evidence check rejects is left out of `to apply:`, unread

The settle gate already refuses such evidence, so this only reaches evidence that skipped the gate. Telling a coordinator to apply text outside the project would be worse than saying nothing. Rejected: listing it unread as not applied, which sends the coordinator to write outside the repo. **Closed.**

## D005 (2026-11-05, MF-03): The close warning reads `warning: to apply: <line>`

It keeps the prefix settle prints, so the same search finds both. Rejected: separate wording for close, which says nothing more. **Closed.**

## D006 (2026-11-05, MF-04): `_with_decisions` tells whether an entry names the task with `decisions._mentions`

It is the match `relevant` already uses, so `T1` doesn't count as named by `T10`, which a test pins. An entry's author line counts too, so a decision a task recorded itself names it. The name is private to another module, because `decisions.py` isn't on this task's file list. Rejected: a plain substring check, which would put `T10`'s decisions first in `T1`'s brief. **Closed.**

## D007 (2026-11-05, MF-05): A correction whose new text ends in a mark merges that mark rather than doubling it

A coordinator may paste the old text back with an edit, so `--summary "new (changed by D001)" --because D002` writes `new (changed by D001, D002)`, and text that is only a mark is refused as empty. Rejected: treating the pasted mark as plain text, which writes two marks in a row. **Closed.**

## D008 (2026-11-05, MF-05): The warning reads the marks anywhere in the summary and acceptance, while a merge reads only the mark at the end

The warning asks whether a decision has been applied at all, and the task's text is the only record of that. Rejected: counting only a trailing mark for the warning, which would warn about a correction a coordinator reworded by hand. **Closed.**

## D009 (2026-11-05, MF-06): The section goes after `## Open decisions`, not before it

An open decision is a stop condition, so it stays straight after Acceptance when both sections print. No test covers a brief with both. Rejected: placing the new section first, which would move the stop condition down. **Closed.**

## D010 (2026-11-05, MF-06): A decision with a Changes line counts once a later entry closes it

"Settled" is read as not in `decisions.open_entries`, so an entry that opened and was later closed is listed under its own title, alongside the closing entry if that one names the task too. Rejected: looking for the closed mark in the entry's own text, which would miss a closure recorded by a later entry. **Closed.**

## D011 (2026-11-05, MF-07): `tasks.tracking_file_warnings` imports `hook.WRITERS` inside the function

`hook` imports `registry` and `handoff`, which import `tasks`, so a top-level import is a cycle. `audit.py` and `cli.py` already import inside a function, with a comment saying why. Rejected: moving the names to a lower module, which needs `project.py` and `baseline.py`, off this task's file list, and which still can't take `handoff.FILE_NAME` without its own cycle. **Closed.**

## D012 (2026-11-05, MF-07): `ws update --acceptance` warns about every item of the task, not only the corrected one

The warning has one source and each line gives its item number, so a line about another item is still true. Rejected: filtering to the corrected number, more code to hide a true warning. **Closed.**

## D013 (2026-11-05, MF-07): A name counts only whole, and an optional `n` labels a task with no id

`MY_DECISIONS.md`, `old-PROGRESS.md` and `DECISIONS.md.bak` don't warn, and a test pins that. An item's `expect` counts as well as its text, since `acceptance_text` includes it. `tracking_file_warnings(task, n=0)` adds `n` to D-TRACKING's signature so `validate_tasks` labels an id-less task as its other rules do. Rejected: a plain substring check, which warns on other files. **Closed.**
