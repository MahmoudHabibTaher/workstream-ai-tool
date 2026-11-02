# Pilot results

M6's measurements: what real sessions carried before this tool, and what they carry on it. Every figure comes from `ws audit usage`, which reads each agent's own transcripts and reports numbers only. Tokens are the context in each model call, and the two agents count differently, so compare within an agent and never across.

## Before

Measured on 2026-11-02, up to 2026-11-01, so nothing here ran on this tool. Figures are medians per session.

**Claude Code on the Rust project:**

```bash
ws audit usage --agent claude-code --project <path> --until 2026-11-01
```

| Role | Sessions | Turns | Turn 1 | Turn 5 | Growth | Peak | Highest | Cumulative |
|---|---|---|---|---|---|---|---|---|
| Worker | 121 | 41 | 53,806 | 79,058 | 25,110 | 155,432 | 406,710 | 5,054,896 |
| Coordinator | 35 | 77 | 71,876 | 85,851 | 13,663 | 172,724 | 481,101 | 9,184,985 |

**Copilot CLI on the Kotlin project:**

```bash
ws audit usage --agent copilot-cli --project <path> --until 2026-11-01 --worker-marker 'clockin|shift'
```

| Role | Sessions | Turns | Turn 1 | Turn 5 | Growth | Peak | Highest | Cumulative |
|---|---|---|---|---|---|---|---|---|
| Worker | 28 | 17 | 60,806 | 71,775 | 10,698 | 94,795 | 160,765 | 1,306,702 |

Copilot has no coordinator row because that harness ran its shifts one at a time, with no session that started workers. Only 63 of its sessions on that project have per-call figures, since older ones don't record them, and the 28 workers are picked out by a rough text match on their opening prompt. Treat that row as approximate.

## How this differs from the first comparison

[The comparison](harness-comparison.md) estimated these by hand. Most of it held up:

- **Worker turn 1, growth and peak match:** 54k, 26k and 155k then, and 54k, 25k and 155k now.
- **Coordinator peak is higher:** 173k rather than 163k, over 35 sessions rather than 31. The ≤ 80k target is unchanged.
- **Cumulative cost was underestimated:** about 2.2M per worker was labelled a floor, and the median is 5.05M. Later turns carry much more than the first.
- **Copilot growth can now be measured:** the comparison had no per-turn figure, and it's about 11k by turn 5.

## Targets

From the plan, for Claude Code on comparable work:

| Measure | Before | Target | After |
|---|---|---|---|
| Worker growth, turn 1 to turn 5 | 25,110 | ≤ 8,000 | Not yet run |
| Coordinator peak | 172,724 | ≤ 80,000 | Not yet run |
