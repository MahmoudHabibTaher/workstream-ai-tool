"""`ws serve`: the web UI on localhost. It reads what `ws snapshot` and `ws review` read, and its
one write is `act.act`, so the page decides nothing and every guard stays in tested Python.

A localhost server that can commit is reachable from any page the browser opens, and from other
accounts on the machine, so:

- It binds 127.0.0.1 and has no option to bind anything else.
- Every request must name this server in Host, which stops DNS rebinding.
- Every request but the first needs the cookie that the printed address's token sets. The token
  lasts one launch.
- The write also needs a same-origin Origin and a JSON body, which a form can't send.

Repo text reaches the page as JSON, and the page draws it as text; the CSP is the second line.

Live updates: one thread stats the files a view depends on, and a change sends every open
/api/events stream a notification. Data never travels that way: clients fetch again through the
same routes, so there's one read path. The server's git calls take no optional locks, so it
can't get in the way of a person's own git.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import socketserver
import subprocess
import sys
import threading
import webbrowser
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from workstream import act, registry, review, snapshot, worktree
from workstream.errors import Refused, WsError
from workstream.project import ASSETS_DIR, Project, open_project

LOOPBACK = "127.0.0.1"
WEB_DIR = ASSETS_DIR / "web"
INDEX = "index.html"
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; "
                               "img-src 'self'; connect-src 'self'; base-uri 'none'; "
                               "form-action 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}
NEEDS_TOKEN = ("<!doctype html><meta charset=utf-8><title>Workstreams</title>"
               "<p>Open the address <code>ws serve</code> printed: it carries this launch's token.")
MAX_BODY = 64 * 1024
WATCH_SECONDS = 1.0
HEARTBEAT_SECONDS = 15.0
BUDGET_TIMEOUT_SECONDS = 120
# Ports a project's address is chosen from, so a browser's marks survive a restart.
STABLE_PORTS = (8700, 200)


# --- what to watch ------------------------------------------------------------------------


def _files_under(folder: Path) -> list[Path]:
    found = []
    for base, dirs, names in os.walk(folder):
        found += [Path(base, name) for name in (*dirs, *names)]
    return found


def git_paths(root: Path) -> list[dict]:
    """Git's part of snapshot.refresh, looked up once: it doesn't move while serving."""
    return snapshot.git_refresh(root)


def watched_paths(project: Project, git: list[dict]) -> list[Path]:
    """Every file a view of this project depends on: snapshot.refresh_paths, with each
    recursive entry expanded to what is under it. Reads the registry, which is how a new
    workstream's files join in."""
    try:
        rows = registry.load(project)["workstreams"]
    except WsError:
        rows = []
    paths = []
    for entry in snapshot.refresh_paths(project, rows, git):
        path = Path(entry["path"])
        paths.append(path)
        if entry["recursive"]:
            paths += _files_under(path)
    return paths


def fingerprint(paths: list[Path]) -> dict[str, tuple[int, int] | None]:
    def stat(path: Path) -> tuple[int, int] | None:
        try:
            found = path.stat()
        except OSError:
            return None
        return found.st_mtime_ns, found.st_size

    return {str(p): stat(p) for p in paths}


class Watcher:
    """Counts changes. Every stream waits on the one condition, so there's one stat loop however
    many are open."""

    def __init__(self, root: Path, interval: float) -> None:
        self.root = root
        self.interval = interval
        self.generation = 0
        self.changed = threading.Condition()
        self.stopping = threading.Event()
        self.git = git_paths(root)

    def scan(self) -> dict:
        return fingerprint(watched_paths(open_project(self.root), self.git))

    def run(self) -> None:
        seen = None
        while not self.stopping.wait(self.interval if seen is not None else 0):
            try:
                now = self.scan()
            except (WsError, OSError):  # a config mid-save: the next look gets it
                continue
            if seen is not None and now != seen:
                with self.changed:
                    self.generation += 1
                    self.changed.notify_all()
            seen = now

    def stop(self) -> None:
        self.stopping.set()
        with self.changed:
            self.changed.notify_all()


# --- the server ---------------------------------------------------------------------------


class Server(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, root: Path, port: int, interval: float = WATCH_SECONDS) -> None:
        self.root = root
        self.token = secrets.token_urlsafe(32)
        self.act_lock = threading.Lock()
        self.watcher = Watcher(root, interval)
        self.heartbeat = HEARTBEAT_SECONDS
        self.static = {p.name: p for p in WEB_DIR.iterdir()
                       if p.is_file() and p.suffix in CONTENT_TYPES}
        super().__init__((LOOPBACK, port), Handler)
        threading.Thread(target=self.watcher.run, name="ws-serve-watcher", daemon=True).start()

    def server_bind(self) -> None:
        # The stock one looks the host's name up, which can stall, and nothing here reads it.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]

    def server_close(self) -> None:
        self.watcher.stop()
        super().server_close()

    @property
    def port(self) -> int:
        return self.server_address[1]

    @property
    def cookie_name(self) -> str:
        # Cookies ignore the port, so two projects served at once need different names.
        return f"ws_serve_{self.port}"

    @property
    def url(self) -> str:
        return f"http://{LOOPBACK}:{self.port}/?token={self.token}"

    def project(self) -> Project:
        return open_project(self.root)


