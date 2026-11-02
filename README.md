# Bridge — AI Funding Navigator

For the local Seedline founder profile and onboarding demo, see [Seedline founder onboarding](docs/seedline-onboarding.md).
For personalized funding assessments, see [Founder funding recommendations](docs/seedline-recommendations.md).
For mock and live conversational onboarding, see [Seedline Assistant](docs/seedline-assistant.md).

Funding intelligence scaffold: a FastAPI service, PostgreSQL schema, Next.js admin dashboard, and an opt-in discovery worker. It records funding sources, stages unverified candidate URLs, tracks provider usage, and supports human review. No model calls run automatically.

## Layout

| Path | Purpose |
| --- | --- |
| `apps/web` | Next.js App Router dashboard with Tailwind and local shadcn/ui components |
| `apps/api` | FastAPI routes and OpenAPI documentation |
| `backend` | SQLAlchemy models, Pydantic schemas, services, discovery worker, CSV importer, sample seed |
| `infrastructure` | Dockerfiles and Alembic migration environment |
| `tests` | API and database behavior tests |
| `configs` | Curated discovery source registry |
| `data` | Original 30-row funding seed CSV |

Programs are canonical opportunities. Each program can have multiple application rounds and factual eligibility rules. Source documents and versions preserve provenance and history; new programs require a review decision before their status becomes approved. Discovery candidates are only URL leads. A person can promote one to a pending program, then separately approve or reject that program after verification.

## Local start with Docker Compose

Requirements: Docker with Compose. Copy `.env.example` to `.env` and set a strong `ADMIN_API_KEY`. The admin UI uses username `admin` and that key as its password. Public explorer pages do not require it.

```bash
cp .env.example .env
docker network create bridge_windmill
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python -m backend.funding_seed
```

