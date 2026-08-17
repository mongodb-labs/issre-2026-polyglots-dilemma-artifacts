You are classifying a single MongoDB driver Jira ticket for a research paper on cross-language conformance testing of MongoDB drivers.

MongoDB maintains driver libraries for a dozen languages (Python, Java, C#, Go, C, Rust, Node.js, Ruby, PHP, Perl, Swift, etc.). Each driver is supposed to implement shared cross-language **specifications** defining identical behavior.

# Categories (choose exactly one)

- `driver_spec_nonconformance` — The driver implemented a spec requirement incorrectly: spec said X, driver did Y. The bug is a literal deviation from a published spec rule.
- `cross_driver_inconsistency` — Filed because two drivers behave differently; the prose explicitly names the comparison.
- `spec_ambiguity_or_gap` — Root cause is the spec being silent, ambiguous, or wrong; fix required amending the spec.
- `spec_authoring` — Ticket is about writing or amending a specification, not fixing a driver.
- `test_infrastructure` — About spec test runner, YAML test files, UTF schema, or CI for running spec tests.
- `not_relevant` — Everything else: build, packaging, CI failures, docs, performance, internal implementation details, language ergonomics. **Default when uncertain.**

# Spec areas

`bson`, `sdam`, `server-selection`, `cmap`, `connection-string`, `dns-seedlist`, `auth`, `auth-scram`, `auth-oidc`, `auth-aws`, `auth-x509`, `crud`, `wire-protocol`, `command-monitoring`, `sessions`, `causal-consistency`, `transactions`, `retryable-reads`, `retryable-writes`, `change-streams`, `read-concern`, `write-concern`, `cursors`, `stable-api`, `csfle`, `gridfs`, `compression`, `load-balancer`, `ocsp`, `logging`, `opentelemetry`, `index-management`, `collation`, `time-series`. Use `[]` if none.

# Output

One JSON object per ticket, no markdown fence, no preamble:

{"key": "<TICKET-KEY>", "category": "...", "spec_areas": ["...", "..."], "is_nonconformance": true|false, "mentions_other_driver": true|false, "preventable_by_yaml_test": true|false|"unsure", "confidence": "high|medium|low", "rationale": "<max 25 words>"}
