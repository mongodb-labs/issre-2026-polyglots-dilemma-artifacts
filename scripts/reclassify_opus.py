"""Reclassify Jira tickets for CRUD spec analysis using Opus with prompt caching.

Three passes over 5 "late-syncing" drivers (NODE, CXX, CDRIVER, RUBY, PHPLIB):

  pass1  130 bugs already tagged crud + driver_spec_nonconformance
         Verify: is primary spec really crud? conformance_bug or initial_implementation?

  pass2  ~330 driver_spec_nonconformance Bugs (Fixed, >=2015-02) NOT tagged crud,
         after dropping tickets whose spec_areas are all in a clearly-non-CRUD exclusion list.
         False-negative hunt: did Sonnet miss a CRUD violation?

  pass3  ~140 not_relevant Bugs (Fixed, >=2015-02) with CRUD operation keywords in summary.
         False-negative hunt: did Sonnet dismiss a CRUD violation entirely?

Output: data/reclassified_opus.jsonl  (one JSON object per line, append mode)
Resumable: skips keys already present in the output file.

Requires ANTHROPIC_API_KEY in env.
"""
import csv
import json
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import anthropic

REPO = Path(__file__).resolve().parents[1]
TICKET_DIR = REPO / "data" / "tickets"
CSV_PATH = REPO / "data" / "classified_sonnet.csv"
OUT_JSONL = REPO / "data" / "reclassified_opus.jsonl"
COMMENTS_JSONL = REPO / "data" / "comments.jsonl"

MODEL = "claude-opus-4-8"
MAX_DESC_CHARS = 3000
WORKERS = 3

LATE_DRIVERS = {"NODE", "CXX", "CDRIVER", "RUBY", "PHPLIB"}
CRUD_SPEC_PUBLISHED = "2015-02"

# Spec areas that have no overlap with the CRUD spec.
# A ticket is excluded from pass2 only if ALL its spec_areas are in this set.
EXCLUDE_SPECS = {
    "sdam", "connection-string", "auth", "auth-scram", "auth-oidc",
    "auth-aws", "auth-x509", "gridfs", "change-streams", "command-monitoring",
    "csfle", "dns-seedlist", "cmap", "index-management", "retryable-reads",
    "versioned-api", "logging", "client-side-encryption",
    "server-discovery-and-monitoring", "ocsp", "compression",
    "load-balancer", "stable-api", "opentelemetry", "collation",
    "time-series", "causal-consistency",
}

CRUD_KEYWORDS = re.compile(
    r"\b(insert|update|delete|find|aggregate|replace|bulk.?write|count.?document|"
    r"estimated.?document|distinct|find.?one.?and|upsert|bulkwrite|insertOne|insertMany|"
    r"updateOne|updateMany|deleteOne|deleteMany|replaceOne|findOne)\b",
    re.IGNORECASE,
)

