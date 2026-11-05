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
