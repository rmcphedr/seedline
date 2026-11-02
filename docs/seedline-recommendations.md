# Founder funding recommendations

This local demo reads the same approved, verified, published funding programs as the public explorer. No recommendation records, new database fields, background jobs, or LLM calls are added. Results are calculated when the founder opens the dashboard or recommendation pages, so a saved profile edit changes the next assessment.

## Data mapping

| Funding record | Founder profile | Use |
| --- | --- | --- |
| `geography` | Business country, province, city | Eligibility for recognized Canada, Quebec, and Montreal labels; relevance when matched |
| `organization_types` | Legal structure | Eligibility for business, nonprofit, and cooperative types |
| `eligibility_rules` with `criterion`, `requirement`, `source_url` | Incorporation status, establishment year or years active, industry, stage, employee count, annual revenue range, funding purposes | Conservative requirement checks when the wording is unambiguous; original source retained in each result |
| `details.sectors`, title, summary, `details.description`, `details.objectives` | Industry, business description, project description, funding purposes, stage | Relevance only; sectors and descriptive text are not treated as eligibility rules |
| `funding_type` | Preferred funding types | Relevance |
| `amount_min`, `amount_max`, `currency` | Funding amount sought | Display; no eligibility claim from amount alone |
| `rounds.status`, `rounds.deadline` | None | Exclude expired or closed programs; display and deadline filtering |

The database inspection on 2026-10-31 found 12 published programs with enrichment details and 10 with a current or unconfirmed round after excluding expired calls. Their sourced rules range from simple age and incorporation limits to compound prose. Many programs have no structured sector, amount, organization type, or deadline. The engine preserves this distinction: an absent opportunity criterion is marked `opportunity_data_missing`; a known requirement needing a profile answer is `profile_missing`; prose that cannot be safely interpreted is `unsupported_rule`.

## Decision model

Eligibility and relevance are separate. Every check is `met`, `not_met`, or `unknown`, with a reason and source URL when available. Any clear conflict produces `potentially_ineligible`; any unknown without a conflict produces `needs_information`; only recorded requirements that can all be checked and met produce `likely_eligible`. These labels never confirm funding eligibility. The original requirements remain visible on the detail page.

A basic profile needs business country, at least one industry, and a funding purpose before relevance ranking appears. This gate is separate from the existing profile completion percentage. Rankings use configurable weights in `backend/recommendations.py`: industry 30, funding purpose 25, business stage 10, project text 10, geography 15, and preferred funding type 10. Each category contributes only when its signal is supported by the saved profile and opportunity record. The score is a relevance indicator out of 100, not a probability of success.

The first pass can evaluate recognized geography, structured applicant types, simple incorporation and nonprofit requirements, minimum or maximum operating years, exact industry and stage rules, simple employee limits, coarse revenue thresholds, and explicit funding-purpose rules. It deliberately leaves founder age and citizenship, percentage ownership, banking relationships, board authority, head-office or lease conditions, revenue capability percentages, and compound alternatives for manual review. Broad `details.sectors` values are ranking signals only.

## Local demonstration

1. Start PostgreSQL and run `alembic upgrade head` if needed. The existing published funding records are required for live results.
2. Run API and web with `APP_ENV=development` and `ENABLE_DEMO_MODE=true` (for Compose, use `APP_ENV=development ENABLE_DEMO_MODE=true docker compose up --build`).
3. Open `/demo`, load the fictional example founder, and open `/dashboard` or `/recommendations`.
4. Open a recommendation such as Fonds Jeunes Entreprises. The sourced “less than five years” criterion asks for Year established when the field is empty.
5. Follow Update Profile, enter a year, then use Back to recommendation after saving. The detail page fetches a fresh assessment. The public `/explore` route remains available without a demo session.

Because source records and dates change, the exact list and ranking depend on the local database at demonstration time. Expired calls are not shown as current recommendations.
