# Design

The short version of every decision, so code can be checked against it. Each section names the rules it serves.

## Shape of the system (R31, R36)

One Python process: a FastAPI app plus one background worker thread started in the app's lifespan.
One SQLite file. No broker, no ORM, no Docker requirement.

Request path for every protected endpoint, in this order:

```
token -> identity (401) -> body/params validation (422) -> role check (403)
      -> load resource (404) -> state/version check (409, 412, 428)
      -> one service function inside one transaction -> response (200/201/202)
```

Layers and what each may do:

| Layer | File | May | May not |
|---|---|---|---|
| Router | `*/router.py` | parse HTTP, take the `Analyst` or `Reviewer` dependency, call one service function, return a schema | contain business rules, write SQL |
| Service | `*/service.py` | enforce rules and state transitions, open a transaction, call store functions | know about HTTP, `Request`, status codes |
| Store | `*/store.py` | run SQL with parameters, map rows to plain data | make decisions, call the model |
| Classifier | `classify/*.py` | call the model or return saved/canned output, validate its shape | touch the database |
| Scoring | `scoring.py` | pure maths over labels | any I/O, any model call |

Services raise `AppError` subclasses (`NotFound`, `Conflict`, `StaleVersion`, `Forbidden`...). One handler in
`main.py` maps them to status codes and the error body `{"error": "<code>", "detail": "<text>"}` (R34).

## Auth and roles (R47, R49, R50)

`.env` holds `ANALYST_TOKEN` and `REVIEWER_TOKEN`. `auth.py` builds a dict `token -> Identity(name, role)` at
startup. A dependency reads `Authorization: Bearer <token>`, looks it up, and returns the identity. Unknown
or missing token: 401. `require_analyst` and `require_reviewer` return 403 for the wrong role. Nothing in a request header
other than the bearer token, nor anything in the body or the data, influences identity. The actor stored on
a decision is `identity.name`.

| Endpoint | analyst | reviewer | none |
|---|---|---|---|
| GET /health | yes | yes | yes |
| POST /datasets | yes | 403 | 401 |
| GET /datasets/{id} | yes | yes | 401 |
| POST /analyses, POST /analyses/{id}/retry | yes | 403 | 401 |
| GET /analyses/{id}, /results | yes | yes | 401 |
| POST /reports, PATCH /reports/{id}, POST /reports/{id}/submit | yes | 403 | 401 |
| POST /reports/{id}/decision | 403 | yes | 401 |
| GET /reports/{id}, GET /reports/{id}/export | yes | yes | 401 |

## SQLite usage (R30, R41, R45)

- Connect with `isolation_level=None` (we control transactions), `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`, `PRAGMA busy_timeout=5000`, `row_factory=sqlite3.Row`.
- Every write goes through `with transaction(conn):` which issues `BEGIN IMMEDIATE`, commits on success, rolls back on exception.
- Validate input before opening a transaction. Never call the model inside one.
- State changes use guarded updates: `UPDATE ... SET status='approved' WHERE version_id=? AND status='submitted'`. If `rowcount == 0`, someone else already acted: raise `Conflict`.
- Constraints are the last line of defence: primary keys on original IDs, `UNIQUE(content_hash)`, `PRIMARY KEY(analysis_id, response_id)`, `UNIQUE(report_id, version_no)`, `UNIQUE(version_id)` on decisions, `CHECK` on every status column.

## Tables

```
datasets          dataset_id PK, content_hash UNIQUE, imported_at, accepted_count, rejected_json
prompts           prompt_id PK, dataset_id FK, text, raw_json
responses         response_id PK, dataset_id FK, prompt_id FK, engine CHECK, model NULL, answer_text,
                  answer_markdown, raw_json
citations         citation_id PK, response_id FK, url, normalised_url, position, location, raw_json
analyses          analysis_id PK, dataset_id FK, execution_mode CHECK, prompt_version, model, scoring_version,
                  category_version, status CHECK, created_at,
                  UNIQUE(dataset_id, execution_mode, prompt_version, model, scoring_version, category_version)
response_results  analysis_id FK, response_id FK, status CHECK('pending','done','failed','skipped'),
                  attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0), labels_json, score_json, evidence_json, error, reason,
                  updated_at, PRIMARY KEY(analysis_id, response_id)
model_calls       call_id PK, analysis_id, response_id, execution_mode, model, latency_ms, input_tokens,
                  output_tokens, cost_usd NULL, outcome, created_at
reports           report_id PK, analysis_id FK UNIQUE, created_at
report_versions   version_id PK, report_id FK, version_no, status CHECK('draft','submitted','approved',
                  'rejected','expired','superseded'), revision INTEGER NOT NULL DEFAULT 1, content_json, content_sha256, created_by,
                  created_at, submitted_at, review_due_at, approval_valid_until, UNIQUE(report_id, version_no)
review_decisions  decision_id PK, version_id FK UNIQUE, actor, decision CHECK('approve','reject'),
                  comment NOT NULL CHECK(length(comment) > 0), decided_at
```