SYSTEM_PROMPT = """\
You are re-classifying MongoDB driver Jira tickets for a research study. The study \
measures whether adopting YAML spec tests reduces the rate of new CRUD spec \
nonconformance bugs. For each ticket you must answer three questions precisely.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUESTION 1 — primary_spec
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Choose the ONE spec whose rules are most directly violated. Options:

  crud              The CRUD spec (see scope below). Choose this only if the root
                    cause is a CRUD-spec rule violation, not another spec's rule.

  retryable-writes  Automatic retry of writes after transient failure; txnNumber
                    injection; retryWrites config; which server to use after retry.
                    Choose this if a CRUD operation fails or misbehaves because the
                    retry machinery is broken, not because the CRUD result shape is wrong.

  retryable-reads   Automatic retry of reads; retryReads config.

  transactions      startTransaction / commitTransaction / abortTransaction lifecycle;
                    transaction state machine; behavior governed by transaction rules
                    (e.g. batch-splitting that increments txnNumber inside a transaction).
                    Choose this if a CRUD operation fails inside a transaction because
                    transaction-level invariants are violated.

  server-selection  Which server the driver routes a given operation to; read-preference
                    modes; routing aggregate-with-$out to primary. Choose this if the
                    bug is that the driver sends a query/write to the wrong server.

  write-concern     How the driver constructs and sends the write concern document TO
                    the server (w, j, wtimeout fields). If the bug is about the driver
                    sending a malformed writeConcern field to the server, that is
                    write-concern.
                    *** CRITICAL DISTINCTION: if the bug is about the driver NOT
                    SURFACING a WriteConcernError (or writeConcernErrors) inside the
                    CRUD result object (BulkWriteResult, findOneAndModify result, etc.)
                    that is CRUD, not write-concern. The CRUD spec defines what fields
                    the result object must contain; failing to populate writeConcernErrors
                    in a result is a CRUD result-shape violation. ***

  sessions          Session handling, lsid attachment, causal consistency.

  bson              BSON binary serialization/deserialization. Choose this if the bug is
                    about how a document value is encoded or decoded, not about CRUD API
                    shape or semantics.

  cursors           getMore, killCursors, cursor lifetime mechanics. Note: find() and
                    aggregate() return cursors, but those operations' required options
                    and result shapes are CRUD spec. Choose cursors only if the bug is
                    specifically about cursor iteration, batch sizing on getMore, or
                    cursor exhaustion---not about the initial find/aggregate call shape.

  find-getmore-killcursors
                    Wire-level format of the OP_MSG find / getMore / killCursors
                    commands: required field names, type constraints (e.g. batchSize
                    MUST be int64 not int32 in the wire command), which fields are
                    allowed or prohibited in the command document. This spec governs
                    the MongoDB wire protocol encoding, NOT the high-level
                    Collection.find() API shape covered by the CRUD spec. Choose this
                    if the bug is about how the driver constructs the find or getMore
                    wire command, not about the caller-visible result or option API.

  bulk-write        MongoClient.bulkWrite() introduced in MongoDB 8.0 (new 2024 API).
                    Do NOT use this for Collection.bulkWrite(), which is crud.

  other             Any other spec not listed above.

  not_a_bug         Ticket is not a driver spec nonconformance at all (build issue,
                    doc update, performance, internal refactor, etc.).

CRUD spec scope — choose "crud" if the bug is about:
  • Collection read operations: find(), findOne(), aggregate(), countDocuments(),
    estimatedDocumentCount(), distinct() — their required options, option semantics,
    and result shapes.
  • Collection write operations: insertOne(), insertMany(), updateOne(), updateMany(),
    replaceOne(), deleteOne(), deleteMany() — their options, validation rules,
    and result types.
  • findOneAndDelete(), findOneAndReplace(), findOneAndUpdate() — options and results.
  • Collection.bulkWrite() — write models accepted, options, and the BulkWriteResult
    shape (insertedCount, matchedCount, modifiedCount, deletedCount, upsertedCount,
    upsertedIds, writeErrors, writeConcernErrors and their field types).
  • Result type field names and types: InsertOneResult.insertedId,
    InsertManyResult.insertedIds, UpdateResult.matchedCount / modifiedCount /
    upsertedId / upsertedCount, DeleteResult.deletedCount.
  • WriteError and WriteConcernError objects as returned inside CRUD results.
  • _id generation: driver MUST generate and prepend _id if document lacks one.
  • Update document validation: updateOne/updateMany require atomic operators ($set,
    $inc, etc.); replaceOne prohibits atomic operators.
  • Optional parameter semantics: don't send optional fields to the server unless
    the user explicitly provided them.

NOT in CRUD spec scope — do NOT choose "crud" for:
  • Legacy pre-CRUD-spec driver APIs: mongoc_collection_update(),
    mongoc_collection_find(), mongoc_collection_insert(), the C driver's
    mongoc_bulk_operation_update() family, or the Ruby/Node legacy update()
    method. The CRUD spec defines new methods (updateOne, updateMany, etc.);
    bugs in the old APIs are not CRUD spec nonconformances.
  • Language-specific input handling: whether a driver validates or transforms
    arbitrary language objects before passing them to a CRUD operation (e.g.
    whether Node.js calls toBSON() on non-BSON input to bulkWrite). The CRUD
    spec defines the API interface, options, and result shapes — not how
    drivers handle language-level input coercion.
  • Wire-level command format of find/getMore/killCursors commands (use
    find-getmore-killcursors instead).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUESTION 2 — bug_type  (answer only when primary_spec == "crud")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  conformance_bug        The driver had an implementation of the operation but it
                         behaved incorrectly vs. the spec. The wrong behavior
                         already existed; this ticket corrects it.
                         Clues: "returns wrong value", "ignores option X",
                         "should raise error but doesn't", "incorrect count",
                         "missing field in result".

  initial_implementation The spec-required operation or feature was entirely absent
                         from the driver. This ticket adds it for the first time.
                         Clues: "Make #X a method on Collection", "Add #aggregate
                         as method", "Implement UpdateResult::getUpsertedCount()",
                         "Support X option" where X never existed before.
                         A YAML test for this feature would not have "caught" a bug
                         in existing code — there was no code. YAML tests would have
                         driven the implementation instead.

  unclear                Cannot determine from available information.

  not_applicable         primary_spec is not "crud" — skip this field.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUESTION 3 — confidence
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  high     Clear signal in summary + description.
  medium   Reasonable inference, some ambiguity.
  low      Thin description, weak signal, or genuine uncertainty.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Output ONLY a single JSON object on one line, no markdown, no preamble:

{"key": "<KEY>", "primary_spec": "<spec>", "bug_type": "<type>", \
"confidence": "<conf>", "rationale": "<1-2 sentences citing specific evidence>"}
"""


