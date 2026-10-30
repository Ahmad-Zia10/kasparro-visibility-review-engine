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

## Model modes

Each answer is labelled by a classifier chosen with `MODEL_MODE` in `.env`. Every result records which
mode produced it.

- `replay` (default): reads saved outputs from `REPLAY_PATH`. Needs no model and no network. An answer
  with no saved output fails as `missing_replay`; nothing is guessed.
- `local`: calls a model served by [Ollama](https://ollama.com) at `OLLAMA_URL`, with temperature 0 and a
  JSON schema for the output. Every output it receives is appended to `REPLAY_PATH`. Results are labelled
  `local-model`. Nothing is paid; cost is recorded as empty.
- `stub`: canned outputs, used by the tests.

To use the local model (a one-time download of about 2 GB):

```
winget install Ollama.Ollama      # or see ollama.com for macOS / Linux
ollama pull qwen2.5:3b
```

Then set `MODEL_MODE=local` in `.env`. Switch back to `MODEL_MODE=replay` to rerun offline from the
saved outputs. Classification on a CPU takes tens of seconds per answer, so `MODEL_TIMEOUT_SECONDS`
defaults to 180.

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
