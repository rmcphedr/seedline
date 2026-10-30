from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from backend.discovery.models import SourceRegistry

TRACKING_PREFIXES = ("utm_",)
TRACKING_EXACT = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source"}


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise ValueError(f"Unsupported URL: {url}")
    host = parts.hostname.lower().rstrip(".")
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    path = parts.path.rstrip("/") or "/"
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_EXACT and not key.lower().startswith(TRACKING_PREFIXES)
    )
    return urlunsplit(("https", host, path, urlencode(query), ""))


def domain_matches(url: str, domain: str) -> bool:
    hostname = (urlsplit(url).hostname or "").lower().rstrip(".")
    allowed = domain.lower().strip().rstrip(".").removeprefix("www.")
    comparable = hostname.removeprefix("www.")
    return bool(allowed) and (comparable == allowed or comparable.endswith("." + allowed))


def known_source_ids(url: str, registry: SourceRegistry) -> list[str]:
    """Select the most specific matching section on shared domains."""
    candidates = [source for source in registry.sources if any(domain_matches(url, domain) for domain in source.domains)]
    if len(candidates) <= 1:
        return [source.id for source in candidates]
    target_path = urlsplit(url).path.lower().rstrip("/")
    scored = []
    for source in candidates:
        seed_path = urlsplit(str(source.url)).path.lower().rstrip("/")
        section = seed_path.rsplit("/", 1)[0]
        score = len(seed_path) if target_path == seed_path else (
            len(section) if section and target_path.startswith(section + "/") else 0
        )
        if score:
            scored.append((score, source.id))
    if not scored:
        return []
    best = max(score for score, _ in scored)
    return [source_id for score, source_id in scored if score == best]