def load_ticket_index() -> dict:
    index = {}
    for jsonl in TICKET_DIR.glob("*.jsonl"):
        with jsonl.open() as f:
            for line in f:
                t = json.loads(line)
                index[t["key"]] = t
    if COMMENTS_JSONL.exists():
        with COMMENTS_JSONL.open() as f:
            for line in f:
                try:
                    r = json.loads(line)
                    if r["key"] in index:
                        index[r["key"]]["comments"] = r["comments"]
                except (json.JSONDecodeError, KeyError):
                    pass
    return index


def load_classified() -> list[dict]:
    with CSV_PATH.open() as f:
        return list(csv.DictReader(f))


def load_done() -> set:
    if not OUT_JSONL.exists():
        return set()
    done = set()
    with OUT_JSONL.open() as f:
        for line in f:
            try:
                done.add(json.loads(line)["key"])
            except (json.JSONDecodeError, KeyError):
                pass
    return done


def _specs(r: dict) -> set:
    return set(s for s in (r.get("spec_areas") or "").split("|") if s)


def build_candidates(rows: list[dict]) -> list[tuple[int, dict]]:
    """Return (pass_num, csv_row) pairs for all three passes, pass1 first."""
    result = []
    done_keys: set[str] = set()

    for r in rows:
        if r["project"] not in LATE_DRIVERS:
            continue
        specs = _specs(r)
        key = r["key"]

        # Pass 1: already tagged crud + nonconformance, within the analysis window.
        # Exclude Improvements: if Jira says Improvement it's adoption work, not a bug.
        # Some Bug-typed tickets are also initial implementations; Opus catches those.
        if (r["category"] == "driver_spec_nonconformance"
                and "crud" in specs
                and r["created"][:7] >= CRUD_SPEC_PUBLISHED
                and r["issuetype"] != "Improvement"):
            result.append((1, r))
            done_keys.add(key)

    for r in rows:
        if r["project"] not in LATE_DRIVERS or r["key"] in done_keys:
            continue
        specs = _specs(r)
        key = r["key"]

        # Pass 2: other driver_spec_nonconformance Bugs, not obviously non-CRUD
        all_excluded = bool(specs) and specs.issubset(EXCLUDE_SPECS)
        if (r["category"] == "driver_spec_nonconformance"
                and r["issuetype"] == "Bug"
                and r["resolution"] in ("Fixed", "Done", "Completed", "Resolved")
                and r["created"][:7] >= CRUD_SPEC_PUBLISHED
                and not all_excluded):
            result.append((2, r))
            done_keys.add(key)

        # Pass 3: not_relevant Bugs with CRUD keywords in summary
        elif (r["category"] == "not_relevant"
                and r["issuetype"] == "Bug"
                and r["resolution"] in ("Fixed", "Done", "Completed", "Resolved")
                and r["created"][:7] >= CRUD_SPEC_PUBLISHED
                and CRUD_KEYWORDS.search(r["summary"])):
            result.append((3, r))
            done_keys.add(key)

    return result


def truncate(s: str, n: int) -> str:
    if not s:
        return ""
    return s if len(s) <= n else s[:n] + f"\n[... truncated {len(s) - n} chars]"


