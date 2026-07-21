#!/usr/bin/env python3
"""
EduPulse - Recording Cleanup / Disk Management Helper

Useful while testing on SD card (before the SSDs are mounted).

Features:
- Show disk usage of the recordings directory
- List recent recordings with sizes and ages
- Offer to delete old files (by age or by count)
- Safe by default (dry-run mode)

Usage:
    python cleanup_recordings.py
    python cleanup_recordings.py --data-dir ~/edupulse/test_recordings --max-age-days 2
    python cleanup_recordings.py --keep-newest 10 --delete
"""

import argparse
from pathlib import Path
from datetime import datetime, timedelta
import shutil


def human_size(num_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


def list_recordings(data_dir: Path):
    files = sorted(data_dir.glob("*.wav"), key=lambda f: f.stat().st_mtime, reverse=True)
    total_size = 0

    print(f"\nRecordings in {data_dir}:")
    print("-" * 70)
    print(f"{'Filename':<45} {'Size':>10} {'Age':>8}")
    print("-" * 70)

    now = datetime.now()
    for f in files:
        size = f.stat().st_size
        total_size += size
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        age = now - mtime
        age_str = f"{int(age.total_seconds() // 3600)}h" if age.days == 0 else f"{age.days}d"
        print(f"{f.name:<45} {human_size(size):>10} {age_str:>8}")

    print("-" * 70)
    free = shutil.disk_usage(str(data_dir)).free
    print(f"Total recordings: {len(files)} files, {human_size(total_size)}")
    print(f"Free space on drive: {human_size(free)}")
    print()

    return files


def cleanup(data_dir: Path, max_age_days: int | None, keep_newest: int | None, really_delete: bool):
    files = sorted(data_dir.glob("*.wav"), key=lambda f: f.stat().st_mtime, reverse=True)

    to_delete = []

    if max_age_days is not None:
        cutoff = datetime.now() - timedelta(days=max_age_days)
        for f in files:
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                to_delete.append(f)

    if keep_newest is not None and len(files) > keep_newest:
        to_delete.extend(files[keep_newest:])

    # Deduplicate while preserving order
    seen = set()
    to_delete = [f for f in to_delete if not (f in seen or seen.add(f))]

    if not to_delete:
        print("Nothing to delete based on current rules.")
        return

    total_size = sum(f.stat().st_size for f in to_delete)

    print(f"\nWould delete {len(to_delete)} file(s) ({human_size(total_size)}):")
    for f in to_delete:
        print(f"  {f.name}")

    if not really_delete:
        print("\nDry run — nothing was deleted.")
        print("Run with --delete to actually remove the files.")
        return

    deleted = 0
    for f in to_delete:
        try:
            f.unlink()
            deleted += 1
        except Exception as e:
            print(f"Failed to delete {f.name}: {e}")

    print(f"\nDeleted {deleted} file(s).")


def main():
    parser = argparse.ArgumentParser(description="EduPulse Recording Cleanup Helper")
    parser.add_argument("--data-dir", type=Path,
                        default=Path.home() / "edupulse" / "test_recordings",
                        help="Recordings directory")
    parser.add_argument("--max-age-days", type=int, default=None,
                        help="Delete files older than this many days")
    parser.add_argument("--keep-newest", type=int, default=None,
                        help="Keep only the N newest files")
    parser.add_argument("--delete", action="store_true",
                        help="Actually delete files (default is dry-run)")

    args = parser.parse_args()

    if not args.data_dir.exists():
        print(f"Directory not found: {args.data_dir}")
        return

    list_recordings(args.data_dir)

    if args.max_age_days or args.keep_newest:
        cleanup(args.data_dir, args.max_age_days, args.keep_newest, args.delete)


if __name__ == "__main__":
    main()
