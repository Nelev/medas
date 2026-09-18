# medas-api

The backend: chat endpoints, Postgres persistence, and the RAG pipeline.

Setup, the API surface, the data model and troubleshooting all live in the
[root README](../README.md) — kept in one place so the two packages cannot
document the same contract differently.

```bash
uv sync --group dev                 # install
uv run alembic upgrade head         # migrate
uv run fastapi dev main.py          # run, on :8000
uv run ruff check . && uv run pytest -q
```