def build_user_msg(ticket: dict, csv_row: dict, pass_num: int) -> str:
    pass_context = {
        1: (
            "Sonnet tagged this as CRUD nonconformance. Your task: verify whether "
            "primary_spec is really 'crud' (vs. another spec whose rule is the root "
            "cause), and determine bug_type."
        ),
        2: (
            f"Sonnet tagged this as {csv_row['category']} "
            f"(spec_areas: {csv_row.get('spec_areas') or 'none'}), NOT as crud. "
            "Your task: determine whether this is actually a CRUD spec nonconformance "
            "that Sonnet missed."
        ),
        3: (
            "Sonnet tagged this as not_relevant. Your task: determine whether this is "
            "a CRUD spec nonconformance bug that Sonnet dismissed incorrectly."
        ),
    }[pass_num]

    links = ticket.get("links") or []
    link_str = (
        ", ".join(
            f"{lnk['type']} {lnk['direction']}: {lnk['key']}"
            for lnk in links[:10]
        )
        or "(none)"
    )

    comments = ticket.get("comments") or []
    if comments:
        comment_lines = ["", "--- COMMENTS ---"]
        for c in comments:
            comment_lines.append(
                f"[{c.get('created', '')} {c.get('author', '')}] {c.get('body', '')}"
            )
        comment_block = "\n".join(comment_lines)
    else:
        comment_block = ""

    return "\n".join([
        f"PASS {pass_num}: {pass_context}",
        "",
        f"PRIOR CLASSIFICATION — category: {csv_row.get('category')}, "
        f"spec_areas: {csv_row.get('spec_areas') or 'none'}, "
        f"confidence: {csv_row.get('confidence')}",
        f"PRIOR RATIONALE: {csv_row.get('rationale', '(none)')}",
        "",
        "--- TICKET ---",
        f"key: {ticket['key']}",
        f"project: {ticket['project']}",
        f"issuetype: {ticket.get('issuetype')}",
        f"resolution: {ticket.get('resolution')}",
        f"created: {(ticket.get('created') or '')[:10]}",
        f"links: {link_str}",
        f"summary: {ticket['summary']}",
        "description:",
        truncate(ticket.get("description") or "(empty)", MAX_DESC_CHARS),
        comment_block,
    ])


def classify_one(
    client: anthropic.Anthropic,
    system_blocks: list,
    ticket: dict,
    csv_row: dict,
    pass_num: int,
) -> dict:
    user_msg = build_user_msg(ticket, csv_row, pass_num)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=system_blocks,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON in response: {text[:200]}")
    result = json.loads(text[start : end + 1])
    result["pass"] = pass_num
    return result


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="Stop after N tickets (for smoke testing)")
    ap.add_argument("--pass", dest="only_pass", type=int, default=None, choices=[1, 2, 3],
                    help="Run only this pass")
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("error: ANTHROPIC_API_KEY not set")
    client = anthropic.Anthropic()
    system_blocks = [
        {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
    ]

    print("Loading ticket index...", file=sys.stderr)
    ticket_index = load_ticket_index()
    print(f"  {len(ticket_index)} tickets indexed", file=sys.stderr)

    print("Loading classified CSV...", file=sys.stderr)
    rows = load_classified()
    csv_by_key = {r["key"]: r for r in rows}

    candidates = build_candidates(rows)
    if args.only_pass:
        candidates = [(p, r) for p, r in candidates if p == args.only_pass]
    pass_counts = Counter(p for p, _ in candidates)
    print(
        f"Candidates: pass1={pass_counts[1]}, pass2={pass_counts[2]}, "
        f"pass3={pass_counts[3]}, total={len(candidates)}",
        file=sys.stderr,
    )

    done = load_done()
    print(f"Already done: {len(done)}", file=sys.stderr)

    pending: list[tuple[int, dict, dict]] = []
    for pass_num, csv_row in candidates:
        key = csv_row["key"]
        if key in done:
            continue
        if key not in ticket_index:
            print(f"[warn] {key} not in ticket index, skipping", file=sys.stderr)
            continue
        pending.append((pass_num, csv_row, ticket_index[key]))

    if args.limit:
        pending = pending[: args.limit]
    print(f"To classify: {len(pending)}", file=sys.stderr)

    fout = OUT_JSONL.open("a")
    n_done = n_err = 0
    start_t = time.time()

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {
            ex.submit(classify_one, client, system_blocks, ticket, csv_row, pass_num): ticket["key"]
            for pass_num, csv_row, ticket in pending
        }
        for fut in as_completed(futs):
            key = futs[fut]
            try:
                result = fut.result()
            except Exception as e:
                n_err += 1
                print(f"[err] {key}: {type(e).__name__}: {e}", file=sys.stderr)
                continue
            fout.write(json.dumps(result) + "\n")
            fout.flush()
            n_done += 1
            if n_done % 25 == 0:
                elapsed = time.time() - start_t
                rate = n_done / max(elapsed, 0.001)
                print(
                    f"  {n_done}/{len(pending)} done, {n_err} errors, "
                    f"{rate:.2f}/s, elapsed {elapsed:.0f}s",
                    file=sys.stderr,
                )

    fout.close()
    print(f"\nDone: {n_done} classified, {n_err} errors", file=sys.stderr)


if __name__ == "__main__":
    main()
