# 0003: What may enter this repo from the source harnesses

**Decision.** Code is ported from subsonic-server. The Kotlin harness contributes ideas only: behaviours such as the briefing, baseline diffing and clock-out gates are reimplemented here from their described behaviour, not copied. No content, names or fixtures from the Kotlin harness enter this repo. Replay tests read a local checkout and skip when it is absent.

**Why.** The Kotlin harness is a work project and is shared with a team. Keeping it out also keeps a later public release clean.