## Background processing (R36, R41, R42, R43, R46)

`POST /analyses` computes the config key. If an analysis with that key exists, return it with 200. Otherwise
insert the analysis and one `pending` row per eligible response (rejected records become `skipped` with a
reason) in one transaction, and return 202.

The worker loop: read the next `pending` row, call the classifier outside any transaction, then save the
result or failure with a guarded update (`... AND status = 'pending'`). With a single worker there is no
claim step and no `running` state. Because each result is saved
as it finishes, restart resumes naturally: on startup the worker picks up `pending` rows of unfinished
analyses. Tests call `process_pending(conn, classifier, limit)` directly, with no thread.

Exactly-once limit: the database guarantees one stored result per `(analysis_id, response_id)`. It cannot
guarantee one model call. If the process dies after the provider responds but before the result is saved,
the retry calls the model again and may be billed again. Attempts are capped at `MODEL_MAX_ATTEMPTS`
(default 3) by the guarded update `... AND attempts < ?`, and every call is
logged in `model_calls`.

## Model adapter (R15, R17, R19, R21, R38, R39, R48)

`classify/base.py` defines a `Classifier` Protocol with `classify(response) -> Classification`, and the
`Classification` Pydantic model. Three implementations, chosen by `MODEL_MODE`. The brief also names a
local-model mode; it is not built because no local model is available, so no result is ever labelled
`local-model`.

- `live`: calls the API with a timeout, bounded `max_tokens`, asks for JSON only, validates with Pydantic. Saves every raw output to the replay file.
- `replay`: returns saved outputs keyed by `(response_id, prompt_version)`. Missing key is a failure, not a guess.
- `stub`: returns canned outputs set by tests, including invalid JSON, empty output and timeouts.

Any output that fails validation becomes a `failed` result with the reason. Never a default label set.
The prompt puts the answer text inside clear delimiters and states it is data to label, not instructions.
The classifier has no tools and no access to anything that could change permissions.

## Classification and scoring (R9, R11, R23 to R29)

Labels per response: `mentioned`, `recommended`, `negative` (booleans), `absent = not mentioned`,
`competitors` (list of names as written), `position` (int or null), `kasparro_cited` (bool, from citations
data, deterministic), `evidence` (exact excerpt plus character span for each true label).

Citation rule: normalise URLs (lowercase host, strip `www.`, trailing slash, fragment and tracking
parameters). Within one response a normalised URL counts once, whatever mix of inline and sources-panel
locations it has; all locations are kept. Across responses each occurrence counts separately per response.

Score `scoring_v1`, 0 to 100 per response:

| Component | Value | Weight |
|---|---|---|
| included | 0 or 1 | 25 |
| recommended | 0 or 1 | 40 |
| position | 1 / position, or null if no ranked list | 20 |
| kasparro_cited | 0 or 1 | 15 |
| negative | penalty | -30 |

A null component is skipped and its weight redistributed proportionally; the result records which
components were used. Final score is clamped to 0 to 100. Failed results have no score and are excluded
from averages but counted. Every aggregate reports `n_successful / n_eligible` and `n_failed`. Weights are
provisional until the hand labels are checked (PR3); any change creates `scoring_v2`.

Categories: assigned to the 50 prompts from reading them, stored with `category_version`, never by the
model at scoring time.

## Reports and review (R45, R51 to R58)

Version states: `draft -> submitted -> approved | rejected | expired`, and `submitted -> superseded` when
edited while pending. Only `draft` content can change. Submit sets `review_due_at = now + 48h`. Approve sets
`approval_valid_until = now + 168h`. Expiry is evaluated when someone decides or exports; a decision after
the deadline marks the version `expired` and returns 409.

Each version has an integer `revision`, starting at 1. The ETag is `"<revision>"`. `PATCH` without
`If-Match` returns 428. The content update is
`... SET content_json = ?, revision = revision + 1 WHERE version_id = ? AND revision = ? AND status = 'draft'`;
zero rows means the client's copy is stale, so 412.

Export returns content plus `report_id`, `version`, `approved_by`, `approved_at`, `valid_until`,
`execution_mode`, `scoring_version`, `category_version` and `content_sha256`.

## Out of scope

Dashboard, Docker, deployment, crawling, vector search, multiple agents, OAuth, multiple workers, a broker.
