# Decisions: Run feedback

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-04, user): scope approved

The user asked for each issue to be handled by its own agent, instead of grouped steps. So there is one task per issue, each worked by a fresh background worker, plus one final proof task. Subsonic-server's own fixes stay out of this queue. RF-14 (expected output on acceptance items) was offered as the one to drop, and the user kept it. Claude Code eval spend is approved for RF-15; Copilot evals are not. **Closed.**

## D002 (2026-11-04, RF-01): an entry that doesn't fit is skipped, and later shorter ones are still kept

D-GOTCHA says to keep whole entries up to the cap but not whether to stop at the first that doesn't fit. Going on keeps more at the same cost, and T5's complaint was short late gotchas being lost. So an entry is cut only when no entry fits whole; alongside one that fits, an over-limit entry is left out and counted. Rejected: stopping at the first entry that doesn't fit, since one long bullet would hide every short one after it. **Closed.**

## D003 (2026-11-04, RF-01): a cut entry counts as one in `(N more in <path>)`

D-GOTCHA asks for the same pointer on a cut entry, and `(0 more ...)` would say nothing was left out. So N counts entries not shown whole, and a lone cut entry reads `(1 more in <path>)`. Rejected: a different wording for the cut case, which D-GOTCHA rules out. **Closed.**

## D004 (2026-11-04, RF-04): only a line with a leading pipe is a table row, and the first cell is read literally

`find_section` skips rows inside code fences, and doesn't read `G7 | text` (no leading pipe) or `| **G7** | text |` (bold) as G7. D-CITE says the first cell starts with the ref, and a loose match could turn prose into a citation. Those forms still get the warning, so nothing is hidden. Rejected: stripping emphasis markup and accepting pipeless rows. **Closed.**

## D005 (2026-11-04, RF-04): a blank PLAN.md counts as not written

`citation_warning` skips an empty or whitespace-only `PLAN.md` as it does a placeholder one, since it has nothing to cite yet. Rejected: warning about every ref in a file that has no plan in it. **Closed.**

## D006 (2026-11-04, RF-05): operators inside quotes or after a backslash don't count, and a bare assignment doesn't warn

D-ENV says "later has `&&`, `||`, `;` or `|`". Read literally, `A=1 sh -c 'a && b'` and `A=1 find . -exec rm {} \;` would warn, though the variable reaches everything that runs. So quoted strings and escaped characters are masked before the search. `A=1 && b` has no command word after the assignment, so it sets a shell variable that lasts, and it doesn't warn. A prefix with several assignments names them all.

Rejected: a literal substring search, for the false warnings above; `shlex`, because in POSIX mode it strips the quotes, so `\;` and `"&&"` look like real operators, and in non-POSIX mode it splits `A="x y"`. **Closed.**
