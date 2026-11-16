"""Guard against private terms in the repo, using hashes only.

Run from the repo root:

    python3 -m scripts.private_terms            # every tracked text file at HEAD
    python3 -m scripts.private_terms --all      # the same (kept from when workstreams/ was skipped)
    python3 -m scripts.private_terms --history  # every blob on every ref, and every commit message

Text is lowercased and split into ``[a-z0-9]+`` tokens. A token, or a pair of
adjacent tokens joined by one space, is a hit when its SHA-256 is in TERM_HASHES.
Any ``/Users/<name>`` path is a hit too. So ``a.b`` splits into two tokens and
can hit, while a run like ``aB`` with no separator is one token and is checked as
a whole.

The module holds only hashes, never a term: a literal list would be rewritten by
the history rewrite into nonsense. Output names ``file:line`` and the term's
index in TERM_HASHES, never the term. Exit status is 1 on any hit, else 0.
"""

import argparse
import hashlib
import re
import subprocess
import sys

# Order is fixed: a hit reports the index into this tuple.
TERM_HASHES = (
    "8b6a966e8b35257fdb0e4f39815962d3374186cbc98a9bb1b7882653f40b6e63",  # 0 token
    "ce3f8b6a080204c711eae40dc51c0717801cbb2e476d8dfd46ac3ff1b537ca2e",  # 1 token
    "3f9252bf82dd935a4d34db3551d34057271d1b6142d55650bebd79d4877e85ea",  # 2 token
    "8efdf55724c97710333b1e6e7ad03e1b61c9c4206a35ca33898058c6e15c9c42",  # 3 token
    "9f3aa1421eebec25cd1a2582a4acdae6c625ca16d1bf304ce7070eb487c70c3a",  # 4 token
    "075095892732ff49cdc485570408ebce0bf3abb6d0725b14635eda821361456f",  # 5 token
    "20a4e7dd027844b99bd03ed9c5dd4409b57e84619db03b74336c97643e0253de",  # 6 pair
)
_INDEX = {h: i for i, h in enumerate(TERM_HASHES)}

# Index reported for a /Users/<name> path, which has no entry in TERM_HASHES.
USERS_PATH = "users-path"

_TOKEN = re.compile(r"[a-z0-9]+")
_USERS = re.compile(r"/Users/[A-Za-z0-9._-]+")

EXCLUDED_BY_DEFAULT = ()


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def line_hits(line):
    """Return the hit labels in one line: term indexes (int) or USERS_PATH."""
    hits = []
    tokens = _TOKEN.findall(line.lower())
    for i, token in enumerate(tokens):
        index = _INDEX.get(_digest(token))
        if index is not None:
            hits.append(index)
        if i + 1 < len(tokens):
            index = _INDEX.get(_digest(token + " " + tokens[i + 1]))
            if index is not None:
                hits.append(index)
    if _USERS.search(line):
        hits.append(USERS_PATH)
    return hits


def text_hits(text):
    """Yield (line number, label) for every hit in text."""
    for number, line in enumerate(text.splitlines(), 1):
        for label in line_hits(line):
            yield number, label


def _format(where, number, label):
    if label == USERS_PATH:
        return f"{where}:{number}: {USERS_PATH}"
    return f"{where}:{number}: term {label}"


def _git(*args, input=None):
    return subprocess.run(
        ["git", *args], input=input, capture_output=True, check=True
    ).stdout


def _decode(data):
    """Return text, or None for a binary blob."""
    if b"\0" in data:
        return None
    return data.decode("utf-8", errors="replace")


def _read_blobs(shas):
    """Return {sha: bytes} for the given blob ids, read in one batch."""
    if not shas:
        return {}
    out = _git("cat-file", "--batch", input="".join(s + "\n" for s in shas).encode())
    blobs, pos = {}, 0
    while pos < len(out):
        end = out.index(b"\n", pos)
        sha, _kind, size = out[pos:end].decode().split()
        start = end + 1
        blobs[sha] = out[start:start + int(size)]
        pos = start + int(size) + 1
    return blobs


def head_files(include_workstreams):
    """Return [(path, blob sha)] for blobs tracked at HEAD."""
    files = []
    for entry in _git("ls-tree", "-r", "-z", "HEAD").split(b"\0"):
        if not entry:
            continue
        meta, path = entry.decode("utf-8", errors="replace").split("\t", 1)
        _mode, kind, sha = meta.split()
        if kind != "blob":
            continue
        if not include_workstreams and path.startswith(EXCLUDED_BY_DEFAULT):
            continue
        files.append((path, sha))
    return files


def scan_head(include_workstreams):
    files = head_files(include_workstreams)
    blobs = _read_blobs([sha for _, sha in files])
    lines = []
    for path, sha in files:
        text = _decode(blobs[sha])
        if text is None:
            continue
        lines.extend(_format(path, n, label) for n, label in text_hits(text))
    return lines


def scan_history():
    lines = []
    seen = {}
    for row in _git("rev-list", "--objects", "--all").decode(errors="replace").splitlines():
        sha, _, path = row.partition(" ")
        if path and sha not in seen:
            seen[sha] = path
    kinds = _git(
        "cat-file", "--batch-check=%(objectname) %(objecttype)",
        input="".join(s + "\n" for s in seen).encode(),
    ).decode().split("\n")
    blob_shas = [k.split()[0] for k in kinds if k.endswith(" blob")]
    blobs = _read_blobs(blob_shas)
    for sha in blob_shas:
        text = _decode(blobs[sha])
        if text is None:
            continue
        where = f"{seen[sha]}@{sha[:12]}"
        lines.extend(_format(where, n, label) for n, label in text_hits(text))
    log = _git("log", "--all", "--format=%H%x00%B%x00").decode(errors="replace")
    parts = log.split("\0")
    for i in range(0, len(parts) - 1, 2):
        sha = parts[i].strip()
        where = f"commit {sha[:12]}"
        lines.extend(_format(where, n, label) for n, label in text_hits(parts[i + 1]))
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m scripts.private_terms")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--all", action="store_true", help="the same as the default scan")
    mode.add_argument("--history", action="store_true",
                      help="scan every blob on every ref and every commit message")
    args = parser.parse_args(argv)
    hits = scan_history() if args.history else scan_head(include_workstreams=args.all)
    for line in hits:
        print(line)
    print(f"{len(hits)} hits")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
