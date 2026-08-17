"""Compute per-commit test-LOC changes for the UTF migration analysis.

Reads  analysis/utf_migration/commits.json  (curated commit list per driver).
Writes analysis/utf_migration/results.csv   (computed LOC stats; regenerable).

Requires bare driver repos in analysis/data/driver_repos/.

Usage:
    python analysis/scripts/utf_migration_loc.py [DRIVER ...]

    If driver names are given, only those drivers are processed.
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
REPOS = BASE / "data" / "driver_repos"
CONFIG = BASE / "utf_migration" / "commits.json"
OUTPUT = BASE / "utf_migration" / "results.csv"


def git_show_diff(git_dir: str, sha: str) -> str:
    r = subprocess.run(
        ["git", f"--git-dir={git_dir}", "show", "--unified=0", "--format=", sha],
        capture_output=True, text=True,
    )
    return r.stdout


def is_test_file(path: str, path_patterns: list[str], extensions: list[str]) -> bool:
    ll = path.lower()
    if not any(ll.endswith(ext.lower()) for ext in extensions):
        return False
    return any(pat in path for pat in path_patterns)


def count_diff(diff_text: str, path_patterns: list[str], extensions: list[str]) -> tuple[int, int]:
    deleted, added = 0, 0
    in_test = False
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            path = line.split(" b/", 1)[1] if " b/" in line else ""
            in_test = is_test_file(path, path_patterns, extensions)
        elif in_test:
            if line.startswith("-") and not line.startswith("---"):
                deleted += 1
            elif line.startswith("+") and not line.startswith("+++"):
                added += 1
    return deleted, added


def main():
    only = set(sys.argv[1:]) if len(sys.argv) > 1 else None
    config = json.loads(CONFIG.read_text())

    existing = []
    if OUTPUT.exists() and only:
        with OUTPUT.open() as f:
            existing = list(csv.DictReader(f))
        existing = [r for r in existing if r["driver"] not in only]

    rows = list(existing)
    for driver, info in config.items():
        if only and driver not in only:
            continue
        git_dir = str(REPOS / info["repo_dir"])
        patterns = info["test_path_patterns"]
        extensions = info["test_extensions"]
        print(f"\n[{driver}]")
        for commit in info["commits"]:
            sha = commit["sha"]
            diff = git_show_diff(git_dir, sha)
            deleted, added = count_diff(diff, patterns, extensions)
            net = deleted - added
            row = {
                "driver": driver,
                "sha": sha,
                "title": commit["title"],
                "role": commit.get("role", "conversion"),
                "test_lines_deleted": deleted,
                "test_lines_added": added,
                "net_test_lines_removed": net,
                "note": commit.get("note", ""),
            }
            rows.append(row)
            print(f"  {sha[:8]}  {deleted:>5}del {added:>5}add {net:>+6}net  {commit['title'][:60]}")

    if not rows:
        print("No data to write.")
        return

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {len(rows)} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
