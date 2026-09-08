#!/usr/bin/env python3
"""Export a de-identified research table from EduPulse capture days.

Does not copy WAVs. Does not write staff_names.txt into the export folder.
Live capture is unchanged.

Example:
  PYTHONPATH=. python hardware/capture/export_research_table.py \
    --base-dir ~/edupulse/captures \
    --staff-file hardware/capture/staff_names.txt \
    --exclude-medical
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from edupulse.research_export import (  # noqa: E402
    default_export_dir,
    discover_sessions,
    write_export,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export de-identified EduPulse research table")
    parser.add_argument("--base-dir", type=Path, default=Path.home() / "edupulse" / "captures")
    parser.add_argument("--day", action="append", default=[], help="Session folder name or date prefix. Repeatable.")
    parser.add_argument("--staff-file", type=Path, default=ROOT / "hardware/capture/staff_names.txt")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--exclude-medical", action="store_true", default=True)
    parser.add_argument("--include-medical", action="store_true", help="Keep nurse/medical category rows")
    parser.add_argument("--salt", default=None)
    args = parser.parse_args()

    if args.day:
        sessions = []
        for day in args.day:
            direct = args.base_dir / day
            if direct.is_dir():
                sessions.append(direct)
                continue
            matches = sorted(args.base_dir.glob(f"{day}*"))
            sessions.extend(p for p in matches if p.is_dir())
        # unique preserve order
        seen: set[Path] = set()
        uniq: list[Path] = []
        for p in sessions:
            if p not in seen:
                seen.add(p)
                uniq.append(p)
        sessions = uniq
    else:
        sessions = discover_sessions(args.base_dir)

    if not sessions:
        print(f"No sessions found under {args.base_dir}", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out or (default_export_dir() / stamp)
    staff = args.staff_file if args.staff_file.is_file() else None
    table = write_export(
        sessions,
        out_dir,
        staff_file=staff,
        exclude_medical=not args.include_medical,
        salt=args.salt or stamp,
    )
    print(f"Wrote {table}")
    print(f"Codebook {out_dir / 'codebook.md'}")
    print("No WAVs copied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
