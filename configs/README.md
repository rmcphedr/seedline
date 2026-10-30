# Configuration

`sources.yaml` is the curated discovery source registry from the starter. Entries are search entry points, not verified funding opportunities. Sync them into `funding_sources` with `python -m backend.discovery.cli sync-sources`.

Runtime secrets and model pricing belong in environment variables and must never be committed. Update discovery rates from the [OpenAI API pricing page](https://developers.openai.com/api/docs/pricing) when enabling paid runs; estimates are distinct from billed totals.
