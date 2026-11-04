"""The protocol, the skills and what they cost: the limits are what stop prompts regrowing."""

from __future__ import annotations

import re
import shlex
import unittest
from unittest import mock

from tests.helpers import WsTestCase, evidence_text, task
from workstream import audit, gitutil, protocol, tasks
from workstream.cli import build_parser
from workstream.errors import WsError

COMMAND_RE = re.compile(r"`(ws [^`]+)`")
FENCED_RE = re.compile(r"^\s*(ws [a-z-]+.*)$", re.MULTILINE)


def fill_in(command: str) -> list[str]:
    """A command from the docs, with its placeholders given values."""
    text = re.sub(r"<[^>]+>", "x", command).replace("...", "x")
    return shlex.split(text)[1:]


class ProtocolTests(unittest.TestCase):
    def test_the_file_and_the_queue_agree_on_the_version(self) -> None:
        self.assertEqual(protocol.version(), tasks.PROTOCOL_VERSION)

    def test_sections(self) -> None:
        self.assertEqual(set(protocol.sections()),
                         {"worker", "files", "plan-shape", "task-schema", "stop"})

    def test_an_unknown_section_names_the_real_ones(self) -> None:
        with self.assertRaisesRegex(WsError, "there is: worker"):
            protocol.section("nope")

    def test_the_four_skills_exist_with_names_matching_their_folders(self) -> None:
        self.assertEqual(protocol.skill_names(),
                         ["ws-coordinate", "ws-plan", "ws-review", "ws-run"])
        for name in protocol.skill_names():
            self.assertIn(f"name: {name}\n", protocol.skill_text(name))
            self.assertTrue(protocol.description(protocol.skill_text(name)))

    def test_every_section_a_skill_names_exists(self) -> None:
        known = set(protocol.sections())
        for name in protocol.skill_names():
            self.assertEqual(set(protocol.referenced_sections(protocol.skill_text(name))) - known,
                             set(), name)

    def test_every_section_has_a_reader(self) -> None:
        """A section no role loads is prose nobody reads."""
        named = {s for name in protocol.skill_names()
                 for s in protocol.referenced_sections(protocol.skill_text(name))}
        # The brief prints `worker` itself.
        self.assertEqual(set(protocol.sections()) - named - {"worker"}, set())

    def test_every_command_they_mention_parses(self) -> None:
        """Agents copy these. A renamed flag must not leave a skill telling them to use it."""
        parser = build_parser()
        texts = [protocol.PROTOCOL_FILE.read_text()]
        texts += [protocol.skill_text(n) for n in protocol.skill_names()]
        commands = {c for t in texts for c in COMMAND_RE.findall(t) + FENCED_RE.findall(t)}
        self.assertGreater(len(commands), 15)
        for command in sorted(commands):
            argv = fill_in(command)
            # A reference like `ws set-status` names a command, and its arguments follow in prose.
            with self.subTest(command=command), mock.patch("sys.stderr"):
                if argv[0] in ("set-status", "add", "protocol", "seed", "decide"):
                    self.assertIn(argv[0], parser.format_help())
                    continue
                if len(argv) == 1 and argv[0] in ("settle", "verify", "claim", "review", "update",
                                                  "show", "close", "brief", "reset"):
                    self.assertIn(argv[0], parser.format_help())
                    continue
                parser.parse_args(argv)

    def test_skills_name_no_agents_tools(self) -> None:
        for name in protocol.skill_names():
            self.assertIsNone(re.search(
                r"AskUserQuestion|EnterPlanMode|ExitPlanMode|ToolSearch|ask_user|write_agent",
                protocol.skill_text(name)), name)


