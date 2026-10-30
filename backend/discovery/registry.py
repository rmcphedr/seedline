from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.discovery.models import SourceRegistry
from backend.models import FundingSource, SourceKind

DEFAULT_REGISTRY = Path(__file__).resolve().parents[2] / "configs" / "sources.yaml"


def load_registry(path: str | Path = DEFAULT_REGISTRY) -> SourceRegistry:
    with Path(path).open(encoding="utf-8") as stream:
        return SourceRegistry.model_validate(yaml.safe_load(stream))


def sync_registry(db: Session, registry: SourceRegistry) -> dict[str, FundingSource]:
    sources = {}
    for entry in registry.sources:
        source = db.scalar(select(FundingSource).where(FundingSource.registry_key == entry.id))
        if source is None:
            source = db.scalar(select(FundingSource).where(FundingSource.name == entry.name))
        if source is None:
            source = FundingSource(name=entry.name, base_url=str(entry.url), kind=SourceKind.website)
        source.name = entry.name
        source.registry_key = entry.id
        source.base_url = str(entry.url)
        source.kind = SourceKind.directory if entry.kind == "directory" else SourceKind.website
        source.allowed_domains = entry.domains
        source.topics = entry.topics
        db.add(source)
        sources[entry.id] = source
    db.commit()
    return sources
