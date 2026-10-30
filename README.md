# Kasparro AI-visibility review service

A small Python backend that reads 150 archived AI answers (ChatGPT, Gemini, Google AI Mode) to 50
prompts, labels and scores how Kasparro appears, and only exports a report after a reviewer approves
that exact version.

The data is a historical snapshot captured on 31 July 2026 (India, English). It is not a current
market ranking.

## Requirements

- Python 3.11 or later
- The assignment pack unzipped into `pack/` so that `pack/data/prompts.jsonl` exists (not in git)

## Setup

```
python -m venv .venv
.venv\Scripts\activate            # Windows
source .venv/bin/activate         # macOS / Linux
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env              # then set ANALYST_TOKEN and REVIEWER_TOKEN
```

Tokens must be at least 16 characters. One way to make one:

```
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Run

```
python -m app.db init             # create the SQLite schema
uvicorn app.main:app --reload     # API at http://127.0.0.1:8000, docs at /docs
```

## Test and lint

```
pytest -q
ruff check . && ruff format --check .
```

## Identities

There are two roles, set only in `.env`: the analyst (`ANALYST_TOKEN`) imports, analyses and edits;
the reviewer (`REVIEWER_TOKEN`) approves or rejects. Send the token as
`Authorization: Bearer <token>`. Any other header or body field that claims a role is ignored.

Errors always have the shape `{"error": "<code>", "detail": "<text>"}`.

## Example requests

Set `ANALYST_TOKEN` and `REVIEWER_TOKEN` in your shell to the values in `.env`. On Windows PowerShell,
use `curl.exe` instead of `curl`.

```
curl http://127.0.0.1:8000/health

# Import the pack from PACK_DIR: 201 the first time, 200 with the same dataset afterwards
curl -X POST http://127.0.0.1:8000/datasets -H "Authorization: Bearer $ANALYST_TOKEN"

# Counts and every rejected record with its line and reason
curl http://127.0.0.1:8000/datasets/<dataset_id> -H "Authorization: Bearer $REVIEWER_TOKEN"
```

The full flow (import, analyse, edit, submit, approve or reject, export) is added as each endpoint lands.
