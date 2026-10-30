"""Pages Bridge already knows, so a new search can skip them."""

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.discovery.normalize import canonicalize_url
from backend.models import FundingProgram, FundingSource, OpportunityCandidate


@dataclass(frozen=True)
class KnownLead:
    kind: str
    title: str
    url: str
    title_key: str | None


def comparable_url(url: str) -> str | None:
    try:
        canonical = canonicalize_url(url)
    except ValueError:
        return None
    parts = urlsplit(canonical)
    host = (parts.hostname or "").removeprefix("www.")
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    return urlunsplit(("https", host, parts.path, parts.query, ""))


def title_key(title: str | None) -> str | None:
    if not title:
        return None
    cleaned = " ".join("".join(char.lower() if char.isalnum() else " " for char in title).split())
    if len(cleaned) < 12:
        return None
    return cleaned


def load_known_leads(db: Session) -> list[KnownLead]:
    leads: list[KnownLead] = []
    programs = db.scalars(select(FundingProgram).order_by(FundingProgram.updated_at.desc())).all()
    for program in programs:
        urls = [program.url, *[round_.application_url for round_ in program.rounds]]
        leads.extend(_pages("program", program.title, urls))
    candidates = db.scalars(select(OpportunityCandidate).order_by(OpportunityCandidate.updated_at.desc())).all()
    for candidate in candidates:
        leads.extend(_pages("candidate", candidate.title or "", [candidate.canonical_url or candidate.url]))
    sources = db.scalars(select(FundingSource).order_by(FundingSource.updated_at.desc())).all()
    for source in sources:
        leads.extend(_pages("source", source.name, [source.base_url]))
    unique: list[KnownLead] = []
    seen: set[str] = set()
    for lead in leads:
        if lead.url in seen:
            continue
        seen.add(lead.url)
        unique.append(lead)
    return unique


def guided_query(query: str, leads: list[KnownLead], *, superficial: bool) -> str:
    parts = [query.strip()]
    if superficial:
        parts.append(
            "Stay superficial. Use web search results only. Return new funding opportunities, "
            "each with the official webpage URL. Include only basic facts that are obvious from search: "
            "the name, one sentence, geography, and audience. Do not investigate eligibility, amounts, or deadlines."
        )
    shown = [lead for lead in leads if lead.kind != "source"][:60]
    shown += [lead for lead in leads if lead.kind == "source"][:20]
    if shown:
        lines = [f"- {lead.title or 'Untitled'} ({lead.kind}): {lead.url}" for lead in shown]
        parts.append(
            "Already recorded. Do not return these pages or the same opportunity under another URL:\n"
            + "\n".join(lines)
        )
    return "\n\n".join(parts)


def _pages(kind: str, title: str, urls: list[str | None]) -> list[KnownLead]:
    pages: list[KnownLead] = []
    for url in urls:
        if not url:
            continue
        key = comparable_url(url)
        if key is None:
            continue
        pages.append(KnownLead(
            kind=kind, title=title or "", url=key,
            title_key=None if kind == "source" else title_key(title),
        ))
    return pages
