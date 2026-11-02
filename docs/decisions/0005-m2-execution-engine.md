# 0005: How the execution engine records and lands work

Decided while building M2.

**Verify records live in the git common dir, not `.workstream/runs/`.** `<git common dir>/workstream/runs/` is shared by every worktree, can't be committed, and needs no `.gitignore` entry in the adopting project. Writing there is safe wherever commits work, because a commit writes there too. Outside a git repo it falls back to `.workstream/runs/`.

**A verification is tied to the code tree, not the commit.** The code tree is the tree without any workstream folder or the registry. So a worker can verify, write evidence, and commit, and the record stays valid; changing any code invalidates it. Rejected: comparing commits, which forces verifying after the evidence commit, while the evidence quotes the verification.

**The record stops honest mistakes, not fraud.** An agent with a shell can edit a file in `.git`. Signing it would add machinery with no attacker to justify it.

**A failing command under the exit-code parser always fails.** It can't tell new failures from old, so treating known-red as a pass would hide every regression. `ws baseline record` warns, and the fix is to configure a parser. Rejected: the Kotlin harness's honour-system `--validated` flag. M4's `ws init` has to handle this for repos with failing lint.

**A task's merged tree is verified before the merge commit exists.** `settle` merges with `--no-commit`, re-runs verify when anything else landed since, and aborts cleanly on failure. Parallel branches first run together here, so it is where they break. If nothing else landed the trees match and the run is skipped. `--skip-post-merge-verify` is the escape for commands that can't run on the main checkout, and the queue records that it was used.

**Merge and bookkeeping are two commits.** A commit can't contain its own hash, and the task records the merge's hash. A crash between them is recovered by rerunning `settle`, which finds the merge by its `Ws-Task:` trailer. Rejected: amending the merge to include tracking files, which still can't name itself.

**The first task that can't land stops the batch.** Those already merged are recorded. Merging past a failure would stack later work on a state nobody has looked at.

**`ws claim --commit` is a flag, and `ws worktree create` enforces it.** A plain claim stays useful without git in the loop. The check sits at the point of need, which refuses a worktree when the claim isn't committed. `ws-coordinate` (M3) will use the flag.

**Worktrees sit inside the repo, excluded through `.git/info/exclude`.** An agent sandbox allows writing there, and the project's `.gitignore` stays untouched. The location is configurable under `[worktree] dir`.

**Task ids are restricted to letters, digits, `.`, `_` and `-`, starting with a letter or digit.** An id now names a file, a folder and a branch. A queue with anything else is refused on load, which is a change from M1.

**Generated files are never agent-written.** Decisions numbering, `PROGRESS.md` entries and `session_handoff.md` come from state. A worker's only channel is its evidence file, whose Gotchas section reaches the handoff and the next task's brief.
