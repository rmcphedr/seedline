# Seedline founder onboarding: local demo

Phase 1 adds a persistent founder and business profile beside the existing public funding explorer. It is a **local development demo**, not an account system. The demo API and pages are disabled unless `ENABLE_DEMO_MODE=true` and `APP_ENV=development` (or `local`/`test`). Preview, staging, and production deployment environment values disable them even if the flag is set. Keep the flag off in deployed settings.

## Start locally

Use the existing Docker Compose setup. Copy `.env.example` to `.env`, set `ADMIN_API_KEY`, then set:

```dotenv
APP_ENV=development
ENABLE_DEMO_MODE=true
```

Start the services and apply the additive migration:

```bash
docker network create bridge_windmill  # only if it does not already exist
docker compose up -d --build
docker compose exec api alembic upgrade head
```

Open [http://localhost:3000/explore](http://localhost:3000/explore). The **Create Demo Profile** button leads to `/demo`, where you can enter an optional display name. The wizard is at `/onboarding`; the profile dashboard is at `/dashboard`. The **View example founder** action creates a fictional, partially completed EcoPack Solutions profile and opens its dashboard. **Start Fresh Demo** creates a new empty profile and switches the current browser to it. Existing local demo rows are retained for inspection; this action does not delete them.

For direct development instead of Compose, set `APP_ENV=development` and `ENABLE_DEMO_MODE=true` in both the API process and `apps/web/.env.local`, along with the existing `API_BASE_URL` and `ADMIN_API_KEY` settings. Apply `alembic upgrade head` with a local PostgreSQL `DATABASE_URL` before starting the API.

The API creates a seven day, opaque session secret. Only its SHA-256 hash is stored in `demo_sessions`; the browser receives the secret in an HTTP-only, SameSite=Lax cookie. The Next.js same-origin route forwards that cookie to the local API. All profile reads and writes resolve the founder and organization from the server-side session. Browser supplied IDs do not authorize profile access. The demo API is at `/api/demo/{create,example,reset,context,founder,organization,funding-intent,details,interests,onboarding,completion,summary}`. The root admin key is not used for this local founder flow.

## Profile model and completion

Migration `0006_founder_onboarding` extends the existing `organizations` table, then adds `founders`, `organization_memberships`, `funding_intents`, `business_profile_details`, `founder_interests`, `onboarding_states`, and `demo_sessions`. A founder can have multiple memberships and a business can have multiple funding intents. The demo creates one of each. `founders.auth_user_id` is reserved for a future authenticated account; `demo_kind` identifies local fresh and example records. Ownership answers and founder interests are private to the session and have no public routes.

The backend calculates profile coverage from answered fields, separately from the onboarding journey status. Section weights live in `backend/profile_completion.py`: founder basics 10%, business overview 30%, funding goals 25%, business details 25%, interests 10%. Each section earns its weight in proportion to answered fields. Skipping gives no credit. Explicit `no`, `unsure`, `pre_revenue`, and `0` answers count; conditional follow-ups such as previous funding details when the answer is `no`, and year established when not incorporated, leave the denominator. Years in operation is asked and scored when an incorporation year cannot be derived. Optional sensitive ownership information is excluded from the score. The API also returns a prioritized list of missing fields useful for future funding discovery. This score does not imply eligibility or a funding match.

The initial profile fields were informed by the checked-in funding seed's stated geography, business type, stage, funding amount, and some ownership or operating-history conditions. The seed is unverified and must not be treated as a definitive set of program requirements. The onboarding flow does not change the enrichment or public publication pipeline.

## Checks

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
cd apps/web && npm run typecheck && npm run lint && npm run build
docker compose config
```

To check migration application without touching an existing database, point `DATABASE_URL` to a **fresh** PostgreSQL database and run `alembic upgrade head`, then `alembic current`. The API tests use an isolated in-memory SQLite database. A fresh browser context is useful for checking that two demo sessions have different profiles. Reload `/onboarding` to verify autosave and resume; use the dashboard Edit links to change business stage and funding goals.

## Future account transition

Production authentication, email verification, recommendations, application drafting, uploads, and founder networking are not implemented. When real accounts arrive, associate authenticated users through `founders.auth_user_id`, replace the demo session dependency with account membership checks, migrate only profiles deliberately claimed by a user, and disable `ENABLE_DEMO_MODE`. Existing demo sessions should then be expired or removed; they must never become production credentials.
