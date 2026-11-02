"""`ws audit usage` on synthetic transcripts in both shapes. Real transcripts hold whole
conversations, so what matters as much as the medians is that nothing else comes out."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from workstream import usage
from tests.helpers import WsTestCase

SECRET = "hunter2-do-not-print"
PROJECT = Path("/somewhere/the project")
CLAUDE, COPILOT = "claude-code", "copilot-cli"


def assistant(n: int, size: int, side: bool = False) -> dict:
    return {"type": "assistant", "isSidechain": side, "timestamp": "2026-03-04T10:00:00Z",
            "message": {"id": f"m{n}", "role": "assistant",
                        "content": [{"type": "text", "text": SECRET}],
                        "usage": {"input_tokens": 10, "cache_read_input_tokens": size - 30,
                                  "cache_creation_input_tokens": 20}}}


def user(text: str) -> dict:
    return {"type": "user", "timestamp": "2026-03-04T10:00:00Z", "message": {"role": "user", "content": text}}


def write_lines(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n{not json, a cut-off line\n")


class TempDirCase(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.base, True)


class MessageLinesTests(TempDirCase):
    def write_session(self, name: str, sizes: list[int], prompt: str = "hello") -> Path:
        folder = self.base / usage.slug(PROJECT)
        records = [user(prompt)] + [assistant(i, s) for i, s in enumerate(sizes)]
        write_lines(folder / f"{name}.jsonl", records)
        return folder / name

    def report(self, **kwargs) -> dict:
        return usage.report(CLAUDE, PROJECT, transcripts=self.base, **kwargs)["roles"]

    def test_a_session_that_started_workers_is_a_coordinator_and_they_are_workers(self) -> None:
        session = self.write_session("main", [100, 200, 300])
        write_lines(session / "subagents" / "a.jsonl",
                    [user("Run `ws brief T1` and follow it.")]
                    + [assistant(i, s) for i, s in enumerate([50, 60, 70, 80, 90, 95])])
        write_lines(session / "subagents" / "b.jsonl", [user("look around")] + [assistant(0, 5)])
        roles = self.report()
        self.assertEqual((roles["coordinator"]["sessions"], roles["coordinator"]["peak"]), (1, 300))
        worker = roles["worker"]
        self.assertEqual((worker["sessions"], worker["first"], worker["atGrowthTurn"], worker["growth"]),
                         (1, 50, 90, 40))
        self.assertEqual(worker["cumulative"], 445)
        self.assertEqual(roles["other"]["sessions"], 1)

    def test_a_worktree_subagent_is_a_worker_whatever_its_prompt_said(self) -> None:
        session = self.write_session("main", [100])
        write_lines(session / "subagents" / "a.jsonl", [user("Implement it")] + [assistant(0, 50)])
        (session / "subagents" / "a.meta.json").write_text('{"spawnedWithWorktree": true}')
        self.assertEqual(self.report()["worker"]["sessions"], 1)

    def test_a_message_counts_once_though_its_usage_repeats(self) -> None:
        folder = self.base / usage.slug(PROJECT)
        write_lines(folder / "s.jsonl", [user("hi"), assistant(1, 100), assistant(1, 100), assistant(2, 200)])
        self.assertEqual(self.report()["other"]["turns"], 2)

    def test_another_projects_transcripts_are_left_out(self) -> None:
        write_lines(self.base / "-elsewhere" / "s.jsonl", [user("hi"), assistant(1, 100)])
        self.assertEqual(self.report()["other"]["sessions"], 0)

    def test_a_short_session_stays_out_of_growth(self) -> None:
        self.write_session("short", [100, 200], prompt="ws brief T1")
        worker = self.report()["worker"]
        self.assertEqual((worker["sessions"], worker["reachedGrowthTurn"], worker["growth"]), (1, 0, None))

    def test_the_window_filters_by_day(self) -> None:
        self.write_session("s", [100])
        self.assertEqual(self.report(since="2026-03-05")["other"]["sessions"], 0)
        self.assertEqual(self.report(until="2026-03-04")["other"]["sessions"], 1)

    def test_an_old_format_sidechain_in_a_main_file_is_not_the_mains(self) -> None:
        folder = self.base / usage.slug(PROJECT)
        write_lines(folder / "s.jsonl", [user("hi"), assistant(1, 100), assistant(2, 9000, side=True)])
        self.assertEqual(self.report()["other"]["peak"], 100)


class EventLinesTests(TempDirCase):
    def write_session(self, name: str, *records: dict, cwd: str = str(PROJECT)) -> None:
        start = {"type": "session.start", "timestamp": "2026-03-04T10:00:00Z",
                 "data": {"context": {"cwd": cwd, "gitRoot": cwd}}}
        write_lines(self.base / name / "events.jsonl", [start, *records])

    @staticmethod
    def call(size: int, agent: str | None = None) -> dict:
        record = {"type": "session.usage_record", "data": {"usage": {"inputTokens": size}}}
        return {**record, "agentId": agent} if agent else record

    def report(self, **kwargs) -> dict:
        return usage.report(COPILOT, PROJECT, transcripts=self.base, **kwargs)["roles"]

    def test_a_coordinator_and_its_workers(self) -> None:
        self.write_session("a", {"type": "user.message", "data": {"content": SECRET}},
                           {"type": "subagent.started", "data": {"agentName": "ws-worker"}},
                           self.call(100), self.call(10, "w1"), self.call(200), self.call(20, "w1"))
        roles = self.report()
        self.assertEqual((roles["coordinator"]["sessions"], roles["coordinator"]["peak"]), (1, 200))
        self.assertEqual((roles["worker"]["sessions"], roles["worker"]["peak"]), (1, 20))

    def test_a_session_opened_with_the_marker_is_a_worker(self) -> None:
        self.write_session("a", {"type": "user.message", "data": {"content": "please clock in"}}, self.call(5))
        self.assertEqual(self.report()["other"]["sessions"], 1)
        self.assertEqual(self.report(worker_marker="clock in")["worker"]["sessions"], 1)

    def test_a_session_below_the_project_counts_and_one_elsewhere_does_not(self) -> None:
        self.write_session("a", self.call(5), cwd=str(PROJECT / ".workstream" / "worktrees" / "t1"))
        self.write_session("b", self.call(5), cwd="/elsewhere")
        self.assertEqual(self.report()["other"]["sessions"], 1)


class RemoteTests(WsTestCase):
    def test_a_checkout_elsewhere_counts_when_it_names_the_same_repository(self) -> None:
        self.git("remote", "add", "origin", "git@example.com:owner/the-repo.git")
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, True)
        start = {"type": "session.start", "timestamp": "2026-03-04T10:00:00Z",
                 "data": {"context": {"cwd": "/elsewhere/wt", "repository": "owner/the-repo"}}}
        write_lines(base / "a" / "events.jsonl",
                    [start, {"type": "session.usage_record", "data": {"usage": {"inputTokens": 7}}}])
        roles = usage.report(COPILOT, self.root, transcripts=base)["roles"]
        self.assertEqual(roles["other"]["sessions"], 1)


class ReportTests(WsTestCase):
    def test_the_command_prints_numbers_and_never_a_transcripts_text(self) -> None:
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, True)
        folder = base / usage.slug(self.root.resolve())
        write_lines(folder / "s.jsonl", [user(f"ws brief {SECRET}"), assistant(1, 1000)])
        out = self.ok("audit", "usage", "--agent", CLAUDE, "--transcripts", str(base))
        self.assertIn("1,000", out)
        self.assertNotIn(SECRET, out)
        as_json = self.ok("audit", "usage", "--agent", CLAUDE, "--transcripts", str(base), "--json")
        self.assertNotIn(SECRET, as_json)
        self.assertEqual(json.loads(as_json)[0]["roles"]["worker"]["peak"], 1000)

    def test_every_agent_with_a_reader_is_reported_when_none_is_named(self) -> None:
        self.assertEqual(usage.agents_with_transcripts(), [CLAUDE, COPILOT])
