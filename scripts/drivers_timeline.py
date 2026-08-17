"""For each driver repo, compute monthly snapshots of synced spec-test files.

Strategy: enumerate ALL .yml/.yaml/.json files in the tree at each month-end
commit, filter out non-test noise (build configs, dep manifests, native-image
metadata), and bucket each file by the *first* matching spec-area keyword
that appears as a path component.

This is robust to test-directory reorganizations within a driver (e.g., NODE
moved tests from `spec/` to `test/spec/` in 2019; CSHARP moved from
`src/.../*Tests` to `tests/.../*Tests` to `specifications/`).

Output: data/drivers_timeline.csv with columns:
  driver, month, spec, n_files, n_lines, commit, sample_path
"""
import csv
import re
import subprocess
import sys
from pathlib import Path
from collections import defaultdict

REPOS = Path("/Users/emptysquare/co/driver-yaml-spec-testing/analysis/data/driver_repos")
OUT = Path("/Users/emptysquare/co/driver-yaml-spec-testing/analysis/data/drivers_timeline.csv")

# Drivers we run (PHPC and HHVM excluded; reported in §5).
DRIVERS = ["CDRIVER", "CSHARP", "CXX", "GODRIVER", "JAVA", "NODE",
           "PERL", "PHPLIB", "PYTHON", "RUBY", "RUST", "SWIFT"]

# Map each spec area to a list of regex patterns that match a path component.
# We test components case-insensitively against these. The first match wins.
# Order matters: more specific patterns first.
SPEC_PATTERNS = [
    ("client-side-encryption",          [r"^client[-_]side[-_]encryption$",
                                          r"^clientEncryption$",
                                          r"^csfle$",
                                          r"^client_side_encryption$"]),
    ("client-side-operations-timeout",  [r"^client[-_]side[-_]operation[-_]timeout$",
                                          r"^client[-_]side[-_]operations[-_]timeout$",
                                          r"^csot$"]),
    ("server-discovery-and-monitoring", [r"^server[-_]discovery[-_]and[-_]monitoring$",
                                          r"^discovery[-_]and[-_]monitoring$",
                                          r"^sdam$", r"^SDAM$"]),
    ("server-selection",                [r"^server[-_]selection$", r"^SS$"]),
    ("connection-monitoring-and-pooling",[r"^connection[-_]monitoring[-_]and[-_]pooling$",
                                          r"^cmap$", r"^connection[-_]monitoring$",
                                          r"^connection[-_]logging$"]),
    ("connection-string",               [r"^connection[-_]string$",
                                          r"^connection[-_]uri$", r"^uri$"]),
    ("initial-dns-seedlist-discovery",  [r"^initial[-_]dns[-_]seedlist[-_]discovery$",
                                          r"^dns[-_]seedlist$",
                                          r"^srv[-_]seedlist$",
                                          r"^dns[-_]txt[-_]records$",
                                          r"^initial[-_]dns[-_]auth$"]),
    ("auth",                            [r"^auth$"]),
    ("crud",                            [r"^crud$", r"^CRUD$",
                                          r"^crud[-_]v\d$",
                                          r"^crud_unified$"]),
    ("change-streams",                  [r"^change[-_]streams$",
                                          r"^change[-_]stream$"]),
    ("retryable-reads",                 [r"^retryable[-_]reads$"]),
    ("retryable-writes",                [r"^retryable[-_]writes$"]),
    ("transactions-convenient-api",     [r"^transactions[-_]convenient[-_]api$",
                                          r"^with[-_]transaction$"]),
    ("transactions",                    [r"^transactions$"]),
    ("read-write-concern",              [r"^read[-_]write[-_]concern$"]),
    ("max-staleness",                   [r"^max[-_]staleness$"]),
    ("gridfs",                          [r"^gridfs$", r"^GridFS$"]),
    ("sessions",                        [r"^sessions$"]),
    ("uri-options",                     [r"^uri[-_]options$"]),
    ("versioned-api",                   [r"^versioned[-_]api$",
                                          r"^stable[-_]api$",
                                          r"^serverApi$"]),
    ("load-balancers",                  [r"^load[-_]balancers$",
                                          r"^load[-_]balancer$"]),
    ("collection-management",           [r"^collection[-_]management$"]),
    ("index-management",                [r"^index[-_]management$"]),
    ("run-command",                     [r"^run[-_]command$"]),
    ("command-logging-and-monitoring",  [r"^command[-_]logging[-_]and[-_]monitoring$",
                                          r"^command[-_]logging$",
                                          r"^server[-_]selection[-_]logging$"]),
    ("command-monitoring",              [r"^command[-_]monitoring$",
                                          r"^cm[-_]tests$",
                                          r"^apm$", r"^APM$"]),
    ("unified-test-format",             [r"^unified[-_]test[-_]format$",
                                          r"^unified[-_]format$",
                                          r"^unified$",
                                          r"^UnifiedSpecTests$"]),
    ("bson-corpus",                     [r"^bson[-_]corpus$",
                                          r"^bson$",  # bson/src/test/resources/bson
                                          r"^decimal$",
                                          r"^bson[-_]binary[-_]vector$",
                                          r"^bson[-_]binary[-_]subtype[-_]\d+$",
                                          r"^bson[-_]decimal128$",
                                          r"^bson[-_]objectid$"]),
    ("atlas-data-lake-testing",         [r"^atlas[-_]data[-_]lake[-_]testing$",
                                          r"^data[-_]lake$",
                                          r"^mongohouse$"]),
    ("ocsp",                            [r"^ocsp$"]),
    ("compression",                     [r"^compression$"]),
    ("client-backpressure",             [r"^client[-_]backpressure$",
                                          r"^backpressure$"]),
    ("mongodb-handshake",               [r"^mongodb[-_]handshake$",
                                          r"^handshake$"]),
    ("open-telemetry",                  [r"^open[-_]telemetry$",
                                          r"^opentelemetry$"]),
    ("dbref",                           [r"^dbref$", r"^DBRef$"]),
    ("logging",                         [r"^logging$"]),
    ("benchmarking",                    [r"^benchmarking$"]),
    ("faas-automated-testing",          [r"^faas[-_]automated[-_]testing$",
                                          r"^lambda$"]),
    ("polling-srv-records",             [r"^polling[-_]srv[-_]records[-_]for[-_]mongos[-_]discovery$"]),
]

