# Bridge coding guide

## Architecture

- `apps/web`: Next.js App Router admin and public explorer. It calls the API from server components and server actions through `lib/api.ts`.
- `apps/api`: FastAPI HTTP routes, request validation, response contracts, and a simple admin key guard.
- `backend/models.py`: canonical SQLAlchemy persistence schema. `backend/schemas.py`: Pydantic API contracts. `backend/services.py`: database operations and review transitions.
- `infrastructure/alembic`: schema migrations. `tests`: isolated API/database tests. `configs`: future workflow configuration.
- `backend/discovery`: source registry, URL normalization, grounded candidate selection, optional OpenAI provider, CLI worker, and per-response usage accounting.

## Conventions

- Keep HTTP routes thin; put database reads and writes in services.
- Use UUID primary keys, UTC timestamps, explicit foreign keys, and migrations for schema changes.
- A funding program represents the enduring opportunity; a funding round represents one application cycle.
- Eligibility rules store sourced facts. Future matching assessments must use separate data structures.
- Preserve source URLs, content hashes, review decisions, and version snapshots in ingestion work.
- New opportunities must enter the pending review queue. Approval or rejection must update the program and review record in one transaction.
- Verification (`review_status` and `verified_at`), application status (derived from rounds), and publication (`published_at`) are separate. Only approved, verified, published programs may appear on public routes. Edits reset verification and publication.
- Admin routes require `ADMIN_API_KEY`; public explorer reads do not. The web admin uses Basic authentication with the same server-side key; server actions must check authorization independently.
- Future fetchers, extractors, and agents should have typed inputs and outputs, and call services to persist results. Do not put scraping or LLM calls in API routes.
- Discovery candidates are unverified leads. Only human action may promote one to a pending funding program; final program approval remains a separate review step.
- Record provider usage after each response, including when a later step fails. Admin discovery uses `OPENROUTER_API_KEY` and `BRIDGE_ENRICHMENT_MODEL`. The CLI `run-job --execute` path still requires an OpenAI key, model, and complete rate card. An admin search is superficial: it skips URLs and titles already stored as sources, candidates, or programs, and leaves new leads unverified.
- Keep secrets server-side. Before public deployment, enable `ADMIN_API_KEY` and protect the web dashboard with an identity layer or deployment access control.

## Checks

- Backend: `.venv/bin/python -m pytest -q` and `.venv/bin/ruff check .`
- Web: `cd apps/web && npm run typecheck && npm run lint && npm run build`
- Migration: `alembic upgrade head` against a fresh PostgreSQL database.
