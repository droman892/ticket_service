# ticket_service

An authenticated backend API for managing support tickets: agents and admins log in, view and update tickets, bulk-import them from CSV, and pull status/priority/customer summaries. Built as the backend counterpart to [csv_extractor](../csv_extractor) — same ticket fields and validation rules, now served over HTTP with real users, roles, and a database instead of local file processing.

**Status: early development.** The data model, database migrations, and authentication (login, JWT bearer tokens, role-based access control) are in place and tested. Ticket, user-management, import, and summary endpoints from `docs/requirements.md` are not implemented yet.

## Problem

`csv_extractor` processes ticket CSVs locally, one file at a time, with no persistence, no users, and no way for multiple people to work the same ticket queue. `ticket_service` is the version of that problem that a small support team could actually run day to day: shared ticket state in a real database, per-agent ownership rules, and an API that could sit behind a real frontend later.

## Who it's for

A small support team with two kinds of users:
- **Agents**, who work an assigned queue of tickets.
- **Admins**, who manage user accounts, can edit or reassign any ticket, and run bulk CSV imports.

Full detail on what each role can and can't do is in `docs/requirements.md`.

## Features

See `docs/requirements.md` for the full, locked specification. At a high level: authenticated login, ticket CRUD with an enforced lifecycle (a closed ticket is permanently immutable), per-agent ownership rules, filtered/paginated/sorted ticket listing, status/priority/customer summaries, and admin-only CSV bulk import with a per-row validation report.

**Implemented so far:** `POST /auth/login` (bearer token, 60-minute TTL), password hashing, and the `get_current_user`/`require_role` dependencies every other endpoint will build on.

## Architecture

FastAPI + PostgreSQL (SQLAlchemy 2.0, async, `asyncpg`), layered as routers (HTTP concerns only) → services (business logic, permission and lifecycle rules) → repositories (database access). Config and secrets come from environment variables, never from code (see `.env.example`).

```
src/
  main.py          FastAPI app
  config.py        environment-based settings
  db.py            async engine/session setup
  api/             routers (HTTP layer)
  services/        business logic, permission/lifecycle rules
  repositories/     database access
  models/          SQLAlchemy ORM models (source of truth for the schema)
  schemas/         Pydantic request/response shapes
  core/            security (password hashing, JWT)
alembic/           database migrations, generated from src/models
tests/             mirrors src/; runs against a real Postgres test database
docs/
  requirements.md  full functional/non-functional spec, acceptance criteria
  adr/             architecture decision records
docker-compose.yml local Postgres for dev + a separate test database
```

Two Postgres databases run side by side in the same container: `ticket_service` for local dev, `ticket_service_test` for the test suite, so tests never touch dev data (see `scripts/init-test-db.sql`).

## Setup

Requires Python 3.13 and Docker (for local PostgreSQL).

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
copy .env.example .env   # then fill in real values — never commit .env
docker compose up -d db
.venv\Scripts\python -m alembic upgrade head
```

## Usage

Not yet available — no HTTP endpoints are implemented.

## Tests

Requires the Postgres container to be running (`docker compose up -d db`) — the test suite runs real migrations against `ticket_service_test` and exercises actual database constraints, not mocks.

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\python -m mypy
```

## Security notes

Full detail will live in `docs/security.md` once there's an API surface to review; headline expectations are captured in `docs/requirements.md` §4 (password hashing, parameterized queries only, server-side role checks, no secrets in code/logs/README).

## Limitations

Pre-implementation. No frontend, no AI/LLM features, no cloud deployment — see `docs/requirements.md` §6 for the full, explicit non-goals list.

## Lessons learned

TBD — will be filled in as the project progresses.