SPEC_REGEX = [(name, [re.compile(p, re.IGNORECASE) for p in pats])
              for name, pats in SPEC_PATTERNS]

# Path components to skip entirely (noise: build configs, dep manifests, etc.)
EXCLUDE_TOP = {".github", ".evergreen", "node_modules", "vendor", "Cargo.lock",
               ".dependabot", "third_party"}
EXCLUDE_PATTERNS = [
    re.compile(r"package(-lock)?\.json$"),
    re.compile(r"composer(-lock)?\.json$"),
    re.compile(r"Cargo\.lock$"),
    re.compile(r"(yarn|pnpm)\.lock$"),
    re.compile(r"sbom\.json$"),
    re.compile(r"native-image"),
    re.compile(r"reflect-config\.json$"),
    re.compile(r"resource-config\.json$"),
    re.compile(r"jni-config\.json$"),
    re.compile(r"proxy-config\.json$"),
    re.compile(r"serialization-config\.json$"),
    re.compile(r"predefined-classes-config\.json$"),
    re.compile(r"\.mocharc\.json$"),
    re.compile(r"tsconfig.*\.json$"),
    re.compile(r"package\.json$"),
    re.compile(r"detekt\.yml$"),
    re.compile(r"\.travis\.yml$"),
    re.compile(r"^\.evg\.yml$"),
    re.compile(r"\.evg\.yml$"),
    re.compile(r"\.dependabot\."),
    re.compile(r"action\.yml$"),
    re.compile(r"docker-compose\.yml$"),
    re.compile(r"appveyor\.yml$"),
    re.compile(r"workflows/"),
]


def is_test_file(path):
    """Return True if path looks like a spec test file (yml/yaml/json) and isn't noise."""
    ll = path.lower()
    if not (ll.endswith(".yml") or ll.endswith(".yaml") or ll.endswith(".json")):
        return False
    parts = path.split("/")
    if parts[0] in EXCLUDE_TOP:
        return False
    for pat in EXCLUDE_PATTERNS:
        if pat.search(path):
            return False
    return True


