"""Classify pulled Jira tickets via Sonnet for the full re-run.

Reads data/tickets/*.jsonl, calls Sonnet per ticket with the current
classify.md prompt, writes data/classified_sonnet.csv.

Resumable: skips keys already present in the output CSV.
Requires ANTHROPIC_API_KEY in env.
"""
import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import anthropic

REPO = Path(__file__).resolve().parents[1]
TICKET_DIR = REPO / "data" / "tickets"
PROMPT_PATH = REPO / "prompts" / "classify.md"
OUT_CSV = REPO / "data" / "classified_sonnet.csv"

MODEL = "claude-sonnet-4-6"
MAX_DESC_CHARS = 4000
COLUMNS = [
    "key", "project", "issuetype", "resolution", "priority",
    "created", "resolutiondate",
    "summary",
    "category", "spec_areas", "is_nonconformance", "mentions_other_driver",
    "preventable_by_yaml_test", "confidence", "rationale",
    "components", "labels", "fix_versions", "links",
    "url",
]


def truncate(s: str, n: int) -> str:
    if not s:
        return ""
    return s if len(s) <= n else s[:n] + f"\n[... truncated {len(s)-n} chars]"


def ticket_to_user_msg(t: dict) -> str:
    parts = [
        f"key: {t['key']}",
        f"project: {t['project']}",
        f"issuetype: {t['issuetype']}",
        f"resolution: {t.get('resolution')}",
        f"priority: {t.get('priority')}",
        f"created: {(t.get('created') or '')[:10]}",
        f"resolved: {(t.get('resolutiondate') or '')[:10]}",
        f"components: {', '.join(t.get('components') or []) or '(none)'}",
        f"labels: {', '.join(t.get('labels') or []) or '(none)'}",
        f"fix_versions: {', '.join(t.get('fixVersions') or []) or '(none)'}",
    ]
    links = t.get("links") or []
    if links:
        parts.append("links:")
        for lnk in links[:20]:
            parts.append(f"  - {lnk['type']} {lnk['direction']}: {lnk['key']}")
    parts.append(f"summary: {t['summary']}")
    parts.append("description:")
    parts.append(truncate(t.get("description") or "(empty)", MAX_DESC_CHARS))
    return "\n".join(parts)


def parse_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON object in response: {text[:200]}")
    return json.loads(text[start:end+1])


def classify_one(client: anthropic.Anthropic, system: str, ticket: dict) -> dict:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=500,
        system=system,
        messages=[{"role": "user", "content": ticket_to_user_msg(ticket)}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    return parse_response(text)


def already_done(out_csv: Path) -> set:
    if not out_csv.exists():
        return set()
    with out_csv.open() as f:
        return {row["key"] for row in csv.DictReader(f)}


def iter_tickets(projects):
    for proj in projects:
        path = TICKET_DIR / f"{proj}.jsonl"
        if not path.exists():
            print(f"[skip] no file for {proj}", file=sys.stderr)
            continue
        with path.open() as f:
            for line in f:
                yield json.loads(line)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--projects", nargs="*", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--workers", type=int, default=12)
    args = p.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("error: ANTHROPIC_API_KEY not set")

    if args.projects is None:
        args.projects = sorted(p.stem for p in TICKET_DIR.glob("*.jsonl"))

    system = PROMPT_PATH.read_text()
    client = anthropic.Anthropic()

    done = already_done(OUT_CSV)
    print(f"already classified: {len(done)}", file=sys.stderr)

    write_header = not OUT_CSV.exists()
    fout = OUT_CSV.open("a", newline="")
    writer = csv.DictWriter(fout, fieldnames=COLUMNS)
    if write_header:
        writer.writeheader()

    pending = []
    for ticket in iter_tickets(args.projects):
        if ticket["key"] in done:
            continue
        if args.limit and len(pending) >= args.limit:
            break
        pending.append(ticket)

    print(f"to classify: {len(pending)}", file=sys.stderr)

    n_done = n_err = 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(classify_one, client, system, t): t for t in pending}
        for fut in as_completed(futs):
            t = futs[fut]
            try:
                result = fut.result()
            except Exception as e:
                n_err += 1
                print(f"[err] {t['key']}: {type(e).__name__}: {e}", file=sys.stderr)
                continue
            spec_areas = result.get("spec_areas") or []
            if isinstance(spec_areas, list):
                spec_areas = "|".join(spec_areas)
            row = {
                "key": t["key"],
                "project": t["project"],
                "issuetype": t.get("issuetype"),
                "resolution": t.get("resolution"),
                "priority": t.get("priority"),
                "created": (t.get("created") or "")[:10],
                "resolutiondate": (t.get("resolutiondate") or "")[:10],
                "summary": t.get("summary", ""),
                "category": result.get("category"),
                "spec_areas": spec_areas,
                "is_nonconformance": result.get("is_nonconformance"),
                "mentions_other_driver": result.get("mentions_other_driver"),
                "preventable_by_yaml_test": result.get("preventable_by_yaml_test"),
                "confidence": result.get("confidence"),
                "rationale": result.get("rationale"),
                "components": "|".join(t.get("components") or []),
                "labels": "|".join(t.get("labels") or []),
                "fix_versions": "|".join(t.get("fixVersions") or []),
                "links": "|".join(
                    f"{lnk['type']}:{lnk['key']}" for lnk in t.get("links") or []
                ),
                "url": f"https://jira.mongodb.org/browse/{t['key']}",
            }
            writer.writerow(row)
            fout.flush()
            n_done += 1
            if n_done % 100 == 0:
                rate = n_done / max(time.time() - start, 0.001)
                print(f"  classified {n_done}/{len(pending)}, errors {n_err}, "
                      f"{rate:.1f}/s", file=sys.stderr)

    fout.close()
    print(f"\ndone: {n_done} classified, {n_err} errors", file=sys.stderr)


if __name__ == "__main__":
    main()
