.PHONY: test lint ingest dev

test:
	uv run pytest tests/ -q

lint:
	uv run ruff check .
	uv run ruff format --check .

ingest:
	uv run python ingest.py

dev:
	uv run uvicorn backend.app:app --reload --port 8000
