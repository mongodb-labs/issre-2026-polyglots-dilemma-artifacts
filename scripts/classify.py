"""Classify pulled Jira tickets via the Anthropic API (Haiku).

Reads data/tickets/*.jsonl, calls Haiku per ticket with the prompt at
prompts/classify.md, writes data/classified.csv.

Resumable: skips ticket keys already present in classified.csv.
Idempotent: re-running picks up where it left off.

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
OUT_CSV = REPO / "data" / "classified.csv"

MODEL = "claude-haiku-4-5"
MAX_DESC_CHARS = 4000  # truncate long descriptions to keep cost predictable
COLUMNS = [
    "key", "project", "issuetype", "resolution", "priority",
    "created", "resolutiondate",
    "summary",
    "category", "spec_area", "mentions_other_driver", "confidence",
    "rationale",
    "components", "labels", "fix_versions", "links",
    "url",
]


def load_prompt() -> str:
    return PROMPT_PATH.read_text()


def truncate(s: str, n: int) -> str:
    if not s:
        return ""
    return s if len(s) <= n else s[:n] + f"\n[... truncated {len(s)-n} chars]"


def ticket_to_user_msg(t: dict) -> str:
    """Render a ticket as the user message."""
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
        for l in links[:20]:
            parts.append(f"  - {l['type']} {l['direction']}: {l['key']}")
    parts.append(f"summary: {t['summary']}")
    parts.append("description:")
    parts.append(truncate(t.get("description") or "(empty)", MAX_DESC_CHARS))
    return "\n".join(parts)


def parse_response(text: str) -> dict:
    """Extract the JSON object from the model output."""
    text = text.strip()
    # Strip code fence if model wrapped despite instruction.
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    # Find first { and last } to be tolerant.
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON object in response: {text[:200]}")
    return json.loads(text[start:end+1])


def classify_one(client: anthropic.Anthropic, system: str, ticket: dict) -> dict:
    user = ticket_to_user_msg(ticket)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=400,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    return parse_response(text)


def already_done(out_csv: Path) -> set:
    if not out_csv.exists():
        return set()
    done = set()
    with out_csv.open() as f:
        r = csv.DictReader(f)
        for row in r:
            done.add(row["key"])
    return done


def iter_tickets(projects):
    for proj in projects:
        path = TICKET_DIR / f"{proj}.jsonl"
        if not path.exists():
            print(f"[skip] no file for {proj}", file=sys.stderr)
            continue
        with path.open() as f:
            for line in f:
                yield json.loads(line)


def jira_url(key: str) -> str:
    return f"https://jira.mongodb.org/browse/{key}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--projects", nargs="*", default=None,
                   help="Subset of projects (default: all .jsonl files)")
    p.add_argument("--limit", type=int, default=None,
                   help="Stop after N tickets (for smoke testing)")
    p.add_argument("--workers", type=int, default=8,
                   help="Concurrent API requests")
    args = p.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("error: ANTHROPIC_API_KEY not set")

    if args.projects is None:
        args.projects = sorted(p.stem for p in TICKET_DIR.glob("*.jsonl"))

    system = load_prompt()
    client = anthropic.Anthropic()

    done = already_done(OUT_CSV)
    print(f"already classified: {len(done)} tickets", file=sys.stderr)

    write_header = not OUT_CSV.exists()
    fout = OUT_CSV.open("a", newline="")
    writer = csv.DictWriter(fout, fieldnames=COLUMNS)
    if write_header:
        writer.writeheader()

    n_done = 0
    n_err = 0
    start = time.time()
    pending = []
    for ticket in iter_tickets(args.projects):
        if ticket["key"] in done:
            continue
        if args.limit and (n_done + len(pending)) >= args.limit:
            break
        pending.append(ticket)

    print(f"to classify: {len(pending)}", file=sys.stderr)

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
                "spec_area": result.get("spec_area"),
                "mentions_other_driver": result.get("mentions_other_driver"),
                "confidence": result.get("confidence"),
                "rationale": result.get("rationale"),
                "components": "|".join(t.get("components") or []),
                "labels": "|".join(t.get("labels") or []),
                "fix_versions": "|".join(t.get("fixVersions") or []),
                "links": "|".join(f"{l['type']}:{l['key']}" for l in t.get("links") or []),
                "url": jira_url(t["key"]),
            }
            writer.writerow(row)
            fout.flush()
            n_done += 1
            if n_done % 50 == 0:
                rate = n_done / max(time.time() - start, 0.001)
                print(f"  classified {n_done}, errors {n_err}, "
                      f"{rate:.1f}/s", file=sys.stderr)

    fout.close()
    print(f"\ndone: {n_done} classified, {n_err} errors", file=sys.stderr)


if __name__ == "__main__":
    main()
