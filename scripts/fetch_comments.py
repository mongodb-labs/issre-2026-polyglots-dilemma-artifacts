"""Fetch Jira comments for all 546 candidate tickets and save to data/comments.jsonl.

Resumable: skips keys already present in the output file.

Usage:
    JIRA_API_KEY=<token> .venv/bin/python3 scripts/fetch_comments.py
"""
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "comments.jsonl"
JIRA_BASE = "https://jira.mongodb.com"
WORKERS = 8
MAX_COMMENT_CHARS = 1000
MAX_COMMENTS = 15

# Inline the candidate-key logic to avoid importing anthropic
CSV_PATH = REPO / "data" / "classified_sonnet.csv"
LATE_DRIVERS = {"NODE", "CXX", "CDRIVER", "RUBY", "PHPLIB"}
CRUD_SPEC_PUBLISHED = "2015-02"
EXCLUDE_SPECS = {
    "sdam", "connection-string", "auth", "auth-scram", "auth-oidc",
    "auth-aws", "auth-x509", "gridfs", "change-streams", "command-monitoring",
    "csfle", "dns-seedlist", "cmap", "index-management", "retryable-reads",
    "versioned-api", "logging", "client-side-encryption",
    "server-discovery-and-monitoring", "ocsp", "compression",
    "load-balancer", "stable-api", "opentelemetry", "collation",
    "time-series", "causal-consistency",
}

import re
CRUD_KEYWORDS = re.compile(
    r"\b(insert|update|delete|find|aggregate|replace|bulk.?write|count.?document|"
    r"estimated.?document|distinct|find.?one.?and|upsert|bulkwrite|insertOne|insertMany|"
    r"updateOne|updateMany|deleteOne|deleteMany|replaceOne|findOne)\b",
    re.IGNORECASE,
)


def candidate_keys() -> set:
    keys = set()
    done_p1: set = set()
    rows = []
    with CSV_PATH.open() as f:
        rows = list(csv.DictReader(f))

    for r in rows:
        if r["project"] not in LATE_DRIVERS:
            continue
        specs = set(s for s in (r.get("spec_areas") or "").split("|") if s)
        if (r["category"] == "driver_spec_nonconformance"
                and "crud" in specs
                and r["created"][:7] >= CRUD_SPEC_PUBLISHED
                and r["issuetype"] != "Improvement"):
            keys.add(r["key"])
            done_p1.add(r["key"])

    for r in rows:
        if r["project"] not in LATE_DRIVERS or r["key"] in done_p1:
            continue
        specs = set(s for s in (r.get("spec_areas") or "").split("|") if s)
        all_excluded = bool(specs) and specs.issubset(EXCLUDE_SPECS)
        if (r["category"] == "driver_spec_nonconformance"
                and r["issuetype"] == "Bug"
                and r["resolution"] in ("Fixed", "Done", "Completed", "Resolved")
                and r["created"][:7] >= CRUD_SPEC_PUBLISHED
                and not all_excluded):
            keys.add(r["key"])
        elif (r["category"] == "not_relevant"
                and r["issuetype"] == "Bug"
                and r["resolution"] in ("Fixed", "Done", "Completed", "Resolved")
                and r["created"][:7] >= CRUD_SPEC_PUBLISHED
                and CRUD_KEYWORDS.search(r["summary"])):
            keys.add(r["key"])

    return keys


def fetch_comments(session: requests.Session, key: str) -> list[dict]:
    url = f"{JIRA_BASE}/rest/api/2/issue/{key}?fields=comment"
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    comments = resp.json()["fields"]["comment"]["comments"]
    result = []
    for c in comments[:MAX_COMMENTS]:
        body = c.get("body") or ""
        if len(body) > MAX_COMMENT_CHARS:
            body = body[:MAX_COMMENT_CHARS] + f"\n[...truncated {len(body) - MAX_COMMENT_CHARS} chars]"
        result.append({
            "author": c.get("author", {}).get("displayName", "unknown"),
            "created": (c.get("created") or "")[:10],
            "body": body,
        })
    return result


def load_done() -> set:
    if not OUT.exists():
        return set()
    done = set()
    with OUT.open() as f:
        for line in f:
            try:
                done.add(json.loads(line)["key"])
            except (json.JSONDecodeError, KeyError):
                pass
    return done


def main():
    token = os.environ.get("JIRA_API_KEY")
    if not token:
        sys.exit("error: JIRA_API_KEY not set")

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })

    keys = candidate_keys()
    done = load_done()
    pending = sorted(keys - done)
    print(f"{len(keys)} candidate keys, {len(done)} already fetched, {len(pending)} to fetch",
          file=sys.stderr)

    fout = OUT.open("a")
    n_ok = n_err = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_comments, session, key): key for key in pending}
        for fut in as_completed(futs):
            key = futs[fut]
            try:
                comments = fut.result()
            except Exception as e:
                n_err += 1
                print(f"[err] {key}: {e}", file=sys.stderr)
                continue
            fout.write(json.dumps({"key": key, "comments": comments}) + "\n")
            fout.flush()
            n_ok += 1
            if n_ok % 50 == 0:
                print(f"  {n_ok}/{len(pending)} done, {n_err} errors", file=sys.stderr)

    fout.close()
    print(f"Done: {n_ok} fetched, {n_err} errors", file=sys.stderr)


if __name__ == "__main__":
    main()
