import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.discovery.models import UsageRecord
from backend.models import DiscoveryUsage


@dataclass(frozen=True)
class CostRates:
    input_per_million: Decimal
    cached_input_per_million: Decimal
    cache_write_per_million: Decimal
    output_per_million: Decimal
    web_search_per_call: Decimal

    @classmethod
    def from_env(cls) -> "CostRates | None":
        names = (
            "BRIDGE_INPUT_USD_PER_1M",
            "BRIDGE_CACHED_INPUT_USD_PER_1M",
            "BRIDGE_CACHE_WRITE_USD_PER_1M",
            "BRIDGE_OUTPUT_USD_PER_1M",
            "BRIDGE_WEB_SEARCH_USD_PER_CALL",
        )
        values = [os.getenv(name) for name in names]
        if not any(values):
            return None
        if not all(values):
            raise ValueError("Set all five Bridge discovery rate variables to enable cost estimates")
        rates = [Decimal(value) for value in values]
        if any(rate < 0 for rate in rates):
            raise ValueError("Discovery rates cannot be negative")
        return cls(*rates)

    def snapshot(self) -> dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}


def estimate_cost(usage: UsageRecord, rates: CostRates) -> Decimal:
    ordinary = max(usage.input_tokens - usage.cached_input_tokens - usage.cache_write_tokens, 0)
    amount = (
        Decimal(ordinary) * rates.input_per_million
        + Decimal(usage.cached_input_tokens) * rates.cached_input_per_million
        + Decimal(usage.cache_write_tokens) * rates.cache_write_per_million
        + Decimal(usage.output_tokens) * rates.output_per_million
    ) / Decimal(1_000_000)
    amount += Decimal(usage.web_search_calls) * rates.web_search_per_call
    return amount.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def record_usage(db: Session, job_id, usage: UsageRecord, rates: CostRates | None) -> DiscoveryUsage:
    if usage.reported_cost_usd is not None:
        estimated_cost = usage.reported_cost_usd
        rate_snapshot = {"source": "provider"}
    else:
        estimated_cost = estimate_cost(usage, rates) if rates else None
        rate_snapshot = rates.snapshot() if rates else None
    item = DiscoveryUsage(
        job_id=job_id,
        provider=usage.provider,
        model=usage.model,
        operation=usage.operation,
        response_id=usage.response_id,
        input_tokens=usage.input_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        cache_write_tokens=usage.cache_write_tokens,
        output_tokens=usage.output_tokens,
        web_search_calls=usage.web_search_calls,
        estimated_cost_usd=estimated_cost,
        rate_snapshot=rate_snapshot,
        raw_usage=usage.raw_usage,
    )
    db.add(item)
    db.commit()
    return item


def usage_summary(db: Session, since: datetime | None = None) -> dict:
    if since is None:
        now = datetime.now(UTC)
        since = datetime(now.year, now.month, 1, tzinfo=UTC)
    rows = db.scalars(select(DiscoveryUsage).where(DiscoveryUsage.created_at >= since)).all()
    known_costs = [row.estimated_cost_usd for row in rows if row.estimated_cost_usd is not None]
    return {
        "period_start": since,
        "response_count": len(rows),
        "input_tokens": sum(row.input_tokens for row in rows),
        "cached_input_tokens": sum(row.cached_input_tokens for row in rows),
        "output_tokens": sum(row.output_tokens for row in rows),
        "web_search_calls": sum(row.web_search_calls for row in rows),
        "estimated_cost_usd": sum(known_costs, Decimal(0)) if len(known_costs) == len(rows) and rows else None,
        "cost_is_partial": bool(known_costs) and len(known_costs) < len(rows),
    }


def list_usage(db: Session, job_id=None, limit: int = 200) -> list[DiscoveryUsage]:
    query = select(DiscoveryUsage)
    if job_id:
        query = query.where(DiscoveryUsage.job_id == job_id)
    return db.scalars(query.order_by(DiscoveryUsage.created_at.desc()).limit(limit)).all()
