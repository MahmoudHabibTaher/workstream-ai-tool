"""The protocol and skills: one copy, shipped with the CLI, never written into a workstream.

Copying the protocol into each workstream is how one harness ended up with 18 of 20 copies out
of date. A queue records which version it was planned against, and `ws validate` says when that
isn't this one.
"""

from __future__ import annotations

import re

from workstream.errors import WsError
from workstream.project import ASSETS_DIR

PROTOCOL_FILE = ASSETS_DIR / "PROTOCOL.md"
POINTER_FILE = ASSETS_DIR / "POINTER.md"
SKILLS_DIR = ASSETS_DIR / "skills"
SECTION_RE = re.compile(r"^## +(\S+)\s*$", re.MULTILINE)
VERSION_RE = re.compile(r"^Version (\S+?)\.", re.MULTILINE)
REFERENCE_RE = re.compile(r"`ws protocol ([a-z-]+)`")


def sections(text: str | None = None) -> dict[str, str]:
    """{name: body} for each `## name`, without the heading. Headings inside a fence don't occur
    in this file, and a test holds it to that."""
    text = PROTOCOL_FILE.read_text() if text is None else text
    matches = list(SECTION_RE.finditer(text))
    out = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[match[1]] = text[match.end():end].strip()
    return out


def section(name: str) -> str:
    found = sections()
    if name not in found:
        raise WsError(f"no protocol section {name!r} (there is: {', '.join(found)})")
    return found[name]


def version() -> str:
    match = VERSION_RE.search(PROTOCOL_FILE.read_text())
    return match[1] if match else ""


def skill_names() -> list[str]:
    return sorted(p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md"))


def skill_text(name: str) -> str:
    path = SKILLS_DIR / name / "SKILL.md"
    if not path.exists():
        raise WsError(f"no skill {name!r}")
    return path.read_text()


def description(text: str) -> str:
    """A skill's frontmatter description: what sits in every session's context."""
    match = re.search(r"^description:\s*(.*)$", text, re.MULTILINE)
    return match[1].strip() if match else ""


def referenced_sections(text: str) -> list[str]:
    """The protocol sections a skill tells its reader to load, in order, without repeats."""
    return list(dict.fromkeys(REFERENCE_RE.findall(text)))
