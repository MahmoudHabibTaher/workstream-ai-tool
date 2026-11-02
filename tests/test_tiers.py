"""What each tier asks for. Small work should stay cheap, and only work that ships should have to
say what it does to a release."""

from __future__ import annotations

from tests.helpers import WsTestCase, evidence_text, task

RUNBOOK = '[release]\nmode = "runbook"\nrunbook = "docs/release.md"'


class TierCase(WsTestCase):
    def releasing(self) -> None:
        self.edit_config('[release]\nmode = "none"', RUNBOOK)

    def make(self, tier: str, ws_id: str = "w") -> None:
        self.ok("new", ws_id, "--title", "T", "--summary", "s", "--tier", tier, "--base", "abc")
        for path in (self.ws_dir / ws_id).glob("*.md"):
            path.write_text(f"# {path.name}\n")


class LiteTests(TierCase):
    def test_a_lite_workstream_is_a_plan_and_a_queue(self) -> None:
        self.ok("new", "w", "--title", "T", "--summary", "s", "--tier", "lite")
        names = sorted(p.name for p in (self.ws_dir / "w").iterdir())
        self.assertEqual(names, ["PLAN.md", "tasks_list.json"])

    def test_its_plan_template_is_short(self) -> None:
        self.ok("new", "w", "--title", "T", "--summary", "s", "--tier", "lite")
        plan = (self.ws_dir / "w" / "PLAN.md").read_text()
        self.assertLess(len(plan.splitlines()), 12)
        self.assertNotIn("## 3. Design", plan)
        self.assertIn("Immutable", plan)

    def test_an_unfilled_plan_is_still_flagged(self) -> None:
        self.ok("new", "w", "--title", "T", "--summary", "s", "--tier", "lite")
        self.assertIn("placeholder", self.fails("validate", "-w", "w"))

    def test_it_runs_to_close(self) -> None:
        self.set_commands(test="true")
        self.make("lite")
        self.seed_ok([task("L1", 10, verify=["test"], acceptance=["works"])], "w")
        self.commit_all("planned")
        self.ok("claim", "--commit", "L1", "-w", "w")
        self.ok("worktree", "create", "L1", "-w", "w")
        where = self.root / ".workstream" / "worktrees" / "l1"
        (where / "a.txt").write_text("x")
        code, out, err = self.ws_at(where, "verify", "L1", "-w", "w")
        self.assertEqual(code, 0, out + err)
        evidence = where / "workstreams" / "w" / "evidence"
        evidence.mkdir()
        (evidence / "L1.md").write_text(evidence_text("L1"))
        self.git_at(where, "add", "-A")
        self.git_at(where, "commit", "-q", "-m", "work")
        self.ok("settle", "L1", "-w", "w")
        self.ok("close", "-w", "w")
        self.assertEqual(self.entry("w")["status"], "done")

    def test_it_does_not_ask_for_a_release_impact_in_a_releasing_project(self) -> None:
        self.releasing()
        self.make("lite")
        self.seed_ok([task("L1", 10)], "w")
        self.ok("validate", "-w", "w")
        self.assertNotIn("release:", self.ok("status", "-w", "w"))


class StandardTests(TierCase):
    def test_a_standard_workstream_keeps_the_log_files(self) -> None:
        self.ok("new", "w", "--title", "T", "--summary", "s")
        names = {p.name for p in (self.ws_dir / "w").iterdir()}
        self.assertLessEqual({"DECISIONS.md", "PROGRESS.md", "session_handoff.md"}, names)

    def test_it_does_not_ask_for_a_release_impact_either(self) -> None:
        self.releasing()
        self.make("standard")
        self.seed_ok([task("S1", 10)], "w")
        self.ok("validate", "-w", "w")


class FullTests(TierCase):
    def test_it_needs_a_runbook(self) -> None:
        out = self.fails("new", "w", "--title", "T", "--summary", "s", "--tier", "full")
        self.assertIn("no runbook", out)
        self.assertFalse((self.ws_dir / "w").exists())

    def test_it_requires_a_release_impact(self) -> None:
        self.releasing()
        self.make("full")
        self.seed_ok([task("F1", 10)], "w")
        self.assertIn("open task has no releaseImpact", self.fails("validate", "-w", "w"))
        self.ok("update", "F1", "-w", "w", "--release-impact", "patch")
        self.ok("validate", "-w", "w")

    def test_a_runbook_removed_later_is_flagged(self) -> None:
        self.releasing()
        self.make("full")
        self.edit_config(RUNBOOK, '[release]\nmode = "none"')
        self.assertIn("needs [release]", self.fails("validate", "-w", "w"))

    def done_queue(self) -> None:
        head = self.git("rev-parse", "HEAD").strip()
        self.write_queue([task("F1", 10, status="done", commit=head, releaseImpact="minor"),
                          task("F2", 20, status="done", commit=head, releaseImpact="patch"),
                          task("F3", 30, status="done", commit=head)], "w")

    def test_status_reports_the_bump_and_the_runbook(self) -> None:
        self.releasing()
        self.make("full")
        self.done_queue()
        out = self.ok("status", "-w", "w")
        self.assertIn("release: minor, runbook docs/release.md", out)
        self.assertIn("done without a releaseImpact: F3", out)

    def test_close_reports_it_too(self) -> None:
        self.releasing()
        self.make("full")
        self.done_queue()
        self.assertIn("release: minor", self.ok("close", "-w", "w"))

    def test_status_and_close_say_nothing_on_other_tiers(self) -> None:
        self.releasing()
        self.make("standard")
        head = self.git("rev-parse", "HEAD").strip()
        self.write_queue([task("S1", 10, status="done", commit=head, releaseImpact="major")], "w")
        self.assertNotIn("release:", self.ok("status", "-w", "w"))
        self.assertNotIn("release:", self.ok("close", "-w", "w"))
