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
