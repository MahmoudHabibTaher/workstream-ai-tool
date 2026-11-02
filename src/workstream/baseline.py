"""What a command reports, and what it already reported before the work began.

A task on a repo with known lint findings must not be judged against zero. `ws baseline
record` runs the commands once and writes <workstream>/baseline.json; `ws verify` then passes
a key when it reports nothing beyond that record.

    {"schemaVersion": 1, "commit": str, "recordedAt": str,
     "keys": {"lint": {"parser": str, "command": str, "exit": int | null,
                       "findings": [fingerprint, ...]}}}

A fingerprint leaves out what moves when unrelated code changes. For regex that is your call:
only named groups count, so leave the line number unnamed. A finding seen twice counts twice,
so a second copy of a known finding is new.

The exit-code parser can't tell new failures from old ones, so a command that fails under it
always fails. Saying otherwise would hide every regression behind the first red run.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ElementTree
from collections import Counter
from pathlib import Path

from workstream import gitutil
from workstream.config import Config
from workstream.errors import WsError
from workstream.fsutil import now_iso, write_json
from workstream.project import Project

SCHEMA_VERSION = 1
FILE_NAME = "baseline.json"
EXIT_CODE = "exit-code"
PASS, KNOWN_ONLY, FAIL = "pass", "known-only", "fail"
# Bounded so one enormous report can't fill the record or anyone's context.
MAX_RECORDED_NEW = 200
# A report older than the run by more than this was left by an earlier one. Some filesystems
# only keep whole seconds.
MTIME_SLACK_SECONDS = 2
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def parse_regex(text: str, pattern: str) -> list[str]:
    """One fingerprint per matching line: the named groups, or the whole match without any."""
    compiled = re.compile(pattern)
    found = []
    for line in strip_ansi(text).splitlines():
        match = compiled.search(line)
        if match is None:
            continue
        named = match.groupdict()
        found.append(" | ".join(v or "" for v in named.values()) if named else match.group(0))
    return found


def parse_sarif(raw: str) -> list[str]:
    """rule | file | message for each result. Raises ValueError on anything but SARIF."""
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("runs"), list):
        raise ValueError("no `runs` list")
    found = []
    for run in data["runs"]:
        for result in run.get("results") or []:
            locations = result.get("locations") or [{}]
            physical = locations[0].get("physicalLocation") or {}
            uri = (physical.get("artifactLocation") or {}).get("uri", "")
            message = (result.get("message") or {}).get("text", "")
            found.append(f"{result.get('ruleId', '')} | {uri.removeprefix('file://')} | {message}")
    return found


def parse_junit(raw: str) -> list[str]:
    """classname::name for each test that failed or errored."""
    found = []
    for case in ElementTree.fromstring(raw).iter("testcase"):
        if case.find("failure") is not None or case.find("error") is not None:
            found.append(f"{case.get('classname', '')}::{case.get('name', '')}")
    return found


def _fresh_reports(root: Path, pattern: str, started: float) -> list[Path]:
    cutoff = started - MTIME_SLACK_SECONDS
    return sorted(p for p in root.glob(pattern) if p.is_file() and p.stat().st_mtime >= cutoff)


def read_findings(entry: dict, log_text: str, root: Path, started: float
                  ) -> tuple[list[str] | None, str]:
    """(fingerprints, problem). Fingerprints are None under the exit-code parser, which reads
    none. A problem means the parser couldn't read what it was pointed at."""
    parser = entry.get("parser", EXIT_CODE)
    if parser == EXIT_CODE:
        return None, ""
    if parser == "regex":
        found = parse_regex(log_text, entry["pattern"])
    else:
        reports = _fresh_reports(root, entry["report"], started)
        if not reports:
            return None, f"this run wrote no report at {entry['report']}"
        parse = parse_sarif if parser == "sarif" else parse_junit
        found = []
        for path in reports:
            try:
                found += parse(path.read_text(errors="replace"))
            except (ValueError, AttributeError, TypeError, ElementTree.ParseError) as e:
                return None, f"cannot read {path.name} as {parser}: {e}"
    # A worktree and the main checkout report the same file under different absolute paths.
    prefix = f"{root}/"
    return [f.replace(prefix, "") for f in found], ""


def diff(current: list[str], known: list[str]) -> tuple[list[str], int]:
    """(findings beyond the baseline, how many known ones are no longer reported)."""
    new = Counter(current) - Counter(known)
    gone = Counter(known) - Counter(current)
    return sorted(new.elements()), sum(gone.values())


def judge(exit_code: int | None, entry: dict, findings: list[str] | None, problem: str,
          known: list[str]) -> dict:
    """{verdict, reason, new, gone, known}: one command's result against its baseline.

    A new finding fails even on exit 0, for a tool that always exits 0. A failed exit with
    nothing parsed fails too: that is a crash or a misconfigured parser, not a clean run.
    """
    if exit_code is None:
        return {"verdict": FAIL, "reason": "timed out", "new": [], "gone": 0, "known": 0}
    if findings is None:
        reason = problem or (f"exit {exit_code}" if exit_code else "")
        verdict = FAIL if (problem or exit_code) else PASS
        return {"verdict": verdict, "reason": reason, "new": [], "gone": 0, "known": 0}
    new, gone = diff(findings, known)
    still_known = len(findings) - len(new)
    if new:
        reason = f"{len(new)} new finding(s), {still_known} known"
        return {"verdict": FAIL, "reason": reason, "new": new[:MAX_RECORDED_NEW],
                "newCount": len(new), "gone": gone, "known": still_known}
    if exit_code and not findings:
        return {"verdict": FAIL, "reason": f"exit {exit_code} but the {entry.get('parser')} "
                                           "parser found nothing: a crash, not a finding",
                "new": [], "gone": gone, "known": 0}
    if exit_code:
        return {"verdict": KNOWN_ONLY, "reason": f"exit {exit_code}, {still_known} known, none new",
                "new": [], "gone": gone, "known": still_known}
    return {"verdict": PASS, "reason": "", "new": [], "gone": gone, "known": still_known}


def path_for(folder: Path) -> Path:
    return folder / FILE_NAME


def load(folder: Path) -> dict:
    """The record, or an empty one when no baseline was taken: everything reported is new."""
    path = path_for(folder)
    if not path.exists():
        return {"schemaVersion": SCHEMA_VERSION, "keys": {}}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise WsError(f"{path}: not valid JSON: {e}") from None
    if not isinstance(data, dict) or not isinstance(data.get("keys"), dict):
        raise WsError(f"{path}: not a baseline (no `keys` table)")
    return data


def known_findings(record: dict, key: str) -> list[str]:
    entry = record.get("keys", {}).get(key)
    return list(entry.get("findings") or []) if isinstance(entry, dict) else []


def keys_to_record(config: Config, queue: list[dict]) -> list[str]:
    """Every named command an open task verifies with, plus any with a parser configured."""
    used = {v for t in queue if t.get("status") in ("todo", "in-progress", "blocked")
            for v in t.get("verify", []) if v in config.commands}
    used |= {k for k in config.baseline_parsers if k in config.commands}
    return sorted(used)


def write(project: Project, folder: Path, keys: dict) -> Path:
    """Merge these keys into the record, stamped with the commit they ran against."""
    record = load(folder)
    record.update(schemaVersion=SCHEMA_VERSION, recordedAt=now_iso(),
                  commit=gitutil.rev_parse(project.root, "HEAD"))
    record["keys"] = {**record["keys"], **keys}
    path = path_for(folder)
    write_json(path, record)
    return path
