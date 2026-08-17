"""Count resolved tickets per driver project in the paper's timeframe.

Run before bulk-pulling, to plan scale. Uses ~/.jira_pat.
"""
import os
import sys
import urllib.parse

import requests

PAT = open(os.path.expanduser("~/.jira_pat")).read().strip()
BASE = "https://jira.mongodb.org/rest/api/2"
HEADERS = {"Authorization": f"Bearer {PAT}", "Accept": "application/json"}

# Driver-related projects from /rest/api/2/project. MONGOCRYPT and MONGOID
# excluded per Jesse's instruction.
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
    "HASKELL", "ERLANG", "HHVM",
    "SPEC",
    "DRIVERSOLD",
]
START = None  # None = no lower bound; pull all-time history
END = "2026-04-28"


def count(jql: str) -> int:
    url = f"{BASE}/search?jql={urllib.parse.quote(jql)}&maxResults=0"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()["total"]


def _date_clause():
    parts = [f'resolved <= "{END}"']
    if START:
        parts.append(f'resolved >= "{START}"')
    return " AND ".join(parts)


def main():
    print(f"Window: {START or '(no lower bound)'} → {END}\n")
    print(f"{'KEY':12s}  {'BUGS':>6s}  {'BUG+IMPROVE':>11s}  {'ALL_RESOLVED':>12s}")
    totals = {"bug": 0, "bug+imp": 0, "all": 0}
    dc = _date_clause()
    for key in PROJECTS:
        try:
            bug = count(
                f'project = {key} AND issuetype = Bug AND '
                f'resolution in (Fixed, Done) AND {dc}'
            )
            bug_imp = count(
                f'project = {key} AND issuetype in (Bug, Improvement) AND '
                f'resolution in (Fixed, Done) AND {dc}'
            )
            all_resolved = count(
                f'project = {key} AND resolution in (Fixed, Done) AND {dc}'
            )
        except requests.HTTPError as e:
            print(f"{key:12s}  ERROR  {e.response.status_code}: {e.response.text[:120]}")
            continue
        print(f"{key:12s}  {bug:>6d}  {bug_imp:>11d}  {all_resolved:>12d}")
        totals["bug"] += bug
        totals["bug+imp"] += bug_imp
        totals["all"] += all_resolved
    print()
    print(f"{'TOTAL':12s}  {totals['bug']:>6d}  {totals['bug+imp']:>11d}  {totals['all']:>12d}")


if __name__ == "__main__":
    main()
