# Changelog

All notable changes to the Marketplace Listing Quality Reviewer are documented
in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and
this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `CONTRIBUTING.md` — contribution guide: setup, code style, testing, PRs
- README quick-start section so a fresh clone can install, run, and test using
  only README steps

## [1.0.0]

### Added

- Deterministic listing validation (no AI): required fields, price format/range,
  title & description length, supported category, category attributes, condition
  enum, tag count/length, contact details, exact + near duplicates, keyword
  stuffing, caps/emoji
- RAG + LLM review over ingested policy PDFs with rule-ID grounding, citation
  validation, and graceful degradation when Groq is unavailable
- Structure-aware policy PDF chunking (`POL-`/`BRD-` rule IDs kept in-chunk)
- Hybrid BM25 + Pinecone retrieval with RRF fusion and cross-encoder reranking
- Reviewer workflow: approve / edit / reject, compare view, batch processing,
  append-only audit log, history
- FastAPI backend (`backend/app.py`) and minimal React + Vite frontend
- SQLite storage: listings, reviews, findings, decisions, ai_revisions
- Structured JSON application and AI-workflow logging
- pytest suite (19 tests) requiring no API keys
- GitHub Actions CI: lint, ruff format, tests with coverage, pip-audit,
  npm-audit, gitleaks
