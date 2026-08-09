"""Repo-root path bootstrap for scripts run as files.

Usage at the top of capture/test CLIs (before other edupulse imports)::

    import ep_path; ep_path.add()

Prefer ``pip install -e .`` so this is unnecessary.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent


def add() -> Path:
    s = str(_ROOT)
    if s not in sys.path:
        sys.path.insert(0, s)
    return _ROOT


def find_and_add(start: Path | None = None) -> Path:
    """Walk parents from *start* (or cwd) until edupulse package is found."""
    cur = (start or Path.cwd()).resolve()
    for p in [cur, *cur.parents]:
        if (p / "edupulse" / "__init__.py").is_file():
            s = str(p)
            if s not in sys.path:
                sys.path.insert(0, s)
            return p
    # fall back to this file's repo root
    return add()
