# Prompt experiment results (200-ticket gold corpus)

Gold corpus: 80 human-labeled + 120 Opus-labeled tickets.
Category distribution: 32 N, 136 R, 24 T, 4 G, 4 S.
Model under test: claude-sonnet-4-6.

## Summary table

| experiment | overall | N prec | N rec | N F1 | key change |
|---|---:|---:|---:|---:|---|
| exp01_baseline | 80.0% | 55.6% | 78.1% | 0.649 | baseline (current classify.md) |
| exp02_specific_rule | 77.5% | 73.3% | 68.8% | **0.710** | gate: "can I name the specific spec rule?" |
| exp03_cot_spec_rule | 77.5% | 75.0% | 65.6% | 0.700 | + `spec_rule` CoT field in output schema |
| exp04_more_n_examples | 79.0% | 47.4% | 84.4% | 0.607 | 4 extra N few-shot examples |
| exp05_liberal_n | 75.5% | 43.1% | 78.1% | 0.556 | "err slightly toward N" instruction |
| exp06_conservative_n | 75.5% | 44.1% | 81.2% | 0.571 | 3-part N checklist |
| exp07_no_fewshot | 76.5% | 54.2% | 81.2% | 0.650 | removed all few-shot examples |
| exp08_simplified | 78.5% | 48.9% | 71.9% | 0.582 | stripped-down prompt |

## Winner: exp02_specific_rule (N F1 = 0.710)

The single addition from baseline: a "gate" question in the N category definition---

> **Before classifying as `driver_spec_nonconformance`, ask: "Can I name the specific spec rule the driver violated?"** If you can, classify N. If you cannot point to a specific spec requirement (only a general sense that "this should work"), default to `not_relevant`.

This raises precision from 55.6% → 73.3% at the cost of recall (78.1% → 68.8%), net +6pp F1. The main failure mode in exp01 was the model calling spec-covered-component bugs N when there was no specific violated rule; the gate directly addresses that.

## What didn't help

- **More N examples (exp04):** pushed recall to 84.4% but precision collapsed to 47.4%. The examples made the model more trigger-happy across the board.
- **Liberal/conservative N framing (exp05/06):** both made precision worse by triggering broader N coverage.
- **No few-shot (exp07):** recall improves but precision stays low; examples help more than they hurt.
- **Spec descriptions (not an experiment here, but tested earlier):** adding one-line descriptions of each spec area to the prompt dropped overall agreement by 3.7pp. Reverted.

## Recommendation

Use **exp02_specific_rule** for the full 13,538-ticket Sonnet re-classification.
The prompt diff from exp01 is one sentence added to the `driver_spec_nonconformance` definition section.

(Note: the 13,538 figure was the planned scope when this summary was written; the final Sonnet run classified 17,501 tickets after more Jira projects were added. See the top-level README for final counts.)
