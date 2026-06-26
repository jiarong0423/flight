from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_FILES = ["data/flights.json", "data/flights.csv"]


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def has_changes() -> bool:
    result = run(["git", "status", "--porcelain", *DATA_FILES])
    return bool(result.stdout.strip())


def update_and_push() -> int:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] Updating static flight data")
    update = run([sys.executable, "scripts/update_data.py"])
    print(update.stdout, end="")
    if update.returncode != 0:
        print("Data update failed")
        return update.returncode

    if not has_changes():
        print("No data changes detected; push skipped")
        return 0

    add = run(["git", "add", *DATA_FILES])
    print(add.stdout, end="")
    if add.returncode != 0:
        return add.returncode

    commit_message = f"Update flight data {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    commit = run(["git", "commit", "-m", commit_message])
    print(commit.stdout, end="")
    if commit.returncode != 0:
        return commit.returncode

    push = run(["git", "push"])
    print(push.stdout, end="")
    return push.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Local scheduler for GitHub Pages static flight data.")
    parser.add_argument("--interval-hours", type=float, default=4.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    if args.once:
        return update_and_push()

    interval_seconds = max(args.interval_hours, 0.1) * 60 * 60
    print(f"Local scheduler started in {ROOT}")
    print(f"Interval: {args.interval_hours} hours")
    while True:
        code = update_and_push()
        if code != 0:
            print(f"Update cycle exited with code {code}; next cycle will retry")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
