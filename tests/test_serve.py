"""`ws serve` over real HTTP on a throwaway repo. What matters most: every way a page that isn't
ours could reach the one write is refused with nothing written, a current write commits, and a
stale one is refused by `ws act` itself."""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import WsTestCase, task
from tests.test_schema import load_schema, problems
from workstream import serve, snapshot
from workstream.cli import build_parser
from workstream.errors import WsError

WS_ID = "alpha"


class ServeTestCase(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws(WS_ID, "AL")
        self.set_commands(test="true")
        self.seed_ok([task("AL-01", 10, verify=["test"], acceptance=["works"], files=[]),
                      task("AL-02", 20, files=[])])
        self.ok("sync")
        (self.ws_dir / WS_ID / "PLAN.md").write_text("# The plan\n")
        self.commit_all("seeded")
        self.server = serve.Server(self.root, 0, interval=0.05)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.host = f"127.0.0.1:{self.server.port}"
        self.cookie = f"{self.server.cookie_name}={self.server.token}"

    def request(self, method: str, path: str, *, body: object = None, headers: dict | None = None,
                cookie: bool = True) -> tuple[int, dict, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=30)
        self.addCleanup(conn.close)
        sent = {"Host": self.host}
        if cookie:
            sent["Cookie"] = self.cookie
        conn.request(method, path, body=None if body is None else json.dumps(body),
                     headers={**sent, **(headers or {})})
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()

    def get_json(self, path: str) -> dict:
        status, _, data = self.request("GET", path)
        self.assertEqual(status, 200, data)
        return json.loads(data)

    def act(self, action: str = "pause", *, revisions: dict | None = None,
            headers: dict | None = None, cookie: bool = True, **fields) -> tuple[int, dict]:
        revisions = revisions or self.get_json(f"/api/snapshot?w={WS_ID}")["revisions"]
        body = {"action": action, "workstream": WS_ID, "expectRegistry": revisions["registry"],
                "expectTasks": revisions["tasks"][WS_ID], **fields}
        sent = {"Origin": f"http://{self.host}", "Content-Type": "application/json",
                **(headers or {})}
        status, _, data = self.request("POST", "/api/act", body=body, headers=sent, cookie=cookie)
        return status, json.loads(data)

    def state(self) -> tuple[str, str, bytes]:
        return (self.git("rev-parse", "HEAD"), self.git("status", "--porcelain"),
                self.registry.read_bytes())

    def assert_refused(self, expected_status: int, **kwargs) -> dict:
        before = self.state()
        status, data = self.act(**kwargs)
        self.assertEqual(status, expected_status, data)
        self.assertEqual(self.state(), before)
        return data


class BindingTests(ServeTestCase):
    def test_it_binds_loopback_only(self) -> None:
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_there_is_no_option_to_bind_anything_else(self) -> None:
        args = build_parser().parse_args(["serve", "--port", "1", "--no-open"])
        self.assertFalse(hasattr(args, "host") or hasattr(args, "bind"))
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            build_parser().parse_args(["serve", "--host", "0.0.0.0"])

    def test_a_projects_port_stays_the_same(self) -> None:
        first, count = serve.STABLE_PORTS
        self.assertEqual(serve.stable_port(self.root), serve.stable_port(self.root))
        self.assertTrue(first <= serve.stable_port(self.root) < first + count)

    def test_a_taken_port_asked_for_is_an_error(self) -> None:
        with self.assertRaises(WsError) as caught:
            serve.bind(self.root, self.server.port)
        self.assertIn(f":{self.server.port}", str(caught.exception))

    def test_a_taken_usual_port_falls_back(self) -> None:
        with mock.patch.object(serve, "stable_port", return_value=self.server.port):
            other = serve.bind(self.root, None)
        self.addCleanup(other.server_close)
        self.assertNotEqual(other.port, self.server.port)


class TokenTests(ServeTestCase):
    def test_nothing_answers_without_the_cookie(self) -> None:
        for path in ("/api/snapshot", "/api/events", "/api/queue", "/static/index.html"):
            status, _, _ = self.request("GET", path, cookie=False)
            self.assertEqual(status, 401, path)
        status, _, page = self.request("GET", "/", cookie=False)
        self.assertEqual(status, 401)
        self.assertIn(b"ws serve", page)

    def test_a_wrong_token_or_cookie_is_refused(self) -> None:
        status, headers, _ = self.request("GET", "/?token=wrong", cookie=False)
        self.assertEqual(status, 401)
        self.assertNotIn("Set-Cookie", headers)
        status, _, _ = self.request("GET", "/api/snapshot", cookie=False,
                                    headers={"Cookie": f"{self.server.cookie_name}=wrong"})
        self.assertEqual(status, 401)

    def test_another_ports_cookie_is_not_this_one(self) -> None:
        status, _, _ = self.request("GET", "/api/snapshot", cookie=False,
                                    headers={"Cookie": f"ws_serve_1={self.server.token}"})
        self.assertEqual(status, 401)

    def test_the_token_sets_the_cookie_and_leaves_the_address(self) -> None:
        status, headers, _ = self.request("GET", f"/?token={self.server.token}", cookie=False)
        self.assertEqual((status, headers["Location"]), (303, "/"))
        self.assertIn(self.cookie, headers["Set-Cookie"])
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Lax", headers["Set-Cookie"])

    def test_the_address_carries_the_token(self) -> None:
        self.assertEqual(self.server.url,
                         f"http://127.0.0.1:{self.server.port}/?token={self.server.token}")


class HostTests(ServeTestCase):
    def test_a_rebinding_name_is_refused_even_with_the_cookie(self) -> None:
        for host in ("evil.example", f"evil.example:{self.server.port}", "127.0.0.1", "127.0.0.1:1"):
            status, _, _ = self.request("GET", "/api/snapshot", headers={"Host": host})
            self.assertEqual(status, 403, host)

    def test_localhost_by_name_answers(self) -> None:
        status, _, _ = self.request("GET", "/api/snapshot",
                                    headers={"Host": f"localhost:{self.server.port}"})
        self.assertEqual(status, 200)


class WriteGuardTests(ServeTestCase):
    def test_a_foreign_origin_writes_nothing(self) -> None:
        self.assert_refused(403, headers={"Origin": "https://evil.example"})

    def test_a_missing_origin_writes_nothing(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=30)
        self.addCleanup(conn.close)
        before = self.state()
        conn.request("POST", "/api/act", body="{}", headers={
            "Host": self.host, "Cookie": self.cookie, "Content-Type": "application/json"})
        self.assertEqual(conn.getresponse().status, 403)
        self.assertEqual(self.state(), before)

    def test_a_form_post_writes_nothing(self) -> None:
        self.assert_refused(415, headers={"Content-Type": "text/plain"})

    def test_no_cookie_writes_nothing(self) -> None:
        revisions = self.get_json(f"/api/snapshot?w={WS_ID}")["revisions"]
        self.assert_refused(401, cookie=False, revisions=revisions)

    def test_no_hash_writes_nothing(self) -> None:
        self.assert_refused(400, expectRegistry="")

    def test_a_body_of_the_wrong_shape_writes_nothing(self) -> None:
        self.assert_refused(400, task=["AL-01"])
        before = self.state()
        status, _, _ = self.request("POST", "/api/act", body=[1], headers={
            "Origin": f"http://{self.host}", "Content-Type": "application/json"})
        self.assertEqual(status, 400)
        self.assertEqual(self.state(), before)

    def test_a_get_cannot_write(self) -> None:
        before = self.state()
        status, _, _ = self.request("GET", "/api/act?action=pause")
        self.assertEqual(status, 404)
        self.assertEqual(self.state(), before)


class WriteTests(ServeTestCase):
    def test_a_current_write_commits(self) -> None:
        before = self.git("rev-parse", "HEAD")
        status, data = self.act("pause")
        self.assertEqual(status, 200, data)
        self.assertIn(f"{WS_ID}: pause (ws act)", data["line"])
        self.assertNotEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual(self.git("log", "-1", "--format=%s").strip(), f"{WS_ID}: pause (ws act)")
        self.assertEqual(self.get_json("/api/snapshot")["registry"][0]["status"], "paused")
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_a_stale_write_is_refused_and_changes_nothing(self) -> None:
        drawn = self.get_json(f"/api/snapshot?w={WS_ID}")["revisions"]
        self.assertEqual(self.act("pause")[0], 200)  # what someone else did since it was drawn
        data = self.assert_refused(409, action="resume", revisions=drawn)
        self.assertIn("stale view", data["refused"])

    def test_a_stale_queue_is_refused(self) -> None:
        drawn = self.get_json(f"/api/snapshot?w={WS_ID}")["revisions"]
        self.ok("update", "-w", WS_ID, "AL-02", "--notes", "changed")
        self.commit_all("queue moved")
        data = self.assert_refused(409, action="pause",
                                   revisions={"registry": self.get_json("/api/snapshot")["revisions"]["registry"],
                                              "tasks": drawn["tasks"]})
        self.assertIn("the queue changed", data["refused"])

    def test_acts_own_refusals_come_through(self) -> None:
        data = self.assert_refused(409, action="resume")
        self.assertIn("resume needs status paused", data["refused"])
        data = self.assert_refused(409, action="close")
        self.assertIn("action must be one of", data["refused"])


class StaticTests(ServeTestCase):
    def test_the_page_comes_with_its_policy(self) -> None:
        status, headers, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_a_path_outside_the_listing_is_not_found(self) -> None:
        for path in ("/static/nope.js", "/static/../serve.py", "/static/..%2fserve.py",
                     "/static/%2e%2e/%2e%2e/config.py", "/static//etc/passwd", "/nope"):
            status, _, _ = self.request("GET", path)
            self.assertEqual(status, 404, path)


class ReadTests(ServeTestCase):
    def assert_schema(self, name: str, value: object) -> None:
        schema = load_schema(name)
        self.assertEqual(problems(value, schema, schema), [])

    def test_the_snapshot_is_the_cli_snapshot(self) -> None:
        self.assert_schema("snapshot", self.get_json("/api/snapshot"))
        data = self.get_json(f"/api/snapshot?w={WS_ID}")
        self.assert_schema("snapshot", data)
        self.assertEqual([t["id"] for t in data["tasks"]], ["AL-01", "AL-02"])

    def test_review_and_queue_pass_their_schemas(self) -> None:
        data = self.get_json(f"/api/review?w={WS_ID}&task=AL-01")
        self.assert_schema("review", data)
        self.assertEqual(data["checks"]["state"], "none")
        self.assert_schema("review-queue", self.get_json("/api/queue"))

    def test_unknown_ids_are_not_found(self) -> None:
        for path in ("/api/snapshot?w=nope", "/api/review?w=nope&task=AL-01",
                     f"/api/review?w={WS_ID}&task=NOPE", "/api/doc?w=nope&name=plan"):
            status, _, data = self.request("GET", path)
            self.assertEqual(status, 404, path)
            self.assertIn("error", json.loads(data))

    def test_a_bad_cap_is_refused(self) -> None:
        status, _, _ = self.request("GET", f"/api/review?w={WS_ID}&task=AL-01&max=0")
        self.assertEqual(status, 400)

    def test_a_document_is_asked_for_by_name_never_by_path(self) -> None:
        self.assertEqual(self.get_json(f"/api/doc?w={WS_ID}&name=plan")["text"], "# The plan\n")
        for name in ("../../.workstream/config.toml", "PLAN.md", "/etc/passwd"):
            status, _, _ = self.request("GET", f"/api/doc?w={WS_ID}&name={name}")
            self.assertEqual(status, 400, name)

    def test_a_missing_document_reads_as_none(self) -> None:
        (self.ws_dir / WS_ID / "PLAN.md").unlink()
        self.assertIsNone(self.get_json(f"/api/doc?w={WS_ID}&name=plan")["text"])

    def test_the_budget_lists_each_role(self) -> None:
        rows = self.get_json("/api/budget")["rows"]
        self.assertTrue({"role", "tokens", "budget", "ok"} <= set(rows[0]))
        self.assertIn("worker", {r["role"] for r in rows})

    def test_an_unknown_route_is_not_found(self) -> None:
        self.assertEqual(self.request("GET", "/api/nope")[0], 404)

    def test_reading_writes_nothing(self) -> None:
        before = self.state()
        for path in ("/api/snapshot", f"/api/snapshot?w={WS_ID}", "/api/queue",
                     f"/api/review?w={WS_ID}&task=AL-01", f"/api/doc?w={WS_ID}&name=plan"):
            self.get_json(path)
        self.assertEqual(self.state(), before)


class EventTests(ServeTestCase):
    def open_stream(self):
        sock = socket.create_connection(("127.0.0.1", self.server.port), timeout=10)
        self.addCleanup(sock.close)
        sock.sendall(f"GET /api/events HTTP/1.1\r\nHost: {self.host}\r\nCookie: {self.cookie}\r\n\r\n".encode())
        stream = sock.makefile("rb")
        self.addCleanup(stream.close)
        lines = []
        while (line := stream.readline()) and line != b"\r\n":
            lines.append(line)
        self.assertIn(b"200", lines[0])
        self.assertTrue(any(b"text/event-stream" in h for h in lines))
        self.assertEqual(stream.readline(), b"event: hello\n")
        stream.readline()
        stream.readline()
        return stream

    def wait_for_change(self, stream) -> None:
        self.assertEqual(stream.readline(), b"event: change\n")

    def settle_watcher(self) -> None:
        """Lets the watcher take its first look, so what follows counts as a change."""
        time.sleep(0.2)

    def test_a_watched_file_changing_reaches_an_open_stream(self) -> None:
        self.settle_watcher()
        stream = self.open_stream()
        self.ok("update", "-w", WS_ID, "AL-02", "--notes", "changed")
        self.wait_for_change(stream)

    def test_the_watched_paths_are_expanded_from_refresh(self) -> None:
        (self.ws_dir / WS_ID / "evidence").mkdir(exist_ok=True)
        (self.ws_dir / WS_ID / "evidence" / "AL-01.md").write_text("# AL-01\n")
        self.git("branch", "task/stray")
        refresh = self.get_json("/api/snapshot")["refresh"]
        expected = []
        for entry in refresh:
            expected.append(entry["path"])
            if entry["recursive"]:
                expected += [str(p) for p in serve._files_under(Path(entry["path"]))]
        watched = [str(p) for p in serve.watched_paths(self.project(), self.server.watcher.git)]
        self.assertEqual(watched, expected)
        self.assertEqual(self.server.watcher.git, snapshot.git_refresh(self.root))
        self.assertIn(str(self.ws_dir / WS_ID / "evidence" / "AL-01.md"), watched)
        self.assertIn(str(self.ws_dir / WS_ID / "PLAN.md"), watched)
        self.assertTrue(any(p.endswith("refs/heads/task/stray") for p in watched))

    def test_a_new_evidence_file_reaches_it(self) -> None:
        self.settle_watcher()
        stream = self.open_stream()
        (self.ws_dir / WS_ID / "evidence").mkdir(exist_ok=True)
        (self.ws_dir / WS_ID / "evidence" / "AL-01.md").write_text("# AL-01\n")
        self.wait_for_change(stream)

    def test_a_new_branch_reaches_it(self) -> None:
        self.settle_watcher()
        stream = self.open_stream()
        self.git("branch", "task/stray")
        self.wait_for_change(stream)

    def test_a_write_from_the_page_reaches_it(self) -> None:
        self.settle_watcher()
        stream = self.open_stream()
        self.assertEqual(self.act("pause")[0], 200)
        self.wait_for_change(stream)

    def test_a_quiet_stream_sends_a_heartbeat(self) -> None:
        self.settle_watcher()
        self.server.heartbeat = 0.05
        stream = self.open_stream()
        self.assertEqual(stream.readline(), b": still here\n")

    def test_no_change_means_no_event(self) -> None:
        self.settle_watcher()
        before = self.server.watcher.generation
        time.sleep(0.3)
        self.assertEqual(self.server.watcher.generation, before)


if __name__ == "__main__":
    unittest.main()