def classify(path):
    """Return (spec_area, matched_component) or (None, None)."""
    parts = path.split("/")[:-1]  # exclude file name
    for spec, regexes in SPEC_REGEX:
        for component in parts:
            for r in regexes:
                if r.match(component):
                    return spec, component
    return None, None


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


def list_blobs(git_dir, commit):
    r = run(["git", f"--git-dir={git_dir}", "ls-tree", "-r", commit])
    out = []
    for line in r.stdout.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        meta, path = parts
        meta_parts = meta.split()
        if len(meta_parts) < 3 or meta_parts[1] != "blob":
            continue
        if is_test_file(path):
            out.append((path, meta_parts[2]))
    return out


def count_noncomment_lines(content_bytes, ext):
    """Count non-blank, non-comment lines.
    YAML: skip blank lines and lines starting with `#` (after leading whitespace).
    JSON: just skip blank lines (JSON has no comments).
    """
    n = 0
    for raw in content_bytes.split(b"\n"):
        s = raw.lstrip()
        if not s:
            continue
        if ext in ("yml", "yaml") and s.startswith(b"#"):
            continue
        n += 1
    return n


def batch_line_counts(git_dir, items, cache):
    """items is list of (path, sha). Caches by sha."""
    sha_to_ext = {}
    for path, sha in items:
        if sha not in cache and sha not in sha_to_ext:
            ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
            sha_to_ext[sha] = ext
    if not sha_to_ext:
        return
    new = list(sha_to_ext.keys())
    p = subprocess.Popen(
        ["git", f"--git-dir={git_dir}", "cat-file", "--batch"],
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
        cache[sha] = count_noncomment_lines(content, sha_to_ext[sha])
        pos = nl + 1 + size + 1


def analyze_driver(driver):
    git_dir = REPOS / f"{driver}.git"
    if not git_dir.exists():
        return [], 0
    cache = {}
    rows = []
    unmatched_total = 0
    unmatched_sample = set()
    for year, month in month_iter(2014, 1, 2026, 5):
        if month == 12:
            cutoff = f"{year+1}-01-01"
        else:
            cutoff = f"{year}-{month+1:02d}-01"
        commit = last_commit_before(str(git_dir), cutoff)
        if not commit:
            continue
        blobs = list_blobs(str(git_dir), commit)
        if not blobs:
            continue
        batch_line_counts(str(git_dir), blobs, cache)
        bucket = defaultdict(lambda: {"n_files": 0, "n_lines": 0, "sample": ""})
        for path, sha in blobs:
            spec, _ = classify(path)
            if spec is None:
                unmatched_total += 1
                if len(unmatched_sample) < 30:
                    unmatched_sample.add(path)
                continue
            bucket[spec]["n_files"] += 1
            bucket[spec]["n_lines"] += cache.get(sha, 0)
            if not bucket[spec]["sample"]:
                bucket[spec]["sample"] = path
        snapshot = f"{year}-{month:02d}"
        for spec, agg in sorted(bucket.items()):
            rows.append({
                "driver": driver, "month": snapshot, "spec": spec,
                "n_files": agg["n_files"], "n_lines": agg["n_lines"],
                "commit": commit[:8], "sample_path": agg["sample"],
            })
        n_files = sum(s["n_files"] for s in bucket.values())
        n_lines = sum(s["n_lines"] for s in bucket.values())
        print(f"  {snapshot}  {commit[:8]}  classified files={n_files:>4}  lines={n_lines:>7}",
              file=sys.stderr, flush=True)
    if unmatched_sample:
        print(f"  [info] {unmatched_total} unmatched files; sample:", file=sys.stderr)
        for p in sorted(unmatched_sample)[:10]:
            print(f"    {p}", file=sys.stderr)
    return rows, unmatched_total


def main():
    only = set(sys.argv[1:]) if len(sys.argv) > 1 else None
    all_rows = []
    for driver in DRIVERS:
        if only and driver not in only:
            continue
        print(f"\n[{driver}]", file=sys.stderr)
        rows, unmatched = analyze_driver(driver)
        all_rows.extend(rows)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["driver", "month", "spec", "n_files", "n_lines",
                                          "commit", "sample_path"])
        w.writeheader()
        w.writerows(all_rows)
    print(f"\nWrote {len(all_rows)} rows to {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
