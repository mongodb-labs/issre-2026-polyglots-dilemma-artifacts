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

**Gate for N:** Before classifying as `driver_spec_nonconformance`, ask: *Can I name the specific rule in the spec that the driver violated?* If yes, N. If you can only say "this is in a spec-covered area" or "the spec probably covers this," classify as `not_relevant` instead.

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

# Few-shot examples

## Example 1 --- `driver_spec_nonconformance`

Ticket: MGO-19
Summary: Change nUpdated to nMatched in bulk api results
Description: (none)
Links: Related:DRIVERS-140

```json
{"key": "MGO-19", "category": "driver_spec_nonconformance", "spec_areas": ["crud"], "is_nonconformance": true, "mentions_other_driver": false, "preventable_by_yaml_test": true, "confidence": "high", "rationale": "Bulk write result field name deviates from spec term 'nMatched'; direct spec conformance fix."}
```

## Example 2 --- `driver_spec_nonconformance`

Ticket: CSHARP-2219
Summary: ClusterClockAdvancingCoreSession should return the greater of the two ClusterTimes
Description: As part of gossiping the cluster time the driver appends a $clusterTime element to the command sent to the server. The code should return whichever ClusterTime is greater, but currently always appends the session's value.
Links: (none)

```json
{"key": "CSHARP-2219", "category": "driver_spec_nonconformance", "spec_areas": ["sessions"], "is_nonconformance": true, "mentions_other_driver": false, "preventable_by_yaml_test": true, "confidence": "high", "rationale": "Sessions spec requires gossiping the greater ClusterTime; driver always uses session value instead."}
```

## Example 3 --- `cross_driver_inconsistency`

Ticket: HHVM-237
Summary: Default Manager URI to "mongodb://127.0.0.1/"
Description: PHPC has defaulted to this value (via libmongoc) since 1.1.1. HHVM currently defaults to "mongodb://localhost", which might prefer IPv6 connections. For consistency, let's change the default URI to "mongodb://127.0.0.1/".
Links: Depends:PHPLIB-220, Related:PHPC-746

```json
{"key": "HHVM-237", "category": "cross_driver_inconsistency", "spec_areas": ["connection-string"], "is_nonconformance": false, "mentions_other_driver": true, "preventable_by_yaml_test": false, "confidence": "high", "rationale": "Explicit behavioral divergence: PHPC uses 127.0.0.1, HHVM uses localhost; filed to align them."}
```

## Example 4 --- `not_relevant` (implementation/architecture bug, not a spec rule violation)

Ticket: NODE-1761
Summary: Mongos topology leaks memory on server reconnect
Description: I have been battling some weird memory leaks in our apps, and have found out that the culprit seems to be the mongodb driver which doesn't handle the Pool teardown properly after server reconnects. Memory grows unboundedly after repeated reconnects.
Links: (none)

```json
{"key": "NODE-1761", "category": "not_relevant", "spec_areas": [], "is_nonconformance": false, "mentions_other_driver": false, "preventable_by_yaml_test": false, "confidence": "high", "rationale": "Memory leak in pool teardown on reconnect; implementation bug with no specific contradicted spec rule."}
```

Note: being in a spec-covered component (connection pooling) does not make this `driver_spec_nonconformance`. The CMAP spec does not contain a rule saying "pools must not leak on reconnect"---it defines the pool API and lifecycle events. A resource leak is an implementation flaw, not a spec deviation.

## Example 5 --- `spec_ambiguity_or_gap`

Ticket: CSHARP-3061
Summary: Clarify how a driver must handle wrong set name in single topology
Description: The SDAM specification allows specifying replica set name in single topology but doesn't specify what to do when the server returns a different set name. Different drivers handle this differently. The fix requires updating the SDAM spec.
Links: Depends:CSHARP-2962, Depends:DRIVERS-980

```json
{"key": "CSHARP-3061", "category": "spec_ambiguity_or_gap", "spec_areas": ["sdam"], "is_nonconformance": false, "mentions_other_driver": false, "preventable_by_yaml_test": false, "confidence": "high", "rationale": "SDAM spec silent on wrong set name in single topology; fix required spec amendment via DRIVERS-980."}
```

## Example 6 --- `test_infrastructure`

Ticket: CSHARP-4084
Summary: Update initial DNS seedlist discovery tests to support dedicated load balancer port
Description: This ticket was split from DRIVERS-2224, please see that ticket for a detailed description.
Links: Issue split:DRIVERS-2224

```json
{"key": "CSHARP-4084", "category": "test_infrastructure", "spec_areas": ["dns-seedlist"], "is_nonconformance": false, "mentions_other_driver": false, "preventable_by_yaml_test": false, "confidence": "high", "rationale": "Child ticket of DRIVERS-2224; updating DNS seedlist discovery test files, not fixing driver behavior."}
```

Note: "Issue split: DRIVERS-XXXX" means this is a per-driver child of a DRIVERS coordination ticket. Do NOT classify as `cross_driver_inconsistency`. The parent coordinates a test update across all drivers.

## Example 7 --- `test_infrastructure`

Ticket: SCALA-444
Summary: Resync read write concern tests to add new read concern levels
Description: See DRIVERS-567 for details.
Links: Depends:SPEC-1152, Depends:DRIVERS-567

```json
{"key": "SCALA-444", "category": "test_infrastructure", "spec_areas": ["read-concern", "write-concern"], "is_nonconformance": false, "mentions_other_driver": false, "preventable_by_yaml_test": false, "confidence": "high", "rationale": "Resync spec test files for new read concern levels; test infrastructure update, not a driver bug."}
```

## Example 8 --- `not_relevant` (performance/internal, not spec)

Ticket: JAVA-4523
Summary: Buffer is leaked from buffer pool on socket exception
Description: In SocketStream#read, the ByteBuf is not released if an exception is thrown. As a result the buffer will be GC'd but will not be returned to the buffer pool. This is a performance issue, but there is no user-visible behavior change.
Links: (none)

```json
{"key": "JAVA-4523", "category": "not_relevant", "spec_areas": [], "is_nonconformance": false, "mentions_other_driver": false, "preventable_by_yaml_test": false, "confidence": "high", "rationale": "Netty buffer pool leak on exception; internal performance issue, no spec-defined behavior involved."}
```

## Example 9 --- `not_relevant` (related link to another project ≠ cross-driver)

Ticket: PHPC-756
Summary: fromJSON() should not evaluate bson_error_t.message as boolean
Description: In bson.c, fromJson calls phongo_throw_exception with either a custom error message or a generic "Error parsing JSON" message. To determine which, it evaluates the error message string as a boolean---this is a PHP-specific bug.
Links: Related:HHVM-273

```json
{"key": "PHPC-756", "category": "not_relevant", "spec_areas": [], "is_nonconformance": false, "mentions_other_driver": false, "preventable_by_yaml_test": false, "confidence": "high", "rationale": "PHP-specific boolean-evaluation bug in JSON error handling; related link to HHVM-273 is a parallel fix, not a cross-driver inconsistency."}
```

## Example 10 --- `not_relevant` (CI / build failure)

Ticket: PHPC-522
Summary: make coveralls fails for PHP 7 builds on Travis CI
Description: Coveralls CI integration fails for PHP 7 builds. See Travis CI log for details.
Links: (none)

```json
{"key": "PHPC-522", "category": "not_relevant", "spec_areas": [], "is_nonconformance": false, "mentions_other_driver": false, "preventable_by_yaml_test": false, "confidence": "high", "rationale": "CI build failure; no driver behavior or spec involvement."}
```
