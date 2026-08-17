You are classifying a single MongoDB driver Jira ticket for a research paper on cross-language conformance testing.

# Background

MongoDB maintains a dozen or so native driver libraries (PyMongo, mongo-java-driver, mongo-csharp-driver, mongo-go-driver, libmongoc, mongo-rust-driver, Node.js driver, Ruby driver, PHP libraries, and historically Perl/Swift/Erlang/Haskell/HHVM/mgo). Each driver is supposed to implement a shared set of cross-language **specifications** that define identical behavior. Major spec areas:

- BSON (binary serialization)
- Server Discovery and Monitoring (SDAM)
- Server Selection
- Connection Monitoring and Pooling (CMAP)
- Connection String / URI parsing
- DNS seedlist / SRV
- Authentication (SCRAM, X.509, GSSAPI, MONGODB-AWS, MONGODB-OIDC)
- CRUD (insert/update/delete/find/aggregate/bulk write)
- Wire Protocol / Commands
- Command Monitoring
- Sessions, Causal Consistency
- Transactions
- Retryable Reads / Retryable Writes
- Change Streams
- Read Concern / Write Concern
- Cursors (find / getMore / killCursors)
- Stable API
- Client-Side Field-Level Encryption (CSFLE) and Queryable Encryption
- GridFS, Compression, Load Balancer, OCSP, Logging, OpenTelemetry
- Index Management, Collation, Time Series

The Jira projects are: PYTHON, MOTOR, JAVA, JAVARS, JAVARX, SCALA, NODE, CSHARP, GODRIVER, MGO, RUST, PHPLIB, PHPC, PHP, RUBY, CDRIVER, CXX, SWIFT, PERL, HHVM, SPEC, DRIVERS, DRIVERSOLD.

# Categories

Choose **exactly one** primary category. Default to `not_relevant` when uncertain.

---

### `driver_spec_nonconformance`
The driver implemented a spec area **incorrectly**. The spec says X; the driver did Y. Includes edge cases in spec coverage that the driver got wrong, missing required spec behaviors, and wrong values/types/semantics for spec-defined fields.

**Yes:** "UpdateOne should return error when update has no modifier" (spec requirement). / "nUpdated should be nMatched in bulk write result" (spec terminology). / "Regex flags 'u' and 'l' dropped during BSON serialization" (BSON spec). / "$clusterTime element should use the greater of the two values" (Sessions spec). / "context cancellation before transaction commit should abort the transaction" (Transactions spec).

**Not this:** A performance bug, memory leak, or internal implementation detail that doesn't contradict a specific spec requirement → `not_relevant`. A systemic architectural flaw in a spec-covered component (pool leak, topology resource leak) that doesn't correspond to a specific spec rule → `not_relevant`.

---

### `cross_driver_inconsistency`
The ticket was filed **because** two or more drivers behave differently from each other in a user-visible way. The prose explicitly names the comparison (e.g. "the Go driver does X but the Java driver does Y", "for consistency with pymongo", "rename to match other drivers"). A fix that explicitly aligns one driver with another.

**Yes:** "PHPC defaults to 'mongodb://127.0.0.1/' but HHVM defaults to 'mongodb://localhost'---for consistency, change HHVM." / "Rename CreateCollectionOptions::validation to validator to match Go and other drivers." / "Python driver succeeds auth with multiple replicas; C++ driver fails---investigate divergence."

**Critical anti-patterns---these are NOT `cross_driver_inconsistency`:**
- A ticket with `links: Issue split: DRIVERS-XXXX`---this means it's a child of a cross-driver coordination ticket (usually a spec rollout or test infrastructure change). The cross-driver coordination lives in DRIVERS; this per-driver ticket is about *implementing* that work in one driver.
- A ticket with `links: Related: NODE-1234` or `Depends: DRIVERS-567`---a related link alone is not cross-driver inconsistency. Cross-driver tickets must be about a behavioral divergence between drivers, not about depending on or coordinating with another ticket.
- A ticket that mentions another driver only as background context ("similar to how Java does it") but was filed for a different primary reason.
- A ticket whose summary is about adding a missing feature or fixing a spec bug---that's `driver_spec_nonconformance`, even if it references another driver's implementation.

---

### `spec_ambiguity_or_gap`
The **root cause** is in the spec, not just the driver. The spec was silent, ambiguous, or wrong on this case, and fixing it required amending the spec (or links to a DRIVERS/SPEC ticket that amended it). Common-mode failures where multiple drivers made the same mistake because the spec didn't address the case.

**Yes:** "SDAM spec doesn't clarify what to do with wrong replica set name in Single topology---clarify and implement." / "Spec is silent on handling command errors before handshake completes---add guidance."

---

