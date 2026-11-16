"""Point the commit ids that files hold at the rewritten history.

Run from the repo root, after ``git filter-repo``:

    python3 -m scripts.remap_commits                       # reads .git/filter-repo/commit-map
    python3 -m scripts.remap_commits --commit-map PATH

filter-repo rewrites ids inside commit messages, never inside files. This reads its
commit-map (an ``old new`` header, then one pair of 40-char ids per line) and
rewrites in place:

- every ``"commit"`` value in ``workstreams/**/tasks_list.json``
- every ``closed.commit`` in ``workstreams/workstreams.json``
- every backticked 7 to 12 character hex id in ``docs/**/*.md`` and
  ``workstreams/**/*.md`` whose prefix matches exactly one old id; the new id is cut
  to the same length

An id that matches no old id is left alone and counted unknown (some short ids
belong to other repositories). A short id that matches more than one old id is left
alone and counted ambiguous. A commit filter-repo dropped (new id all zeros) maps to
nothing. The last line prints the counts: remapped, unknown, ambiguous.
"""

import argparse
import bisect
import json
import re
import sys
from pathlib import Path

DEFAULT_COMMIT_MAP = ".git/filter-repo/commit-map"

_FULL_ID = re.compile(r"[0-9a-f]{40}")
_SHORT_ID = re.compile(r"`([0-9a-f]{7,12})`")
_DROPPED = "0" * 40


def read_commit_map(path):
    """Return {old id: new id} from a filter-repo commit-map, skipping dropped commits."""
    mapping = {}
    for line in Path(path).read_text().splitlines():
        parts = line.split()
        if len(parts) != 2 or not all(_FULL_ID.fullmatch(p) for p in parts):
            continue  # the "old new" header, or a blank line
        old, new = parts
        if new != _DROPPED:
            mapping[old] = new
    return mapping


class Remapper:
    """Looks ids up in one commit-map and counts what it did."""

    def __init__(self, mapping):
        self.mapping = mapping
        self.olds = sorted(mapping)
        self.remapped = 0
        self.unknown = 0
        self.ambiguous = 0

    def full(self, old):
        """The new id for a 40-char id, or None when the map lacks it."""
        new = self.mapping.get(old)
        if new is None:
            self.unknown += 1
            return None
        self.remapped += 1
        return new

    def short(self, prefix):
        """The new id cut to len(prefix) when exactly one old id starts with prefix, else None."""
        start = bisect.bisect_left(self.olds, prefix)
        matches = []
        for old in self.olds[start:start + 2]:
            if old.startswith(prefix):
                matches.append(old)
        if not matches:
            self.unknown += 1
            return None
        if len(matches) > 1:
            self.ambiguous += 1
            return None
        self.remapped += 1
        return self.mapping[matches[0]][:len(prefix)]

    def summary(self):
        return f"{self.remapped} remapped, {self.unknown} unknown, {self.ambiguous} ambiguous"


def _write_json(path, data):
    # The same layout ws writes (src/workstream/fsutil.py write_json).
    path.write_text(json.dumps(data, indent=2) + "\n")


def _remap_commit_keys(node, remapper):
    """Rewrite every "commit" string value under node; return whether anything changed."""
    changed = False
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "commit" and isinstance(value, str):
                new = remapper.full(value)
                if new is not None:
                    node[key] = new
                    changed = True
            else:
                changed |= _remap_commit_keys(value, remapper)
    elif isinstance(node, list):
        for item in node:
            changed |= _remap_commit_keys(item, remapper)
    return changed


def remap_tasks_list(path, remapper):
    data = json.loads(path.read_text())
    if _remap_commit_keys(data, remapper):
        _write_json(path, data)
        return True
    return False


def remap_registry(path, remapper):
    data = json.loads(path.read_text())
    changed = False
    for row in data.get("workstreams", []):
        closed = row.get("closed") if isinstance(row, dict) else None
        if isinstance(closed, dict) and isinstance(closed.get("commit"), str):
            new = remapper.full(closed["commit"])
            if new is not None:
                closed["commit"] = new
                changed = True
    if changed:
        _write_json(path, data)
    return changed


def remap_markdown(path, remapper):
    text = path.read_text()

    def replace(match):
        new = remapper.short(match.group(1))
        return match.group(0) if new is None else f"`{new}`"

    new_text = _SHORT_ID.sub(replace, text)
    if new_text != text:
        path.write_text(new_text)
        return True
    return False


def remap_repo(root, mapping):
    """Rewrite the files under root in place; return (Remapper, [changed paths])."""
    root = Path(root)
    remapper = Remapper(mapping)
    changed = []
    ws_dir = root / "workstreams"
    for path in sorted(ws_dir.glob("**/tasks_list.json")):
        if remap_tasks_list(path, remapper):
            changed.append(path)
    registry = ws_dir / "workstreams.json"
    if registry.is_file() and remap_registry(registry, remapper):
        changed.append(registry)
    for base in (root / "docs", ws_dir):
        for path in sorted(base.glob("**/*.md")):
            if remap_markdown(path, remapper):
                changed.append(path)
    return remapper, changed


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.remap_commits",
        description="Rewrite commit ids held in files using git filter-repo's commit-map.",
    )
    parser.add_argument("--root", default=".", help="repo root (default: the current directory)")
    parser.add_argument(
        "--commit-map", default=None,
        help=f"filter-repo's commit-map to read (default: <root>/{DEFAULT_COMMIT_MAP})",
    )
    args = parser.parse_args(argv)
    root = Path(args.root)
    commit_map = Path(args.commit_map) if args.commit_map else root / DEFAULT_COMMIT_MAP
    if not commit_map.is_file():
        print(f"no commit-map at {commit_map}", file=sys.stderr)
        return 1
    remapper, changed = remap_repo(root, read_commit_map(commit_map))
    for path in changed:
        print(f"rewrote {path.relative_to(root)}")
    print(remapper.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