class ArgumentOrderTests(unittest.TestCase):
    def test_options_may_sit_between_a_subcommand_and_its_ids(self) -> None:
        """The form the skills use. Before Python 3.12 argparse refused it for an action followed
        by a list, so this has to pass on every version CI runs."""
        parser = build_parser()
        for argv, ids in ((["worktree", "create", "-w", "x", "T1", "T2"], ["T1", "T2"]),
                          (["worktree", "remove", "--force", "T1", "-w", "x"], ["T1"]),
                          (["claim", "--commit", "-w", "x", "--by", "y", "T1"], ["T1"]),
                          (["settle", "-w", "x", "T1", "T2"], ["T1", "T2"])):
            self.assertEqual(parser.parse_args(argv).ids, ids, argv)
        self.assertEqual(parser.parse_args(["baseline", "record", "-w", "x", "lint"]).keys, ["lint"])


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.measured = audit.measure_flow()

    def row(self, role: str) -> dict:
        return next(r for r in audit.role_rows(self.measured) if r["role"] == role)

    def test_every_role_is_within_budget(self) -> None:
        self.assertEqual([r for r in audit.role_rows(self.measured) if not r["ok"]], [])

    def test_the_plans_targets_are_what_is_enforced(self) -> None:
        self.assertEqual(audit.BUDGETS[audit.ALWAYS_ON], 150)
        self.assertEqual(audit.BUDGETS[audit.WORKER], 2500)
        self.assertEqual(audit.BUDGETS[audit.COORDINATOR], 3000)
        self.assertEqual(audit.BUDGETS[audit.PER_TASK], 400)
        self.assertEqual(audit.BUDGETS[audit.PLANNER], 3000)

    def test_a_section_a_skill_names_counts_toward_its_role(self) -> None:
        text = audit.role_text(("ws-plan",))
        self.assertIn(protocol.section("task-schema"), text)
        self.assertIn(protocol.section("plan-shape"), text)

    def test_a_section_two_skills_name_counts_once(self) -> None:
        text = audit.role_text(audit.SKILLS_BY_ROLE[audit.COORDINATOR])
        self.assertEqual(text.count(protocol.section("stop")), 1)

    def test_each_agent_is_measured_with_what_it_really_loads(self) -> None:
        for agent in ("claude-code", "copilot-cli"):
            on_agent = self.row(f"{audit.COORDINATOR} on {agent}")
            self.assertGreater(on_agent["tokens"], self.row(audit.COORDINATOR)["tokens"], agent)
            self.assertGreater(self.row(f"{audit.ALWAYS_ON} on {agent}")["tokens"],
                               self.row(audit.ALWAYS_ON)["tokens"], agent)
            self.assertTrue(self.row(f"{audit.ALWAYS_ON} on {agent}")["ok"], agent)

    def test_growth_past_a_limit_is_caught(self) -> None:
        with mock.patch.dict(audit.BUDGETS, {audit.PLANNER: 10}):
            self.assertFalse(self.row(audit.PLANNER)["ok"])

    def test_a_failing_sample_says_why(self) -> None:
        with mock.patch.object(audit._Flow, "set_up", lambda flow: flow.ws("no-such-command")), \
                self.assertRaisesRegex(WsError, "invalid choice"):
            audit.measure_flow()

    def test_the_measured_worker_load_is_the_real_brief(self) -> None:
        self.assertIn("Run `ws brief S-01 -w sample`", self.measured[audit.WORKER])
        self.assertIn("## Acceptance", self.measured[audit.WORKER])

    def test_the_per_task_load_includes_what_the_coordinator_sees(self) -> None:
        text = self.measured[audit.PER_TASK]
        self.assertIn("S-03: done, merged as", text)
        self.assertIn("claimed S-01, S-02, S-03", text)
        self.assertIn("Proposed: P1", text)


class AuditCommandTests(WsTestCase):
    def test_prints_each_role_and_exits_zero(self) -> None:
        out = self.ok("audit", "context")
        for role in audit.BUDGETS:
            self.assertIn(role, out)

    def test_a_task_whose_brief_is_too_big_fails(self) -> None:
        self.new_ws()
        self.seed_ok([task("T1", 10, summary="word " * 3000)])
        code, out, err = self.ws("audit", "context")
        self.assertEqual(code, 1, out + err)
        self.assertIn("brief T1", out)
        self.assertIn("OVER", out)
        self.assertIn("over budget: brief T1", err)

    def test_cited_plan_sections_do_not_count(self) -> None:
        self.new_ws()
        (self.ws_dir / "alpha" / "PLAN.md").write_text(
            "## 2\n\n### T1: trap\n" + "word " * 3000 + "\n")
        self.seed_ok([task("A-1", 10, findings=["T1"])])
        self.ok("audit", "context")

    def test_finished_tasks_are_left_out(self) -> None:
        self.new_ws()
        head = self.git("rev-parse", "HEAD").strip()
        self.write_queue([task("T1", 10, status="done", commit=head, summary="word " * 3000)])
        self.ok("audit", "context")

    def test_protocol_command(self) -> None:
        self.assertIn("task-schema", self.ok("protocol"))
        self.assertIn("Do this task only", self.ok("protocol", "worker"))
        self.assertIn("no protocol section", self.fails("protocol", "nope"))


class NewGateTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()
        self.set_commands(test="true")
        self.commit_all("config")

    def arrange(self, *tasks_: dict) -> None:
        self.seed_ok(list(tasks_))
        self.commit_all("seeded")

    def test_a_batch_is_one_phase(self) -> None:
        self.arrange(task("T1", 10), task("T2", 20, phase=2))
        out = self.fails("claim", "--commit", "T1", "T2")
        self.assertIn("a batch is one phase", out)
        self.assertEqual(self.by_id("T1")["status"], "todo")

    def test_a_batch_shares_no_files(self) -> None:
        self.arrange(task("T1", 10, files=["a.py"]), task("T2", 20, files=["a.py"]))
        self.assertIn("T1 and T2 both name a.py", self.fails("claim", "--commit", "T1", "T2"))

    def test_a_claim_refuses_files_shared_with_unfinished_work(self) -> None:
        self.arrange(task("T1", 10, status="blocked", files=["a.py"]),
                     task("T2", 20, status="in-progress", files=["b.py"]),
                     task("T3", 30, phase=2, files=["a.py"]),
                     task("T4", 40, phase=2, files=["b.py"]),
                     task("T5", 50, phase=2))
        self.assertIn("T3 shares a.py with T1, which is blocked",
                      self.fails("claim", "--commit", "T3"))
        self.assertIn("T4 shares b.py with T2, which is in-progress",
                      self.fails("claim", "--commit", "T4"))
        self.assertEqual(self.by_id("T3")["status"], "todo")
        self.ok("claim", "--commit", "T5")

    def test_a_foreground_task_is_claimed_alone(self) -> None:
        self.arrange(task("T1", 10, mode="foreground"), task("T2", 20))
        self.assertIn("foreground tasks run alone", self.fails("claim", "--commit", "T1", "T2"))
        self.ok("claim", "--commit", "T1")

    def test_a_foreground_task_gets_no_worktree(self) -> None:
        self.arrange(task("T1", 10, requires=["browser"]))
        self.ok("claim", "--commit", "T1")
        self.assertIn("needs browser", self.fails("worktree", "create", "T1"))

    def test_a_paused_workstream_can_not_be_claimed(self) -> None:
        self.arrange(task("T1", 10))
        self.ok("set-status", "paused")
        self.assertIn("is paused", self.fails("claim", "T1"))
        self.assertIn("is paused", self.fails("claim", "--commit", "T1"))
        self.ok("set-status", "active")
        self.ok("claim", "T1")

    def test_a_workstream_waits_for_what_it_depends_on(self) -> None:
        self.ok("new", "later", "--title", "L", "--summary", "s", "--depends-on", "alpha",
                "--base", "abc1234")
        self.seed_ok([task("L1", 10)], "later")
        self.assertIn("depends on alpha", self.fails("claim", "-w", "later", "L1"))

    def test_a_deferred_task_shipped_nothing(self) -> None:
        from workstream import registry
        rows = [{"status": "deferred", "releaseImpact": "major", "id": "A"},
                {"status": "done", "releaseImpact": "patch", "id": "B"}]
        self.assertEqual(registry.release_bump(rows), ("patch", []))

    def test_existing_commits_knows_a_commit_from_anything_else(self) -> None:
        (self.root / "a.txt").write_text("a\n")
        commit = self.commit_all("a")
        blob = self.git("rev-parse", "HEAD:a.txt").strip()
        found = gitutil.existing_commits(self.root, [commit[:7], commit, "f" * 40, blob, commit])
        self.assertEqual(found, {commit[:7], commit})
        self.assertEqual(gitutil.existing_commits(self.root, []), set())

    def test_validate_warns_about_a_rewritten_commit(self) -> None:
        self.write_queue([task("T1", 10, status="done", commit="f" * 40)])
        self.assertIn("isn't in this repository", self.ok("validate"))

    def test_validate_warns_about_an_older_protocol(self) -> None:
        path = self.write_queue([task("T1", 10, status="todo")])
        data = self.queue()
        data["protocolVersion"] = "0"
        tasks.save(path, data)
        self.assertIn("planned against protocol 0", self.ok("validate"))

    def test_the_brief_shows_the_scope_rule(self) -> None:
        plan = self.root.parent / "plan.md"
        plan.write_text('# Plan\n\n```json ws-tasks\n{"scope": {"rule": "No new endpoints.", '
                        '"outOfScope": ["the admin UI"]}, "tasks": [{"id": "T1", "phase": 1, '
                        '"priority": 10, "title": "t"}]}\n```\n')
        (self.ws_dir / "alpha" / "PLAN.md").write_text("{{EMPTY}}")
        self.ok("seed", "--from-plan", str(plan))
        self.assertEqual(self.queue()["scope"]["rule"], "No new endpoints.")
        brief = self.ok("brief", "T1")
        self.assertIn("**Scope rule:** No new endpoints.", brief)
        self.assertIn("**Out of scope:** the admin UI", brief)

    def test_a_plan_with_a_bad_scope_is_refused(self) -> None:
        plan = self.root.parent / "plan.md"
        plan.write_text('```json ws-tasks\n{"scope": {"nope": 1}, "tasks": [{"id": "T1"}]}\n```\n')
        (self.ws_dir / "alpha" / "PLAN.md").write_text("{{EMPTY}}")
        self.assertIn("scope may only hold", self.fails("seed", "--from-plan", str(plan)))

    def test_an_open_decision_stays_open_in_the_log(self) -> None:
        from workstream.decisions import render_entry
        self.assertIn("**Closed.**", render_entry(1, "d", "T", "x", "Why."))
        entry = render_entry(1, "d", "T", "x", "Someone must pick. **Open.**")
        self.assertNotIn("**Closed.**", entry)

    def test_evidence_must_name_what_it_rejected(self) -> None:
        from workstream import evidence
        t = {"id": "T", "acceptance": []}
        missing = evidence_text("T", 0, proposals="### P1: a call\nBecause.")
        self.assertIn("doesn't say what was rejected", evidence.problems(missing, t)[0])
        self.assertEqual(evidence.problems(
            evidence_text("T", 0, proposals="### P1: a\nBecause. Rejected: b."), t), [])
        self.assertEqual(evidence.problems(
            evidence_text("T", 0, proposals="### P1: a\nWho decides? **Open.**"), t), [])


if __name__ == "__main__":
    unittest.main()
