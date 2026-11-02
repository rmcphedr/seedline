# Seedline Assistant

The local demo assistant shares the existing founder profile with manual onboarding. It stores conversation messages and unconfirmed suggestions separately from the profile. Suggestions affect profile completion and funding recommendations only after the founder accepts them. The assistant never decides grant eligibility; the existing recommendation service recalculates it from confirmed profile values.

## Run locally

1. Start the database and apply `alembic upgrade head` (revisions `0007_assistant` and `0008_assistant_usage` add conversation, suggestion, provenance, and provider usage tables).
2. Set `APP_ENV=development` and `ENABLE_DEMO_MODE=true`. `SEEDLINE_ASSISTANT_MODE=mock` is the default. With Compose, these demo flags can be supplied to `docker compose up --build`.
3. Open `/demo`, create a fresh founder, and choose **Start with Seedline Assistant**. The manual form remains available from the assistant and onboarding pages.
4. Enter: “I'm developing a small company in Montreal that creates sustainable packaging for food businesses. We're already generating revenue and want funding to purchase new manufacturing equipment.” Review the suggestions and accept them.
5. Open `/recommendations`, select a promising opportunity with a missing eligibility field, and choose **Check eligibility with Seedline**. Answer its focused question and confirm the suggestion. The opportunity assessment updates when you return.

Mock mode recognizes the demonstration statement and a few common location, stage, employee, amount, incorporation, and funding-purpose phrases. It is deterministic and uses the same suggestion validation, confirmation, persistence, and recommendation paths as live mode. It does not create fake opportunities or eligibility decisions.

To use OpenRouter, set `SEEDLINE_ASSISTANT_MODE=live` in the API environment and restart the API. The assistant reuses `OPENROUTER_API_KEY` and `BRIDGE_ENRICHMENT_MODEL`; set `SEEDLINE_ASSISTANT_MODEL` only to override that model. The model must support OpenRouter's `json_schema` response format. The existing NVIDIA free model has reasoning disabled for structured responses, as in enrichment. API keys stay server-side; the browser calls only the local demo proxy. The assistant sends the current response, a compact set of business fields, and at most four short recent messages. It does not send the full founder profile or funding database. In an opportunity conversation, the backend chooses a target field from that opportunity's existing assessment. The model may reword that question but cannot choose another target.

## Storage and safeguards

- `assistant_conversations` belongs to a founder and organization, with optional opportunity context. The demo cookie is checked on every read and write.
- `assistant_messages` persists the conversation. A caller-supplied UUID makes message retries idempotent. `assistant_suggestions` records the proposed value, evidence excerpt, confidence, base profile value, and decision status.
- Extracted fields are restricted to an allowlist and validated with the same Pydantic patch schemas as manual onboarding. Evidence text must appear in the latest founder message. Unsupported fields and enum values are ignored. Conflicting suggestions for one field are discarded.
- Accept, edit, reject, and accept all use one confirmation endpoint. A changed base profile value blocks stale confirmation. Repeated confirmation does not write again. Confirmed suggestions call the existing profile service in one transaction and record `ai_confirmed` provenance; later manual edits record `manual`.
- Missing baseline matching fields come first, then missing criteria on promising opportunities, then other business context. Contextual conversations prioritize the selected opportunity's missing fields. Skipped or previously asked fields are not repeated. Inapplicable year questions are excluded based on incorporation status.
- OpenRouter failures do not alter the profile or persist a failed user message. The founder can retry or use manual onboarding. Mock mode needs no network or API key.
- Each successful OpenRouter response writes token usage to `assistant_usage` immediately, including when later extraction validation fails. The usage record contains token counts and provider metadata, not founder text or full prompts.

This first version handles concise text statements. More nuanced corrections, multilingual phrasing, and compound eligibility conditions still need richer extraction and human review. A future version should add server-side rate limiting before broader deployment; demo mode remains disabled outside local environments.