Open [dashboard](http://localhost:3000) and [API docs](http://localhost:8000/docs). The health check is at `http://localhost:8000/health`.

## Run services directly

Start PostgreSQL with `docker compose up -d db`, then:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
export DATABASE_URL=postgresql+psycopg://bridge:bridge@localhost:5432/bridge
.venv/bin/alembic upgrade head
.venv/bin/python -m backend.funding_seed
export ADMIN_API_KEY=your-strong-admin-key
.venv/bin/uvicorn apps.api.main:app --reload
```

In another terminal:

```bash
cd apps/web
cp .env.example .env.local
# Set ADMIN_API_KEY to the same value as the API before starting.
npm install
npm run dev
```

The API accepts a Supabase PostgreSQL connection string through `DATABASE_URL`; use a server-side connection string and keep it out of the web environment. `ADMIN_API_KEY` is required for all admin API routes and the web admin's Basic authentication. Set the same server-side value in both services. Use HTTPS and a full identity/access-control layer before a public production deployment. This scaffold is compatible with Vercel for `apps/web` and a Dockerized VPS for the API.

## Opportunity administration and explorer

Open `/admin/sources` to manage classified resource pages, `/admin/opportunities` to search and filter all records, and `/admin/opportunities/[id]` to edit a program, its application rounds, and its sourced eligibility requirements. The legacy `/` operations workspace remains available for ingestion, discovery, and review. An edit resets verification and removes the record from public view. Verification records when a human approved the opportunity; publication is a separate admin action.

The public `/explore` and `/explore/[id]` pages use unauthenticated read-only API endpoints. Only verified and published programs are returned. Application status is derived from funding rounds, while organization types are selected only after confirming them. Seed records start unpublished. The admin detail page can launch enrichment and inspect staged proposals.

The supplied CSV produces 12 pending programs, four unverified financing candidates, and 14 source-only listings. The source registry may already contain some URLs, so the number of newly created source rows depends on the database. Re-running the importer preserves reviews and does not duplicate records.

## Import the funding seed

`data/bridge_funding_seed_30.csv` is a supplied starting list, not a verification of current program terms. After migrating the database, run `.venv/bin/python -m backend.funding_seed` (or the Docker command above). Set `DATABASE_URL` for the database you want to update. You can pass a different CSV path as the command's argument if it has the same columns.

The importer routes specific calls and financing programs with explicit grant, non-repayable contribution, or loan labels into `funding_programs` and the pending `review_queue`. Financing entries whose type cannot be inferred safely enter `opportunity_candidates`. Directory, grantmaker listing, and procurement portal entries become `funding_sources` for later discovery. All 30 original rows, the file hash, and the zero-model-call count are recorded in a completed `ingestion_jobs` entry; program versions and candidate data retain their individual CSV rows. CSV status, audience, and notes are unverified claims. The dated call has an unknown round status and no structured deadline until someone checks its cutoff time and time zone.

The import makes no model calls and creates no `discovery_usage` charges. Re-running it reuses URLs already in the database, preserves existing review decisions, and avoids a duplicate import job for the same file bytes.

## Discovery and spending controls

The starter's curated list lives in `configs/sources.yaml`. Its URL canonicalization, domain matching, and cited-link checks now feed the existing `opportunity_candidates` table. The separate SQLite staging store is not used. A candidate must match a URL in a web-search tool source or citation annotation; model prose alone cannot create a candidate. Candidates stay unverified until a person promotes one. Promotion creates a pending program and version record, not a published approval.

Set up the registry and queue a job without making any paid calls:

```bash
.venv/bin/python -m backend.discovery.cli sources
.venv/bin/python -m backend.discovery.cli sync-sources
.venv/bin/python -m backend.discovery.cli queue --mode trusted --source-key wage --query 'Funding for Canadian gender equality nonprofits' --limit 8
.venv/bin/python -m backend.discovery.cli usage
```

The `queue` command prints a job UUID. `run-job <UUID>` previews that job and makes no API request. The dashboard's Ingestion section can queue jobs and show monthly and per-job response counts, token use, web-search calls, and estimated USD. The API also exposes individual ledger entries at `GET /discovery/usage` (optionally filtered by `job_id`). Its Discovery section shows unverified candidates and lets an admin dismiss or send one to the program review queue.

Admins can also run a search from `/admin/discovery`. A request such as "find 5 more opportunities in Canada that are women-focused" is passed to the discovery agent, which looks for official pages and basic searchable facts only. The agent is given the URLs and titles already stored as sources, candidates, and programs. Matching pages are skipped instead of saved again. Each new lead keeps the webpage it came from and stays unverified until someone promotes it. That search uses `OPENROUTER_API_KEY` and `BRIDGE_ENRICHMENT_MODEL`, the same model as enrichment. If the key is missing, the run is saved as failed and no provider call is made.

When you later choose to enable live discovery, install the optional extra (`.venv/bin/pip install -e '.[dev,discovery]'`), configure `OPENAI_API_KEY`, `BRIDGE_DISCOVERY_MODEL`, and all five `BRIDGE_*_USD_*` rate variables in the server environment, then run `.venv/bin/python -m backend.discovery.cli run-job <UUID> --execute`. The worker refuses paid execution when the key, model, or rate card is missing. Rates are not hard-coded because they can change; confirm them against the [current OpenAI API pricing page](https://developers.openai.com/api/docs/pricing) for the exact model and tool. Each provider response saves its token counts, web-search call count, response ID, rate snapshot, and estimated cost. Estimates are for monitoring; use provider billing for authoritative charges. There is no automatic scheduler or hard dollar cap in this scaffold.

## Development checks

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
cd apps/web && npm run typecheck && npm run lint && npm run build
```

For schema changes, update models and create a new Alembic revision. Keep old migrations immutable.

## Windmill enrichment

The admin can queue enrichment jobs for selected funding opportunities. Windmill runs a versioned flow that calls Bridge's worker-only API to load, fetch, extract, validate, and stage each proposal. The opportunity detail page shows source evidence, conflicts, and editable proposed values. Applying selected fields sends the record through normal verification before publication; rejection leaves the record unchanged. See [the local Windmill setup and smoke test](bridge-windmill/README.md).
