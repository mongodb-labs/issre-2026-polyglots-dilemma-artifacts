"""Score Sonnet results against gold corpus labels.

Usage:
    python score.py <results_dir>

results_dir should contain chunk_NN.results.jsonl files and will receive
metrics.json and a printed confusion matrix.
"""
import json, sys
from pathlib import Path
from collections import defaultdict

GOLD_LABELS = Path('/tmp/gold_eval/gold_corpus_labels.json')
GOLD_CORPUS  = Path('/Users/emptysquare/co/driver-yaml-spec-testing/analysis/data/gold_corpus.csv')

CATEGORIES = [
    "driver_spec_nonconformance",
    "cross_driver_inconsistency",
    "spec_ambiguity_or_gap",
    "spec_authoring",
    "test_infrastructure",
    "not_relevant",
]
SHORT = {
    "driver_spec_nonconformance": "N",
    "cross_driver_inconsistency": "X",
    "spec_ambiguity_or_gap":      "G",
    "spec_authoring":             "S",
    "test_infrastructure":        "T",
    "not_relevant":               "R",
}


def load_results(results_dir):
    model = {}
    for path in sorted(Path(results_dir).glob('chunk_*.results.jsonl')):
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line: continue
                d = json.loads(line)
                if d.get('key'):
                    model[d['key']] = d
    return model


def score(results_dir, label=""):
    gold = json.loads(GOLD_LABELS.read_text())
    model = load_results(results_dir)

    pairs = []
    for key, human in gold.items():
        m = model.get(key)
        if not m: continue
        pairs.append((human, m.get('category', ''), key, m))

    present = [c for c in CATEGORIES if any(h==c or mc==c for h,mc,_,_ in pairs)]
    matrix = defaultdict(lambda: defaultdict(int))
    for h, mc, _, _ in pairs:
        matrix[h][mc] += 1

    row_w = 35
    print(f"\n{'='*65}")
    print(f"  {label}  (n={len(pairs)})")
    print(f"{'='*65}")
    print(f"{'human \\ model':<{row_w}} " + "  ".join(f"{SHORT.get(c,c[:3]):>3}" for c in present))
    for human in present:
        if not any(h==human for h,_,_,_ in pairs): continue
        n_human = sum(matrix[human].values())
        row = f"{human:<{row_w}} " + "  ".join(f"{matrix[human][mc]:>3}" for mc in present)
        print(row + f"  (n={n_human})")

    print()
    metrics = {}
    total_agree = 0
    print(f"{'category':<35} {'prec':>6} {'recall':>7} {'human':>6} {'model':>6}")
    for cat in present:
        tp = matrix[cat][cat]
        fp = sum(matrix[h][cat] for h in present if h != cat)
        fn = sum(matrix[cat][m] for m in present if m != cat)
        prec = tp / (tp + fp) if (tp + fp) else float('nan')
        rec  = tp / (tp + fn) if (tp + fn) else float('nan')
        f1   = 2*prec*rec/(prec+rec) if (prec+rec) else float('nan')
        total_agree += tp
        h_n = sum(matrix[cat].values())
        m_n = sum(matrix[h][cat] for h in present)
        metrics[cat] = {'precision': round(prec,4), 'recall': round(rec,4),
                        'f1': round(f1,4), 'human_n': h_n, 'model_n': m_n, 'tp': tp}
        print(f"{cat:<35} {prec:>6.0%} {rec:>7.0%} {h_n:>6} {m_n:>6}")

    n = len(pairs)
    overall = total_agree / n
    print(f"\noverall agreement: {total_agree}/{n} = {overall:.1%}")

    # N-specific F1 (the key metric)
    n_met = metrics.get('driver_spec_nonconformance', {})
    n_f1 = n_met.get('f1', float('nan'))
    print(f"N F1: {n_f1:.3f}  (prec={n_met.get('precision',0):.0%} rec={n_met.get('recall',0):.0%})")

    out = {'overall_agreement': round(overall, 4),
           'n_agreed': total_agree, 'total': n,
           'n_f1': round(n_f1, 4) if n_f1 == n_f1 else None,
           'categories': metrics}
    Path(results_dir, 'metrics.json').write_text(json.dumps(out, indent=2))
    return out


if __name__ == '__main__':
    results_dir = sys.argv[1] if len(sys.argv) > 1 else '.'
    score(results_dir, label=Path(results_dir).name)
