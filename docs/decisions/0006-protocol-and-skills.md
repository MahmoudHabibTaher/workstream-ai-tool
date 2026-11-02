# 0006: One protocol, four skills, and limits that fail CI

Decided while building M3. [rule-map.md](../rule-map.md) lists where every old rule went.

**The protocol and skills ship inside the package**, under `src/workstream/assets/`, not in top-level `protocol/` and `skills/` folders as the plan first drew them. `ws protocol` and M5's `ws adapt` have to find them after a plain install.

**The protocol is read by section.** `ws protocol stop` prints one section, so nobody loads the rest. The worker's rules live in its `worker` section and `ws brief` prints them, so there is one copy.

**`ws-run` is the loop; `ws-coordinate` is everything around it.** That is the old dispatch and coordinate split, except that bookkeeping moved to `ws settle`, so `ws-run` is about 30 lines. Project steps such as a release moved out to a runbook named in the config.

**Skills name capabilities, not an agent's tools.** "One question at a time", not a specific tool. M5 turns them into each agent's form.

**A skill's cost includes every protocol section it names.** `ws audit context` follows `ws protocol <section>` references, so moving text out of a skill can't hide it.

**The coordinator's budget covers `ws-run` and `ws-coordinate` together**, since one session usually loads both.

**The per-task cost is measured, not estimated.** The audit runs a sample batch through the real CLI in a throwaway repo and counts what the coordinator would see. A chatty new message fails CI like a long skill does. Tokens are still estimated at four characters each: good enough to catch growth, and M6 measures the real thing.

**A reviewer limit was added** at 1,500 tokens. The plan set none, and a role with no limit would be the one to grow.

**A new command that claims a batch is stricter than a plain claim.** `ws claim --commit` refuses a batch that spans phases, shares files or mixes a foreground task with others. Plain `ws claim` stays as M1 ported it, since it doesn't start workers. Both refuse a paused or closed workstream, or one whose dependencies aren't done.

**Proposed decisions must say what they rejected.** Both harnesses asked for this in prose, and one recorded that it is the part most often left out. `settle` now refuses a proposal without `Rejected:`, unless it is marked `**Open.**` for someone to settle.

**The start-of-session baseline check is gone.** Subsonic ran or justified skipping a full check at every clock-in. Now a worker's `ws verify` fails on a red tree and `settle` re-checks merged code, so a red tree surfaces with no ritual. The cost is one worker's time when the integration branch is already red, which the first blocked report stops. If pilots show this wastes real work, M4's `ws doctor` can check it before a batch.

**Some old rules are only as good as the agent following them.** "Don't redo a worker's job", "one question at a time" and similar are skill lines with no gate. Scenario evals for those belong to M5, when real agents run these skills.
