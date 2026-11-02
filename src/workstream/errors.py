"""The two ways a `ws` command says no. The CLI turns both into one stderr line and exit 1."""

from __future__ import annotations


class WsError(Exception):
    """The caller asked for something that can't be done: a bad id, a broken file."""


class Refused(WsError):
    """A guard said no and nothing was written. The message is the line a UI shows."""
