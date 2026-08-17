"""Regenerate utf_driver_code_changes.pdf from results.csv.

Computes per-driver net LOC removed (conversion + runner_evolution commits,
excluding runner_creation) and saves a bar chart as a PDF.

Usage: python analysis/scripts/plot_utf_driver_code_changes.py
"""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("PDF")
import matplotlib.pyplot as plt

BASE = Path(__file__).parent.parent
CSV_PATH = BASE / "utf_migration" / "results.csv"
OUT = BASE / "utf_migration" / "utf_driver_code_changes.pdf"

LABELS = {
    "CSHARP":  "C#",
    "GODRIVER": "Go",
    "JAVA":    "Java",
    "NODE":    "Node.js",
    "PHPLIB":  "PHP",
    "PYTHON":  "Python",
    "RUST":    "Rust",
}


def main():
    rows = list(csv.DictReader(CSV_PATH.open()))
    totals = {}
    for row in rows:
        if row["role"] == "runner_creation":
            continue
        driver = row["driver"]
        totals[driver] = totals.get(driver, 0) + int(row["net_test_lines_removed"])

    drivers = sorted(LABELS.keys(), key=lambda d: LABELS[d])
    drivers = [d for d in drivers if d in totals]
    labels = [LABELS[d] for d in drivers]
    # Negate: positive savings → negative y (lines removed go below zero)
    values = [-totals[d] for d in drivers]

    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman"],
        "pdf.fonttype": 42,
    })

    fig, ax = plt.subplots(figsize=(8, 6))

    ax.bar(labels, values, color="#2ca02c", width=0.6, zorder=3,
           edgecolor="black", linewidth=0.8)
    ax.axhline(0, color="black", linewidth=0.8, zorder=4)
    ax.yaxis.grid(True, linestyle="--", color="gray", alpha=0.6, zorder=0)
    ax.set_axisbelow(True)

    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color("black")
        spine.set_linewidth(1.5)

    ax.set_xlabel("Driver", fontsize=26, labelpad=8)
    ax.set_ylabel("Net Lines of Code Changed", fontsize=26, labelpad=8)
    ax.tick_params(axis="x", labelsize=26)
    ax.tick_params(axis="y", labelsize=26)
    plt.xticks(rotation=30, ha="right")

    plt.tight_layout()
    plt.savefig(OUT)
    print(f"Saved {OUT}")


if __name__ == "__main__":
    main()