class Rejected(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _one(query: dict[str, list[str]], name: str, required: bool = True) -> str | None:
    values = query.get(name)
    if not values or not values[0]:
        if required:
            raise Rejected(400, f"needs {name}")
        return None
    return values[0]


def read_doc(project: Project, ws_id: str, name: str) -> dict:
    """A workstream's narrative file by its snapshot name, never by a path."""
    file_name = snapshot.NARRATIVE_FILES.get(name)
    if file_name is None:
        raise Rejected(400, f"no document called {name!r}")
    ws = registry.find(registry.load(project), ws_id)
    path = project.folder(ws) / file_name
    return {"name": name, "text": path.read_text() if path.is_file() else None}


def read_budget(root: Path) -> dict:
    """`ws audit context`, in its own process: it redirects stdout while it measures, and that
    would swallow what other request threads print. It runs in the project, so -P keeps the
    project's own folders off the import path, and this package is named outright in case it
    came from a relative PYTHONPATH."""
    package_parent = str(Path(__file__).resolve().parent.parent)
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(
        p for p in (package_parent, os.environ.get("PYTHONPATH")) if p)}
    done = subprocess.run(
        [sys.executable, "-P", "-m", "workstream", "--root", str(root), "audit", "context", "--json"],
        cwd=root, env=env, capture_output=True, text=True, timeout=BUDGET_TIMEOUT_SECONDS)
    try:
        return {"rows": json.loads(done.stdout)}
    except json.JSONDecodeError:
        lines = done.stderr.strip().splitlines()
        raise Rejected(500, lines[-1] if lines else f"audit exited {done.returncode}") from None


