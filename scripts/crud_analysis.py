"""CRUD-focused analysis: do YAML spec tests reduce nonconformance bug rates?

Reads:
  - data/classified_sonnet.csv (LLM-classified tickets)
  - data/drivers_timeline.csv (per-driver monthly YAML/JSON file counts)
  - data/drivers_submodule_timeline.csv (for JAVA, GODRIVER, PHPLIB)

Outputs:
  - data/crud_panel.csv (driver × month panel, CRUD only)
  - data/plots/crud_late5.png/.pdf  pre/post bug-rate chart for 5 late-syncing drivers
  - prints per-driver summary to stdout

Analysis approach
-----------------
The 5 "late-syncing" drivers (NODE, CXX, CDRIVER, RUBY, PHPLIB) all adopted CRUD
YAML tests after the CRUD spec was already published (Feb 2015).  For each of these
drivers the pre-sync window ("spec published, no YAML tests") and the post-sync
window ("spec plus YAML tests") both start after the spec existed, so the comparison
isolates the effect of the tests rather than the effect of the spec itself.

The 4 early-syncing drivers (CSHARP, JAVA, PERL, PYTHON --- all synced 2015-03)
are excluded from this comparison: they adopted tests almost simultaneously with
the spec publication, leaving only one month of post-spec pre-sync history.
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DATA = Path(__file__).resolve().parents[1] / "data"
PLOT_DIR = DATA / "plots"
OPUS_JSONL = DATA / "reclassified_opus.jsonl"

DRIVERS = ["CDRIVER", "CSHARP", "CXX", "GODRIVER", "JAVA", "NODE",
           "PERL", "PHPLIB", "PYTHON", "RUBY", "RUST", "SWIFT"]
SUBMODULE_DRIVERS = {"JAVA", "GODRIVER", "PHPLIB"}

# 5 late-syncing drivers: synced CRUD YAML tests after the CRUD spec was published,
# giving a clean pre/post comparison window.
LATE_DRIVERS = {"NODE", "CXX", "CDRIVER", "RUBY", "PHPLIB"}
LATE_LABELS = {"NODE": "Node.js", "CXX": "C++", "CDRIVER": "C", "RUBY": "Ruby", "PHPLIB": "PHP"}
CRUD_SPEC_PUBLISHED = "2015-02"

SPEC_ALIASES = {"bson": "bson-corpus", "sdam": "server-discovery-and-monitoring"}


def load_opus_overlay() -> dict:
    """Return {key: result_dict} from reclassified_opus.jsonl, or {} if absent."""
    if not OPUS_JSONL.exists():
        return {}
    overlay = {}
    with OPUS_JSONL.open() as f:
        for line in f:
            try:
                r = json.loads(line)
                overlay[r["key"]] = r
            except (json.JSONDecodeError, KeyError):
                pass
    return overlay


def month_index(m):
    y, mo = int(m[:4]), int(m[5:7])
    return (y - 2000) * 12 + (mo - 1)


def load_crud_bugs(opus_overlay: dict | None = None) -> dict:
    """Return {(driver, month): n_bugs}.

    When opus_overlay is provided (keyed by Jira key), it overrides Sonnet's
    classification for any ticket it covers.  A ticket counts as a CRUD bug iff:
      - It appears in opus_overlay with primary_spec=="crud" and
        bug_type=="conformance_bug"  (Opus-reviewed tickets), OR
      - It does NOT appear in the overlay, has category==driver_spec_nonconformance,
        and "crud" in spec_areas  (Sonnet-only tickets, typically other drivers).
    This lets pass-1 bugs be downgraded and pass-2/3 false-negatives be added.
    """
    if opus_overlay is None:
        opus_overlay = {}

    counts = defaultdict(int)
    with (DATA / "classified_sonnet.csv").open() as f:
        for r in csv.DictReader(f):
            project = r["project"]
            if project not in DRIVERS:
                continue
            created = r.get("created", "")
            if not created or len(created) < 7:
                continue
            key = r["key"]

            if key in opus_overlay:
                opus = opus_overlay[key]
                if (opus.get("primary_spec") == "crud"
                        and opus.get("bug_type") == "conformance_bug"):
                    counts[(project, created[:7])] += 1
            else:
                if r["category"] != "driver_spec_nonconformance":
                    continue
                specs = [SPEC_ALIASES.get(s, s)
                         for s in (r.get("spec_areas") or "").split("|") if s]
                if "crud" in specs:
                    counts[(project, created[:7])] += 1

    return counts


def load_crud_assets():
    """Returns {(driver, month): (n_files, n_lines)}."""
    assets = {}
    with (DATA / "drivers_timeline.csv").open() as f:
        for r in csv.DictReader(f):
            if r["spec"] != "crud" or r["driver"] not in DRIVERS:
                continue
            key = (r["driver"], r["month"])
            assets[key] = (int(r["n_files"]), int(r["n_lines"]))
    with (DATA / "drivers_submodule_timeline.csv").open() as f:
        for r in csv.DictReader(f):
            if r["spec"] != "crud" or r["driver"] not in SUBMODULE_DRIVERS:
                continue
            key = (r["driver"], r["month"])
            sub_f, sub_l = int(r["n_files"]), int(r["n_lines"])
            existing = assets.get(key, (0, 0))
            assets[key] = (max(existing[0], sub_f), max(existing[1], sub_l))
    return assets


def load_driver_active_range():
    months = defaultdict(list)
    with (DATA / "classified_sonnet.csv").open() as f:
        for r in csv.DictReader(f):
            created = r.get("created", "")
            if created and len(created) >= 7 and r["project"] in DRIVERS:
                months[r["project"]].append(created[:7])
    return {d: (min(ms), max(ms)) for d, ms in months.items()}


def month_iter(start, end):
    sy, sm = int(start[:4]), int(start[5:7])
    ey, em = int(end[:4]), int(end[5:7])
    y, m = sy, sm
    while (y, m) <= (ey, em):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m > 12:
            m = 1
            y += 1


def build_panel(bugs, assets, ranges):
    rows = []
    for driver in DRIVERS:
        if driver not in ranges:
            continue
        first, last = ranges[driver]
        for month in month_iter(first, last):
            n_files, n_lines = assets.get((driver, month), (0, 0))
            n_bugs = bugs.get((driver, month), 0)
            rows.append({
                "driver": driver, "month": month,
                "n_bugs": n_bugs, "n_files": n_files, "n_lines": n_lines,
            })
    return rows


def first_sync(panel_by_driver, driver):
    for r in panel_by_driver[driver]:
        if r["n_files"] > 0:
            return r["month"]
    return None


def chart_late5(panel_by_driver):
    """Pre/post CRUD bug-rate chart for the 5 late-syncing drivers.

    Pre-sync window: CRUD spec publication (2015-02) through each driver's sync month.
    Post-sync window: sync month onwards.
    Both windows have the published CRUD spec; the only difference is YAML test presence.
    NODE is an outlier (post-sync rate higher) driven by a BulkWrite result-shape
    conformance cluster (2019--2022) that YAML tests do not catch because they validate
    wire protocol, not language-level result object structure.
    """
    sync_dates = {d: first_sync(panel_by_driver, d) for d in LATE_DRIVERS}
    drivers_ordered = sorted(LATE_DRIVERS, key=lambda d: sync_dates[d])

    pre_rates, post_rates, pre_mo, post_mo = {}, {}, {}, {}
    pre_bugs, post_bugs = {}, {}
    for d in drivers_ordered:
        pre = [r for r in panel_by_driver[d]
               if r["month"] >= CRUD_SPEC_PUBLISHED and r["month"] < sync_dates[d]]
        post = [r for r in panel_by_driver[d] if r["month"] >= sync_dates[d]]
        pb, pm = sum(r["n_bugs"] for r in pre), len(pre)
        ob, om = sum(r["n_bugs"] for r in post), len(post)
        pre_rates[d] = pb / pm * 12 if pm else 0
        post_rates[d] = ob / om * 12 if om else 0
        pre_mo[d], post_mo[d] = pm, om
        pre_bugs[d], post_bugs[d] = pb, ob

    # Reverse so earliest adopter (Node.js) is at top
    drivers_ordered = list(reversed(drivers_ordered))

    y = np.arange(len(drivers_ordered))
    height = 0.35

    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman"],
        "pdf.fonttype": 42,
    })
    fig, ax = plt.subplots(figsize=(9, 8))
    ax.barh(y + height / 2,
            [pre_rates[d] for d in drivers_ordered],
            height, label="Pre-adoption (no YAML tests)",
            color="#d62728", alpha=0.85)
    bars_post = ax.barh(y - height / 2,
                        [post_rates[d] for d in drivers_ordered],
                        height, label="Post-adoption (YAML tests)",
                        color="#1f77b4", alpha=0.85)

    max_rate = max(list(pre_rates.values()) + list(post_rates.values()))
    ax.set_xlim(0, max_rate * 1.9)

    def bugs_label(n):
        return f"{n} bug" if n == 1 else f"{n} bugs"

    for yi, d in zip(y, drivers_ordered):
        v = pre_rates[d]
        ax.text(v + max_rate * 0.03, yi + height / 2,
                f"{v:.1f} ({bugs_label(pre_bugs[d])} in {pre_mo[d] / 12:.1f} years)",
                va="center", fontsize=18)
    for bar, d in zip(bars_post, drivers_ordered):
        v = post_rates[d]
        chg = (v - pre_rates[d]) / pre_rates[d] * 100 if pre_rates[d] else 0
        ax.text(v + max_rate * 0.03, bar.get_y() + bar.get_height() / 2,
                f"{v:.1f} ({bugs_label(post_bugs[d])} in {post_mo[d] / 12:.1f} years, {chg:+.0f}%)",
                va="center", fontsize=18)

    ax.set_yticks(y)
    ax.set_yticklabels(
        [f"{LATE_LABELS[d]}\n({sync_dates[d]})" for d in drivers_ordered],
        fontsize=24)
    ax.set_xlabel("CRUD nonconformance bugs / year", fontsize=24)
    ax.tick_params(axis="x", labelsize=24)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.15),
              ncol=1, fontsize=20)
    ax.grid(True, alpha=0.3, axis="x")
    plt.tight_layout()
    plt.subplots_adjust(bottom=0.30)
    plt.savefig(PLOT_DIR / "crud_late5.pdf")
    plt.savefig(PLOT_DIR / "crud_late5.png", dpi=120)
    plt.close()


def main():
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    opus_overlay = load_opus_overlay()
    if opus_overlay:
        print(f"Opus overlay loaded: {len(opus_overlay)} tickets")
    else:
        print("No Opus overlay found; using Sonnet classifications only")

    print("Loading CRUD bugs from classified_sonnet.csv...")
    bugs = load_crud_bugs(opus_overlay)
    total_bugs = sum(bugs.values())
    print(f"  {total_bugs} CRUD nonconformance bugs across {len(set(d for d, m in bugs))} drivers")

    print("Loading CRUD test assets...")
    assets = load_crud_assets()
    print(f"  {len(assets)} (driver, month) cells with CRUD test files")

    print("Loading driver active ranges...")
    ranges = load_driver_active_range()

    print("Building CRUD panel...")
    panel = build_panel(bugs, assets, ranges)
    print(f"  {len(panel)} total (driver, month) cells")

    out = DATA / "crud_panel.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["driver", "month", "n_bugs", "n_files", "n_lines"])
        w.writeheader()
        w.writerows(panel)
    print(f"  wrote {out}")

    panel_by_driver = defaultdict(list)
    for r in panel:
        panel_by_driver[r["driver"]].append(r)
    for d in panel_by_driver:
        panel_by_driver[d].sort(key=lambda r: r["month"])

    print("\n=== Per-driver summary (all pre-sync vs all post-sync) ===\n")
    print(f"{'Driver':10s} {'Sync':8s} {'Pre bugs':>8s} {'Pre mo':>6s} {'Pre rate':>8s}"
          f" {'Post bugs':>9s} {'Post mo':>7s} {'Post rate':>9s} {'Change':>8s}")
    for driver in DRIVERS:
        sync = first_sync(panel_by_driver, driver)
        rows = panel_by_driver[driver]
        if not sync:
            print(f"{driver:10s} {'never':8s}")
            continue
        pre_bugs = sum(r["n_bugs"] for r in rows if r["month"] < sync)
        pre_months = sum(1 for r in rows if r["month"] < sync)
        post_bugs = sum(r["n_bugs"] for r in rows if r["month"] >= sync)
        post_months = sum(1 for r in rows if r["month"] >= sync)
        pre_rate = pre_bugs / pre_months * 12 if pre_months else 0
        post_rate = post_bugs / post_months * 12 if post_months else 0
        change = (post_rate - pre_rate) / pre_rate * 100 if pre_rate else float('inf')
        print(f"{driver:10s} {sync:8s} {pre_bugs:8d} {pre_months:6d} {pre_rate:8.3f}"
              f" {post_bugs:9d} {post_months:7d} {post_rate:9.3f} {change:+7.0f}%")

    print("\n=== Late-syncing drivers: post-spec pre-sync vs post-sync rates ===\n")
    print(f"{'Driver':10s} {'Sync':8s} {'Pre bugs':>8s} {'Pre mo':>6s} {'Pre rate':>9s}"
          f" {'Post bugs':>9s} {'Post mo':>7s} {'Post rate':>9s} {'Change':>8s}")
    for driver in sorted(LATE_DRIVERS, key=lambda d: first_sync(panel_by_driver, d)):
        sync = first_sync(panel_by_driver, driver)
        rows = panel_by_driver[driver]
        pre = [r for r in rows if r["month"] >= CRUD_SPEC_PUBLISHED and r["month"] < sync]
        post = [r for r in rows if r["month"] >= sync]
        pb, pm = sum(r["n_bugs"] for r in pre), len(pre)
        ob, om = sum(r["n_bugs"] for r in post), len(post)
        pr = pb / pm * 12 if pm else 0
        or_ = ob / om * 12 if om else 0
        chg = (or_ - pr) / pr * 100 if pr else float('inf')
        print(f"{driver:10s} {sync:8s} {pb:8d} {pm:6d} {pr:9.3f}"
              f" {ob:9d} {om:7d} {or_:9.3f} {chg:+7.0f}%")

    print("\nGenerating chart...")
    chart_late5(panel_by_driver)
    print("  wrote crud_late5.png / crud_late5.pdf")

    print("\nDone.")


if __name__ == "__main__":
    main()
