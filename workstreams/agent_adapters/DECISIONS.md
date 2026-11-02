# Decisions: Agent adapters

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-02, user): scope approved

The user said to start M5. Copilot here is on a work account and the user keeps this project separate from work, so no real Copilot run happens without asking. Headless Claude Code has no valid login here, and the user must sign in themselves. **Closed.**

## D002 (2026-11-02, AA-01): a file already at a skill's path counts as not ours

It could be someone's own skill with the same name, so it gets the same refusal as a hand edit. Rejected: overwriting it because the name matches. **Closed.**

## D003 (2026-11-02, AA-02): skill descriptions were shortened, and the audit counts the block markers and the worker's description

All three load in every session, and counting them took always-on past 150. Each description lost a few words. Rejected: raising the limit, since the limit is the point. Whether the shorter descriptions still trigger is for AA-05 to show. **Closed.**

## D004 (2026-11-02, AA-03): `ws hook` wraps argument errors too

argparse exits 2 on bad arguments, and exit 2 is what blocks on one agent, so a version skew would stop every edit. Rejected: leaving it, since a missing flag isn't a reason to stop someone's work. **Closed.**

## D005 (2026-11-02, AA-04): a run on Copilot must name its account

On this machine it is logged in to a work account, and this project is kept apart from work. A flag saying which account you mean is cheap, and a wrong guess would spend someone else's credits. Rejected: a warning, which a script would scroll past. **Closed.**
