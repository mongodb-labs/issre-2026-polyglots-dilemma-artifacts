# The Polyglot's Dilemma---Artifacts

Analysis pipeline and data behind the quantitative results in "The Polyglot's Dilemma: Conformance Testing a Dozen Specs in as Many Languages."

This repository contains two analyses:

1. CRUD bug-prevention study: do YAML spec tests reduce nonconformance bug rates?
2. UTF migration lines-of-code analysis: how much test code did each driver delete by migrating to UTF? See utf_migration/README.md.

## CRUD bug-prevention study

The paper's Fig. 5 covers the 5 late-syncing drivers (C, C++, Node.js, Ruby, PHP). We classified their 6,836 resolved tickets from MongoDB's public issue tracker with an LLM classifier, re-examined the CRUD candidates with a higher-effort pipeline, and mined each driver's git history to determine the month it first synced CRUD YAML test files from the shared specifications repository.

The Sonnet classifier was run over a wider corpus (17,501 tickets across 22 Jira projects) before we decided to focus on the 5 late-syncing drivers; only the late-5 numbers appear in the paper. See the note on [data/classified_sonnet.csv](data/classified_sonnet.csv) below.

We chose the CRUD (create, read, update, delete) specification because it is complex, all 189 of its test files use the Unified Test Format (the most of any spec), and it has a long history of implementation in some drivers before the introduction of YAML tests.

### Classifier validation

The Sonnet classifier prompt ([prompts/classify.md](prompts/classify.md)) was selected from 8 candidate prompts evaluated against a 200-ticket gold corpus (80 tickets human-labeled, 120 labeled by Claude Opus; [data/gold_corpus.csv](data/gold_corpus.csv)). The winning prompt scored F1=0.71 for the spec-nonconformance category (precision 73.3%, recall 68.8%); its key feature is a conservative gate: the model may only assign the nonconformance category if it can name the specific spec rule the driver violated. See [experiments/results_summary.md](experiments/results_summary.md) for all 8 experiments.

Because nonconformance bugs are a rare class (~2% base rate), we did not rely on the single-pass Sonnet output for the paper's headline numbers. Claude Opus reclassified 546 candidate tickets in the 5 late-syncing drivers over 3 passes (verify existing CRUD tags, hunt false negatives among other-spec bugs, hunt false negatives among not-relevant bugs with CRUD keywords), using fetched Jira comments for fuller context, and an author manually reviewed all 40 Node.js CRUD bugs one by one.

### Classification counts (5 late-syncing drivers)

| Stage | Tickets |
|-------|---------|
| Classified by Sonnet (pass 1) | 6,836 |
| Reclassified by Opus (CRUD candidates, 3 passes) | 546 |
| Manually reviewed by author (NODE) | 40 |
| Final CRUD nonconformance bugs (all-time) | 125 |
| Final CRUD nonconformance bugs (inside pre/post windows) | 117 (61 pre-adoption + 56 post-adoption) |

The 8-bug gap between all-time (125) and in-window (117) is bugs dated before the CRUD spec was published (2015-02), which can't actually be called "nonconformance."

### Analysis approach

The **5 late-syncing drivers**---C, C++, Node.js, Ruby, and PHP---all adopted CRUD YAML tests after the CRUD spec was already published (February 2015). For each driver the **pre-sync window** (spec published, no YAML tests) and the **post-sync window** (YAML tests adopted) both start after the spec existed, so the comparison isolates the effect of the tests rather than the effect of the spec publication itself.