class Handler(BaseHTTPRequestHandler):
    server: Server
    server_version = "ws"
    sys_version = ""

    def log_message(self, format: str, *args: object) -> None:
        pass

    # --- answering ------------------------------------------------------------------------

    def _headers(self, status: int, content_type: str, length: int | None = None,
                 extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        if length is not None:
            self.send_header("Content-Length", str(length))
        for name, value in {**SECURITY_HEADERS, **(extra or {})}.items():
            self.send_header(name, value)
        self.end_headers()

    def _send(self, status: int, body: bytes, content_type: str,
              extra: dict[str, str] | None = None) -> None:
        self._headers(status, content_type, len(body), extra)
        self.wfile.write(body)

    def _json(self, status: int, data: object) -> None:
        self._send(status, json.dumps(data).encode(), "application/json")

    # --- guards ---------------------------------------------------------------------------

    def _check_host(self) -> None:
        allowed = {f"{LOOPBACK}:{self.server.port}", f"localhost:{self.server.port}"}
        if self.headers.get("Host") not in allowed:
            raise Rejected(403, "wrong Host")

    def _has_cookie(self) -> bool:
        wanted = f"{self.server.cookie_name}="
        for cookies in self.headers.get_all("Cookie", []):
            for part in cookies.split(";"):
                part = part.strip()
                if part.startswith(wanted) and hmac.compare_digest(
                        part[len(wanted):].encode(), self.server.token.encode()):
                    return True
        return False

    def _check_write(self) -> None:
        if self.headers.get("Origin") != f"http://{self.headers.get('Host')}":
            raise Rejected(403, "a write must come from this page")
        if self.headers.get_content_type() != "application/json":
            raise Rejected(415, "a write is JSON")

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            raise Rejected(400, "needs Content-Length") from None
        if not 0 <= length <= MAX_BODY:
            raise Rejected(413, "too long")
        try:
            data = json.loads(self.rfile.read(length))
        except ValueError:
            raise Rejected(400, "not JSON") from None
        if not isinstance(data, dict):
            raise Rejected(400, "not an object")
        return data

    # --- routes ---------------------------------------------------------------------------

    def _answer(self, route) -> None:
        try:
            self._check_host()
            route()
        except Rejected as e:
            self._json(e.status, {"error": e.message})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # a page should say what broke, and the server should stay up
            try:
                self._json(500, {"error": f"{type(e).__name__}: {e}"})
            except OSError:
                pass

    def do_GET(self) -> None:
        self._answer(self._get)

    def do_POST(self) -> None:
        self._answer(self._post)

    def _get(self) -> None:
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        if url.path == "/" and "token" in query:
            self._log_in(query["token"][0])
        elif not self._has_cookie():
            if url.path == "/":
                self._send(401, NEEDS_TOKEN.encode(), CONTENT_TYPES[".html"])
            else:
                raise Rejected(401, "open the address ws serve printed")
        elif url.path == "/":
            self._static(INDEX)
        elif url.path.startswith("/static/"):
            self._static(url.path.removeprefix("/static/"))
        elif url.path == "/api/events":
            self._events()
        elif url.path.startswith("/api/"):
            self._read(url.path.removeprefix("/api/"), query)
        else:
            raise Rejected(404, "not found")

    def _log_in(self, token: str) -> None:
        if not hmac.compare_digest(token.encode(), self.server.token.encode()):
            self._send(401, NEEDS_TOKEN.encode(), CONTENT_TYPES[".html"])
            return
        # Lax, not Strict: a Strict cookie isn't sent on a link followed from another app's page,
        # and the write's own guards are what stop another site.
        cookie = f"{self.server.cookie_name}={token}; Path=/; HttpOnly; SameSite=Lax"
        self._send(303, b"", "text/plain", {"Set-Cookie": cookie, "Location": "/"})

    def _static(self, name: str) -> None:
        path = self.server.static.get(name)  # a listing, so no path ever reaches the disk
        if path is None:
            raise Rejected(404, "not found")
        self._send(200, path.read_bytes(), CONTENT_TYPES[path.suffix])

    def _read(self, name: str, query: dict[str, list[str]]) -> None:
        try:
            project = self.server.project()
            if name == "snapshot":
                data = snapshot.build_snapshot(project, _one(query, "w", required=False))
            elif name == "review":
                data = self._review(project, query)
            elif name == "queue":
                data = review.build_queue(project)
            elif name == "doc":
                data = read_doc(project, _one(query, "w"), _one(query, "name"))
            elif name == "budget":
                data = read_budget(project.root)
            else:
                raise Rejected(404, "not found")
        except WsError as e:
            raise Rejected(404, str(e)) from None
        self._json(200, data)

    def _review(self, project: Project, query: dict[str, list[str]]) -> dict:
        raw = _one(query, "max", required=False)
        max_lines = review.DEFAULT_MAX_LINES
        if raw is not None:
            if not raw.isdigit() or int(raw) < 1:
                raise Rejected(400, "max must be a positive number")
            max_lines = int(raw)
        return review.build_review(project, _one(query, "w"), _one(query, "task"),
                                   _one(query, "file", required=False), max_lines, checks=True)

    def _events(self) -> None:
        watcher = self.server.watcher
        self._headers(200, "text/event-stream")
        seen = watcher.generation
        self.wfile.write(f"event: hello\ndata: {seen}\n\n".encode())
        self.wfile.flush()
        while not watcher.stopping.is_set():
            with watcher.changed:
                watcher.changed.wait_for(
                    lambda: watcher.generation != seen or watcher.stopping.is_set(),
                    timeout=self.server.heartbeat)
                now = watcher.generation
            line = f"event: change\ndata: {now}\n\n" if now != seen else ": still here\n\n"
            seen = now
            self.wfile.write(line.encode())
            self.wfile.flush()

    def _post(self) -> None:
        if urlsplit(self.path).path != "/api/act":
            raise Rejected(404, "not found")
        if not self._has_cookie():
            raise Rejected(401, "open the address ws serve printed")
        self._check_write()
        body = self._body()
        for name in ("action", "workstream", "expectRegistry"):
            if not isinstance(body.get(name), str) or not body[name]:
                raise Rejected(400, f"needs {name}")
        for name in ("task", "notes", "expectTasks"):
            if not isinstance(body.get(name), (str, type(None))):
                raise Rejected(400, f"{name} must be text")
        try:
            with self.server.act_lock:
                line = act.act(self.server.project(), body["action"], body["workstream"],
                               task=body.get("task"), notes=body.get("notes"),
                               expect_registry=body["expectRegistry"],
                               expect_tasks=body.get("expectTasks"))
        except Refused as e:
            self._json(409, {"refused": str(e)})
            return
        self._json(200, {"line": line})


# --- starting it --------------------------------------------------------------------------


def stable_port(root: Path) -> int:
    first, count = STABLE_PORTS
    return first + int(sha256(str(root).encode()).hexdigest()[:8], 16) % count


def bind(root: Path, port: int | None) -> Server:
    """A server on the port asked for, or on this project's usual port, or any free one if that's
    taken. A port asked for and not free is an error rather than a surprise."""
    try:
        return Server(root, stable_port(root) if port is None else port)
    except OSError as e:
        if port is not None:
            raise WsError(f"can't listen on {LOOPBACK}:{port}: {e.strerror or e}") from None
    return Server(root, 0)


def run(project: Project, port: int | None, open_browser: bool) -> int:
    os.environ["GIT_OPTIONAL_LOCKS"] = "0"
    root = worktree.integration_checkout(project)
    server = bind(root, port)
    print(f"serving {root}\n{server.url}\nctrl-C stops it", flush=True)
    if open_browser:
        try:
            webbrowser.open(server.url)
        except webbrowser.Error:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


