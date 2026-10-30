from urllib.parse import urlsplit

from backend.discovery.catalog import comparable_url
from backend.discovery.models import DiscoveredCandidate
from backend.discovery.normalize import canonicalize_url, domain_matches


def search_links_from_response(payload: object) -> set[str]:
    """Take URLs only from tool sources and citation annotations, never model prose."""
    if not isinstance(payload, dict):
        return set()
    urls: set[str] = set()

    def visit(obj):
        if isinstance(obj, dict):
            value = obj.get("url")
            if isinstance(value, str):
                try:
                    urls.add(canonicalize_url(value))
                except ValueError:
                    pass
            for child in obj.values():
                visit(child)
        elif isinstance(obj, list):
            for child in obj:
                visit(child)

    for output in payload.get("output", []):
        if not isinstance(output, dict):
            continue
        if output.get("type") == "web_search_call":
            action = output.get("action", {})
            if isinstance(action, dict):
                visit(action.get("sources", []))
        elif output.get("type") == "message":
            for content in output.get("content", []):
                if isinstance(content, dict):
                    visit(content.get("annotations", []))
    return urls


def grounded_candidates(
    candidates: list[DiscoveredCandidate], observed_urls: set[str], allowed_domains: list[str] | None, limit: int
) -> list[DiscoveredCandidate]:
    accepted = []
    seen = set()
    for candidate in candidates:
        canonical = canonicalize_url(str(candidate.url))
        if canonical not in observed_urls or canonical in seen:
            continue
        if allowed_domains and not any(domain_matches(canonical, domain) for domain in allowed_domains):
            continue
        accepted.append(candidate)
        seen.add(canonical)
        if len(accepted) >= limit:
            break
    return accepted


def citation_titles(payload: object) -> dict[str, str]:
    titles: dict[str, str] = {}
    if not isinstance(payload, dict):
        return titles

    def visit(obj):
        if isinstance(obj, dict):
            url = obj.get("url")
            title = obj.get("title")
            if isinstance(url, str) and isinstance(title, str) and title.strip():
                try:
                    titles.setdefault(canonicalize_url(url), title.strip())
                except ValueError:
                    pass
            for child in obj.values():
                visit(child)
        elif isinstance(obj, list):
            for child in obj:
                visit(child)

    visit(payload)
    return titles


def candidates_from_citations(
    accepted: list[DiscoveredCandidate], observed_urls: set[str], payload: object,
    known_urls: set[str], allowed_domains: list[str] | None, limit: int,
) -> list[DiscoveredCandidate]:
    """Keep a cited page when selection omits it and it is not already on file."""
    if len(accepted) >= limit:
        return accepted
    titles = citation_titles(payload)
    seen = set()
    for item in accepted:
        try:
            seen.add(canonicalize_url(str(item.url)))
        except ValueError:
            pass
    for url in sorted(observed_urls):
        if len(accepted) >= limit or url in seen:
            continue
        page = comparable_url(url)
        if page is None or page in known_urls:
            continue
        if allowed_domains and not any(domain_matches(url, domain) for domain in allowed_domains):
            continue
        host = (urlsplit(url).hostname or "the source").removeprefix("www.")
        accepted.append(DiscoveredCandidate(
            title=(titles.get(url) or f"Funding page on {host}")[:300],
            url=url, provider_hint=None, type_hint="unknown",
            reason_to_investigate="Cited by web search.",
        ))
        seen.add(url)
    return accepted
