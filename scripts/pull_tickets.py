"""Bulk-pull resolved tickets from MongoDB Jira driver projects.

For each project, write data/tickets/<KEY>.jsonl, one ticket per line.
Idempotent: running again overwrites the file. Resume support is not
needed at this scale.

Uses ~/.jira_pat. PAT must have read access to the listed projects.
"""
import argparse
import json
import os
import time
import urllib.parse
from pathlib import Path

import requests

PAT = open(os.path.expanduser("~/.jira_pat")).read().strip()
BASE = "https://jira.mongodb.org/rest/api/2"
HEADERS = {"Authorization": f"Bearer {PAT}", "Accept": "application/json"}

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "data" / "tickets"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Driver projects in scope. Excludes MONGOCRYPT and MONGOID per Jesse.
# HASKELL/ERLANG had 0 tickets in the window so we skip them.
PROJECTS = [
    "DRIVERS",
    "PYTHON", "MOTOR",
    "JAVA", "JAVARS", "JAVARX", "SCALA",
    "NODE",
    "CSHARP",
    "GODRIVER", "MGO",
    "RUST",
    "PHPLIB", "PHPC", "PHP",
    "RUBY",
    "CDRIVER", "CXX",
    "SWIFT", "PERL",
    "HHVM",
    "SPEC",
    "DRIVERSOLD",
]
START = None  # None = no lower bound; pull all-time history
END = "2026-04-28"

# Fields we keep. resolutiondate is the standard Jira name for the
# date the resolution was set.
FIELDS = ",".join([
    "summary", "description", "issuetype", "status", "resolution",
    "created", "resolutiondate", "components", "labels", "fixVersions",
    "issuelinks", "project", "priority",
])
PAGE = 100  # Jira Server max per page on this instance


def search_page(jql: str, start_at: int) -> dict:
    url = (f"{BASE}/search?jql={urllib.parse.quote(jql)}"
           f"&maxResults={PAGE}&startAt={start_at}&fields={FIELDS}")
    for attempt in range(5):
        r = requests.get(url, headers=HEADERS, timeout=60)
        if r.status_code == 429:
            wait = int(r.headers.get("retry-after", "10"))
            time.sleep(wait + 1)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"giving up after retries: {url}")


def shrink_issue(issue: dict) -> dict:
    """Extract just the fields we need for classification + analysis."""
    f = issue["fields"]
    links = []
    for l in (f.get("issuelinks") or []):
        t = (l.get("type") or {}).get("name")
        other = l.get("outwardIssue") or l.get("inwardIssue")
        if not other:
            continue
        links.append({
            "type": t,
            "direction": "outward" if "outwardIssue" in l else "inward",
            "key": other.get("key"),
        })
    return {
        "key": issue["key"],
        "project": (f.get("project") or {}).get("key"),
        "summary": f.get("summary") or "",
        "description": f.get("description") or "",
        "issuetype": (f.get("issuetype") or {}).get("name"),
        "status": (f.get("status") or {}).get("name"),
        "resolution": (f.get("resolution") or {}).get("name"),
        "priority": (f.get("priority") or {}).get("name"),
        "created": f.get("created"),
        "resolutiondate": f.get("resolutiondate"),
        "components": [c["name"] for c in (f.get("components") or [])],
        "labels": list(f.get("labels") or []),
        "fixVersions": [v["name"] for v in (f.get("fixVersions") or [])],
        "links": links,
    }


def pull_project(project: str, types: str) -> int:
    parts = [f'project = {project}', f'issuetype in ({types})',
             'resolution in (Fixed, Done)',
             f'resolved <= "{END}"']
    if START:
        parts.append(f'resolved >= "{START}"')
    jql = " AND ".join(parts) + " ORDER BY resolved ASC"
    out = OUT_DIR / f"{project}.jsonl"
    n = 0
    start_at = 0
    with out.open("w") as fh:
        while True:
            page = search_page(jql, start_at)
            issues = page.get("issues", [])
            for issue in issues:
                fh.write(json.dumps(shrink_issue(issue)) + "\n")
                n += 1
            total = page.get("total", 0)
            start_at += len(issues)
            print(f"  {project}: {start_at}/{total}", flush=True)
            if start_at >= total or not issues:
                break
    return n


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--projects", nargs="*", default=PROJECTS,
                   help="Subset of projects to pull")
    p.add_argument("--types", default="Bug, Improvement, Task",
                   help='Jira issuetypes, e.g. "Bug, Improvement"')
    args = p.parse_args()

    grand = 0
    for proj in args.projects:
        print(f"--- {proj} ---", flush=True)
        n = pull_project(proj, args.types)
        print(f"  wrote {n} tickets to data/tickets/{proj}.jsonl", flush=True)
        grand += n
    print(f"\nTOTAL: {grand} tickets")


if __name__ == "__main__":
    main()
