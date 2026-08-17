# UTF Migration LOC Analysis

How much test code did each MongoDB driver delete when it migrated from many
format-specific YAML test runners to the Unified Test Format (UTF)?

## Files

- `commits.json` --- manually curated list of UTF-migration commits per driver,
  with test-file path patterns for each language.
- `results.csv` --- computed per-commit LOC stats (regenerable; tracked for
  convenience).
- `../scripts/utf_migration_loc.py` --- script that reads `commits.json` and
  writes `results.csv`.

## Methodology

For each driver we manually identified commits that are part of the UTF
migration:

1. **`runner_creation`** --- the commit(s) that first introduced the unified
   runner. This is an *investment* (adds LOC) rather than a saving.
2. **`conversion`** --- commits that converted old format-specific test runners
   (and their YAML files) to the unified format, deleting legacy code.
3. **`runner_evolution`** --- later housekeeping of the unified runner itself
   (e.g. JUnit 4→5 migration); labeled separately.

For each commit the script runs `git show --unified=0` against the bare driver
repo and counts `-` (deleted) and `+` (added) lines in test files, filtered by
per-driver path patterns and file extensions.

## Regenerating results.csv

```
cd /path/to/driver-yaml-spec-testing
analysis/.venv/bin/python analysis/scripts/utf_migration_loc.py
```

To process only specific drivers:
```
analysis/.venv/bin/python analysis/scripts/utf_migration_loc.py RUST JAVA
```