### `spec_authoring`
The ticket is **about writing or amending a specification** (typically filed in DRIVERS or SPEC project), not about fixing a driver.

---

### `test_infrastructure`
About the spec test runner, YAML test format, UTF schema, or CI plumbing for running spec tests. **Not** about driver behavior. Includes tickets to update, resync, enable, or disable YAML spec test files.

**Yes:** "Resync read/write concern tests to add new read concern levels (see DRIVERS-567)." / "Update initial DNS seedlist discovery tests to support dedicated load balancer port (Issue split: DRIVERS-2224)." / "Update disabled change stream tests." / "Improve JSON tests for Binary Vector Subtype (Issue split: DRIVERS-3097)."

Note: many T tickets have `links: Issue split: DRIVERS-XXXX` because the DRIVERS project coordinates cross-driver test rollouts and each driver gets a child ticket.

---

### `not_relevant`
Everything else: build/packaging, CI failures, doc typos, dependency bumps, performance tuning, internal refactors with no behavior change, language-binding issues that don't touch a spec area, support questions, Coverity/static-analysis warnings, API ergonomics, ORM/LINQ mapping bugs.

**When in doubt, classify as `not_relevant`.**

---

# Decision guide for common pitfalls

1. **"Issue split: DRIVERS-XXXX" in links** → almost always `test_infrastructure` (spec test rollout child ticket) or `driver_spec_nonconformance` (driver fixing per-spec). Never `cross_driver_inconsistency` just because of this link.

2. **"Related: [other-driver-ticket]" in links** → not sufficient for X. Read the prose. If the prose doesn't say "Driver A does X but Driver B does Y," it's not X.

3. **Ticket mentions another driver by name** → not automatically X. If the ticket is about the filing driver's own spec compliance, it's N even if another driver is mentioned for comparison.

4. **Bug is in a spec-covered component** → not automatically N. Memory leaks, perf issues, CI failures, and docs bugs in spec-covered components are still `not_relevant` unless the bug contradicts a specific spec rule.

5. **Ticket uses spec terminology** → not automatically N. Check whether the bug is a literal deviation from the spec. If the spec doesn't say anything about this behavior, it might be `not_relevant`.

6. **Thin description** → classify as `not_relevant` with `confidence: low`, not as a spec category. Don't speculate.

---

# Spec areas

If the ticket touches a spec area, name it using these identifiers (use `[]` if none apply):
`bson`, `sdam`, `server-selection`, `cmap`, `connection-string`, `dns-seedlist`, `auth`, `auth-scram`, `auth-oidc`, `auth-aws`, `auth-x509`, `crud`, `wire-protocol`, `command-monitoring`, `sessions`, `causal-consistency`, `transactions`, `retryable-reads`, `retryable-writes`, `change-streams`, `read-concern`, `write-concern`, `cursors`, `stable-api`, `csfle`, `gridfs`, `compression`, `load-balancer`, `ocsp`, `logging`, `opentelemetry`, `index-management`, `collation`, `time-series`.

Use only these identifiers. If a ticket's topic falls outside this vocabulary, use `[]` and put the topic in the rationale.

---

# Cross-driver evidence

Set `mentions_other_driver: true` only if the summary or description **explicitly** names another driver by language or product name (e.g. "the Java driver does X", "matches behavior of pymongo") OR if the driver for this ticket explicitly discusses divergence from another named driver. Do NOT set to true just because `links` contains a key from another project.

---

# Confidence

- `high`: clear signal in the summary or description.
- `medium`: reasonable inference, some ambiguity.
- `low`: thin description, weak signal, or you're genuinely unsure.

Default to `medium`.

---

# Additional flags

- `is_nonconformance`: true if the driver literally deviated from a published spec requirement (spec said X, driver did Y). Can be true with any category.
- `preventable_by_yaml_test`: true if a YAML/UTF spec test asserting the correct behavior could plausibly have caught this before release. False for build/packaging, perf, docs, internal refactors. Use `"unsure"` if the bug touches a spec area but the failure mode is hard to express as a YAML assertion.

---

# Output format

Output **only** a single JSON object on one line, no markdown fence, no preamble, no explanation outside the JSON:

```
{"key": "<TICKET-KEY>", "category": "...", "spec_areas": ["...", "..."], "is_nonconformance": true|false, "mentions_other_driver": true|false, "preventable_by_yaml_test": true|false|"unsure", "confidence": "high|medium|low", "rationale": "<max 25 words citing the specific phrase or evidence you used>"}
```

`spec_areas` is a JSON array (use `[]` if none). `key` must echo the ticket's Jira key exactly. If the ticket is too thin to classify, use `not_relevant` with `confidence: low` and rationale `insufficient detail`.

---

