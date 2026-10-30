-- Each table is added by the PR that first needs it.

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id    TEXT PRIMARY KEY,
    content_hash  TEXT NOT NULL UNIQUE,
    imported_at   TEXT NOT NULL,
    rejected_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prompts (
    dataset_id TEXT NOT NULL REFERENCES datasets (dataset_id),
    prompt_id  TEXT NOT NULL,
    text       TEXT NOT NULL,
    raw_json   TEXT NOT NULL,
    PRIMARY KEY (dataset_id, prompt_id)
);

CREATE TABLE IF NOT EXISTS responses (
    dataset_id      TEXT NOT NULL,
    response_id     TEXT NOT NULL,
    prompt_id       TEXT NOT NULL,
    engine          TEXT NOT NULL CHECK (engine IN ('aimode', 'chatgpt', 'gemini')),
    model_version   TEXT,
    answer_text     TEXT NOT NULL,
    answer_markdown TEXT,
    raw_json        TEXT NOT NULL,
    PRIMARY KEY (dataset_id, response_id),
    FOREIGN KEY (dataset_id, prompt_id) REFERENCES prompts (dataset_id, prompt_id)
);

CREATE TABLE IF NOT EXISTS citations (
    dataset_id    TEXT NOT NULL,
    citation_id   TEXT NOT NULL,
    response_id   TEXT NOT NULL,
    position      INTEGER NOT NULL CHECK (position >= 1),
    citation_type TEXT NOT NULL CHECK (citation_type IN ('inline_hyperlink', 'sources_panel')),
    url           TEXT NOT NULL,
    raw_json      TEXT NOT NULL,
    PRIMARY KEY (dataset_id, citation_id),
    FOREIGN KEY (dataset_id, response_id) REFERENCES responses (dataset_id, response_id)
);

CREATE TABLE IF NOT EXISTS analyses (
    analysis_id      TEXT PRIMARY KEY,
    dataset_id       TEXT NOT NULL REFERENCES datasets (dataset_id),
    execution_mode   TEXT NOT NULL CHECK (execution_mode IN ('local-model', 'replay', 'stub')),
    prompt_version   TEXT NOT NULL,
    model            TEXT NOT NULL,
    scoring_version  TEXT NOT NULL,
    category_version TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    UNIQUE (dataset_id, execution_mode, prompt_version, model, scoring_version, category_version)
);

-- No foreign key to responses: skipped rows name rejected records that were never stored.
CREATE TABLE IF NOT EXISTS response_results (
    analysis_id   TEXT NOT NULL REFERENCES analyses (analysis_id),
    response_id   TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('pending', 'done', 'failed', 'skipped')),
    attempts      INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    labels_json   TEXT,
    score_json    TEXT,
    evidence_json TEXT,
    error         TEXT,
    reason        TEXT,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (analysis_id, response_id)
);

CREATE TABLE IF NOT EXISTS model_calls (
    call_id        TEXT PRIMARY KEY,
    analysis_id    TEXT NOT NULL REFERENCES analyses (analysis_id),
    response_id    TEXT NOT NULL,
    execution_mode TEXT NOT NULL CHECK (execution_mode IN ('local-model', 'replay', 'stub')),
    model          TEXT,
    latency_ms     INTEGER NOT NULL,
    input_tokens   INTEGER,
    output_tokens  INTEGER,
    cost_usd       REAL,
    outcome        TEXT NOT NULL,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    report_id   TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL UNIQUE REFERENCES analyses (analysis_id),
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_versions (
    version_id           TEXT PRIMARY KEY,
    report_id            TEXT NOT NULL REFERENCES reports (report_id),
    version_no           INTEGER NOT NULL CHECK (version_no >= 1),
    status               TEXT NOT NULL CHECK (status IN (
                             'draft', 'submitted', 'approved', 'rejected', 'expired', 'superseded')),
    revision             INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    content_json         TEXT NOT NULL,
    content_sha256       TEXT NOT NULL,
    created_by           TEXT NOT NULL,
    created_at           TEXT NOT NULL,
    submitted_at         TEXT,
    review_due_at        TEXT,
    approval_valid_until TEXT,
    UNIQUE (report_id, version_no)
);

CREATE TABLE IF NOT EXISTS review_decisions (
    decision_id TEXT PRIMARY KEY,
    version_id  TEXT NOT NULL UNIQUE REFERENCES report_versions (version_id),
    actor       TEXT NOT NULL,
    decision    TEXT NOT NULL CHECK (decision IN ('approve', 'reject')),
    comment     TEXT NOT NULL CHECK (length(comment) > 0),
    decided_at  TEXT NOT NULL
);