The 4 early-syncing drivers (C#, Java, Perl, Python---all synced March 2015) are excluded: they adopted tests almost simultaneously with the spec publication, leaving only one month of post-spec pre-sync history.

Pre-adoption rates are computed over months from spec publication (Feb 2015) to each driver's sync date. Post-adoption rates are computed from sync date to end of data. The chart ([data/plots/crud_late5.pdf](data/plots/crud_late5.pdf)) is the paper's Fig. 5.

## What's here

```
.
├── README.md                 this file
├── requirements.txt          Python deps (anthropic, matplotlib, numpy, requests)
├── prompts/
│   ├── classify.md           per-ticket classifier prompt (system prompt for Sonnet)
│   └── subagent.md           batch subagent dispatch prompt
├── experiments/              prompt-selection experiments against the gold corpus
│   ├── exp01..exp08 *.md     the 8 candidate prompts
│   ├── exp0N_metrics.json    per-experiment scores
│   ├── results_summary.md    comparison and winning prompt
│   └── score.py              scoring script
├── scripts/
│   ├── count_volume.py       counts tickets per driver project
│   ├── pull_tickets.py       bulk-pulls Jira tickets to data/tickets/
│   ├── classify.py           Haiku classifier (superseded)
│   ├── classify_sonnet.py    Sonnet classifier with the winning prompt
│   ├── drivers_timeline.py   per-driver monthly YAML/JSON test file counts
│   ├── drivers_submodule_timeline.py  submodule-based drivers (JAVA, GODRIVER, PHPLIB)
│   ├── fetch_comments.py     pull Jira comments for CRUD candidates → data/comments.jsonl
│   ├── reclassify_opus.py    Opus reclassification of CRUD candidates → data/reclassified_opus.jsonl
│   ├── crud_analysis.py      CRUD panel, pre/post rate comparison, chart (paper Fig. 5)
│   ├── utf_migration_loc.py  UTF migration LOC counts (see utf_migration/)
│   └── plot_utf_driver_code_changes.py  chart for paper Fig. 4
├── utf_migration/            lines-of-code analysis of the UTF migration (paper Fig. 4)
└── data/
    ├── classified_sonnet.csv aggregated Sonnet classifications (17,501 unique tickets)
    │                          The paper uses only the 6,836 tickets in the 5 late-syncing
    │                          drivers (CDRIVER, CXX, NODE, RUBY, PHPLIB); the rest were
    │                          classified in the same pass but not analyzed
    ├── reclassified_opus.jsonl  Opus reclassification of 546 CRUD candidates (5 late drivers)
    ├── gold_corpus.csv       200-ticket gold corpus for precision/recall
    ├── drivers_timeline.csv  per-driver monthly spec-test file counts
    ├── drivers_submodule_timeline.csv  submodule-based driver file counts
    ├── crud_panel.csv        (driver, month) panel for CRUD analysis
    └── plots/
        └── crud_late5.pdf/.png  pre/post bug-rate chart (paper Fig. 5)
```

## Data provenance

All ticket data comes from MongoDB's public issue tracker, <https://jira.mongodb.org>. Raw per-ticket dumps (`data/tickets/`, `data/chunks/`, `data/sonnet_results/`, `data/comments.jsonl`) are omitted from this repository to keep it small and to avoid republishing bulk contributor metadata; the scripts below regenerate them from the public tracker. The classified CSVs retain ticket keys, summaries, and descriptions so every classification can be audited against the public tracker (each row links to its ticket URL).

## Reproducing the full pipeline

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Jira access uses a personal access token from your <https://jira.mongodb.org> account, kept outside the repo:

```sh
echo 'YOUR_TOKEN' > ~/.jira_pat
chmod 600 ~/.jira_pat
```

The classification scripts call the Anthropic API and require `ANTHROPIC_API_KEY` in the environment.

```sh
# 1. Pull all resolved Bug + Improvement tickets from driver Jira projects
.venv/bin/python scripts/pull_tickets.py

# 2. Classify tickets with Sonnet (resumable)
#    Output: data/classified_sonnet.csv
.venv/bin/python scripts/classify_sonnet.py

# 3. Clone driver repos (bare) for timeline mining
mkdir -p data/driver_repos
for r in mongo-c-driver mongo-csharp-driver mongo-cxx-driver \
         node-mongodb-native mongo-python-driver mongo-perl-driver \
         mongo-ruby-driver mongo-rust-driver mongo-swift-driver \
         mongo-java-driver mongo-go-driver mongo-php-library; do
  git clone --bare https://github.com/mongodb/$r data/driver_repos/${r}.git
done

# 4. Build per-driver YAML/JSON test timelines
.venv/bin/python scripts/drivers_timeline.py             # ~10 min
.venv/bin/python scripts/drivers_submodule_timeline.py   # ~3 min

# 5. Fetch Jira comments and reclassify CRUD candidates with Opus (5 late drivers)
.venv/bin/python scripts/fetch_comments.py
.venv/bin/python scripts/reclassify_opus.py

# 6. Run CRUD-focused analysis and generate the paper's Fig. 5
#    Applies the Opus overlay (reclassified_opus.jsonl) on top of Sonnet.
.venv/bin/python scripts/crud_analysis.py
```

For the UTF migration LOC analysis (paper Fig. 4), see [utf_migration/README.md](utf_migration/README.md).
