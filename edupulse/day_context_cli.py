"""CLI for EduPulse day-context notes.

Invoked as:
  python -m edupulse.day_context_cli note "Fire drill" --tag fire_drill
  python -m edupulse.day_context_cli context [--day YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import sys

from edupulse.day_context import (
    append_note,
    context_md_path,
    ensure_day_context,
    load_day_context,
    resolve_session_dir,
)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("Usage: edupulse note \"…\" | edupulse context", file=sys.stderr)
        return 2

    cmd = argv[0]
    rest = argv[1:]

    if cmd == "note":
        p = argparse.ArgumentParser(prog="edupulse note", description="Append a day-context note")
        p.add_argument("text", nargs="+", help="Note text")
        p.add_argument("--day", help="Session date or folder (default: latest capture day)")
        p.add_argument("--tag", action="append", default=[], help="Tag (repeatable), e.g. fire_drill")
        p.add_argument("--when", help="Optional time hint, e.g. ~09:15")
        p.add_argument(
            "--captures-dir",
            default=None,
            help="Override captures root (default ~/edupulse/captures)",
        )
        args = p.parse_args(rest)
        note = " ".join(args.text).strip()
        session = resolve_session_dir(args.day, args.captures_dir)
        path = append_note(session, note, tags=args.tag or None, when=args.when)
        data = load_day_context(session)
        print(f"Noted → {path}")
        if data.get("tags"):
            print(f"Tags: {', '.join(data['tags'])}")
        return 0

    if cmd == "context":
        p = argparse.ArgumentParser(prog="edupulse context", description="Show day context")
        p.add_argument("--day", help="Session date or folder (default: latest capture day)")
        p.add_argument(
            "--captures-dir",
            default=None,
            help="Override captures root (default ~/edupulse/captures)",
        )
        args = p.parse_args(rest)
        session = resolve_session_dir(args.day, args.captures_dir)
        ensure_day_context(session)
        data = load_day_context(session)
        print(f"Session: {session}")
        print(f"File:    {context_md_path(session)}")
        if data.get("tags"):
            print(f"Tags:    {', '.join(data['tags'])}")
        print()
        print(data.get("markdown") or "(empty)")
        return 0

    print(f"Unknown day-context command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
