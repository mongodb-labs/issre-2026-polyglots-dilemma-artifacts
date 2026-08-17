"""For drivers that pull spec tests via git submodule, compute monthly snapshots
of the submodule's spec test contents.

Walks the driver's commits chronologically. At each month-end commit:
1. Get the submodule SHA via `git ls-tree`
2. Read that commit from the specifications repo (must be already fetched)
3. Compute per-spec yml/json file count and line count

Output: data/drivers_submodule_timeline.csv
  driver, month, spec, n_files, n_lines, driver_commit, submodule_sha
"""
import csv
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPOS = Path("/Users/emptysquare/co/driver-yaml-spec-testing/analysis/data/driver_repos")
SPECS = Path("/Users/emptysquare/co/driver-yaml-spec-testing/analysis/data/specifications")
OUT = Path("/Users/emptysquare/co/driver-yaml-spec-testing/analysis/data/drivers_submodule_timeline.csv")

DRIVERS = ["JAVA", "GODRIVER", "PHPLIB"]


def find_specs_submodule_path(git_dir, commit):
    """Read .gitmodules at this commit and return the path of the submodule
    pointing at mongodb/specifications, or None."""
    r = run(["git", f"--git-dir={git_dir}", "show", f"{commit}:.gitmodules"])
    if r.returncode != 0:
        return None
    lines = r.stdout.splitlines()
    cur_path = None
    for line in lines:
        line = line.strip()
        if line.startswith("path"):
            cur_path = line.split("=", 1)[1].strip()
        elif line.startswith("url"):
            url = line.split("=", 1)[1].strip()
            if "mongodb/specifications" in url and cur_path:
                return cur_path
            cur_path = None
    return None


def run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, check=False, **kw)


def month_iter(start_year, start_month, end_year, end_month):
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def last_commit_before(git_dir, date_iso):
    r = run(["git", f"--git-dir={git_dir}", "log", "-1", f"--before={date_iso}", "--format=%H"])
    return r.stdout.strip() or None


def submodule_sha(git_dir, commit, path):
    r = run(["git", f"--git-dir={git_dir}", "ls-tree", commit, path])
    line = r.stdout.strip()
    if not line:
        return None
    parts = line.split()
    if len(parts) < 3 or parts[1] != "commit":
        return None
    return parts[2]


def list_yaml_in_specs(commit):
    r = run(["git", f"--git-dir={SPECS}/.git", "ls-tree", "-r", commit, "source/"])
    if r.returncode != 0:
        return None
    out = []
    for line in r.stdout.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        meta, path = parts
        meta_parts = meta.split()
        if len(meta_parts) < 3 or meta_parts[1] != "blob":
            continue
        sha = meta_parts[2]
        ll = path.lower()
        if ll.endswith(".yml") or ll.endswith(".yaml"):
            out.append((path, sha))
    return out


def count_noncomment_yaml(content_bytes):
    n = 0
    for raw in content_bytes.split(b"\n"):
        s = raw.lstrip()
        if not s or s.startswith(b"#"):
            continue
        n += 1
    return n


def batch_line_counts(specs_git_dir, shas, cache):
    new = [s for s in shas if s not in cache]
    if not new:
        return
    p = subprocess.Popen(
        ["git", f"--git-dir={specs_git_dir}", "cat-file", "--batch"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0,
    )
    p.stdin.write(("\n".join(new) + "\n").encode())
    p.stdin.flush()
    p.stdin.close()
    out = p.stdout.read()
    p.wait()
    pos = 0
    for sha in new:
        nl = out.find(b"\n", pos)
        header = out[pos:nl].decode()
        parts = header.split()
        if len(parts) < 3 or parts[1] != "blob":
            cache[sha] = 0
            pos = nl + 1
            continue
        size = int(parts[2])
        content = out[nl + 1:nl + 1 + size]
        cache[sha] = count_noncomment_yaml(content)
        pos = nl + 1 + size + 1


def main():
    cache = {}
    sha_seen = {}  # submodule_sha -> per-spec dict
    rows = []
    for driver in DRIVERS:
        git_dir = REPOS / f"{driver}.git"
        if not git_dir.exists():
            continue
        print(f"\n[{driver}]", file=sys.stderr)
        for year, month in month_iter(2014, 1, 2026, 5):
            if month == 12:
                cutoff = f"{year+1}-01-01"
            else:
                cutoff = f"{year}-{month+1:02d}-01"
            d_commit = last_commit_before(str(git_dir), cutoff)
            if not d_commit:
                continue
            sub_path = find_specs_submodule_path(str(git_dir), d_commit)
            if not sub_path:
                continue
            s_sha = submodule_sha(str(git_dir), d_commit, sub_path)
            if not s_sha:
                continue
            if s_sha not in sha_seen:
                blobs = list_yaml_in_specs(s_sha)
                if blobs is None:
                    # SHA not in specs repo (shouldn't happen if fetched)
                    print(f"    [warn] specs SHA {s_sha[:8]} not found", file=sys.stderr)
                    sha_seen[s_sha] = {}
                    continue
                batch_line_counts(str(SPECS / ".git"), [b[1] for b in blobs], cache)
                bucket = defaultdict(lambda: {"n_files": 0, "n_lines": 0})
                for path, sha in blobs:
                    parts = path.split("/")
                    if len(parts) < 2 or parts[0] != "source":
                        continue
                    spec = parts[1]
                    bucket[spec]["n_files"] += 1
                    bucket[spec]["n_lines"] += cache.get(sha, 0)
                sha_seen[s_sha] = dict(bucket)
            snapshot = f"{year}-{month:02d}"
            for spec, agg in sorted(sha_seen[s_sha].items()):
                rows.append({
                    "driver": driver,
                    "month": snapshot,
                    "spec": spec,
                    "n_files": agg["n_files"],
                    "n_lines": agg["n_lines"],
                    "driver_commit": d_commit[:8],
                    "submodule_sha": s_sha[:8],
                })
            total_files = sum(s["n_files"] for s in sha_seen[s_sha].values())
            total_lines = sum(s["n_lines"] for s in sha_seen[s_sha].values())
            print(f"  {snapshot}  drv={d_commit[:8]} sub={s_sha[:8]}  "
                  f"files={total_files:>4} lines={total_lines:>7}", file=sys.stderr, flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["driver", "month", "spec", "n_files", "n_lines",
                                          "driver_commit", "submodule_sha"])
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {len(rows)} rows to {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
