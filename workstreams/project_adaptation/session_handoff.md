# Session handoff

**State:** 1/5 done on `main` at `fa7c825`, as of 2026-11-02.

**Just landed:** AD-01 (`fa7c825085`)

**Next:** `ws claim --commit AD-02` (phase 1).

**Gotchas:**
- AD-01: node's stylish eslint output has no usable regex, since the file sits on its own line. The profile's pattern needs `--format unix`, so a project on stylish gets a comment at init rather than known findings.
