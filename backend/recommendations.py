"""On-demand, conservative eligibility checks and separate relevance ranking."""

import re
import unicodedata
from datetime import UTC
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import models as m
from backend import onboarding

SCORE_WEIGHTS = {"industry": 30, "funding_purpose": 25, "business_stage": 10,
                 "project_text": 10, "geography": 15, "funding_type": 10}
INDUSTRY_TERMS = {
    "technology": ("technology", "software", "digital"),
    "manufacturing": ("manufactur", "industrial", "production"),
    "sustainable_manufacturing": ("sustainab", "compost", "reusab", "circular", "green manufactur"),
    "health": ("health", "medical", "biotech"),
    "food_agriculture": ("food", "agricultur", "farm"),
    "retail": ("retail", "commerce", "shop"),
    "professional_services": ("professional service", "consult"),
    "creative": ("art", "cultur", "creative"),
    "education": ("educat", "learning", "training"),
    "clean_energy": ("clean energy", "renewable", "solar", "wind energy"),
    "social_impact": ("social", "community", "non-profit", "nonprofit"),
}
PURPOSE_TERMS = {
    "research": ("research", "r&d"), "product": ("product develop", "prototype"),
    "equipment": ("equipment", "machinery"), "hiring": ("hiring", "recruit", "staff"),
    "marketing": ("marketing", "advertis"), "expansion": ("expansion", "grow", "scale"),
    "training": ("training", "skills"), "launch": ("launch", "startup", "start-up"),
}
STOPWORDS = {"about", "after", "also", "and", "business", "businesses", "funding", "grant",
             "loan", "more", "program", "project", "their", "this", "with", "your", "for", "the"}
FIELD_ORDER = ("business_country", "business_province", "business_city", "industry", "business_stage",
               "legal_structure", "incorporation_status", "year_established", "years_in_operation",
               "employee_count", "annual_revenue_range", "funding_purposes", "ownership_eligibility")
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                "seven": 7, "eight": 8, "nine": 9, "ten": 10}
YEAR_VALUE = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
REVENUE_RANGES = {"pre_revenue": (0, 0), "under_100k": (0, 100000),
                  "100k_500k": (100000, 500000), "500k_1m": (500000, 1000000),
                  "1m_5m": (1000000, 5000000), "over_5m": (5000000, None)}


def normalized(value: object) -> str:
    return unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()


def has_term(text: str, term: str) -> bool:
    return bool(re.search(rf"\b{re.escape(term)}\b", text)) if len(term) <= 4 else term in text


def criterion(label: str, requirement: str, status: str, explanation: str, *, field: str | None = None,
              unknown_reason: str | None = None, rule: m.EligibilityRule | None = None,
              source_url: str | None = None) -> dict:
    return {"label": label, "requirement": requirement, "status": status, "explanation": explanation,
            "field": field, "unknown_reason": unknown_reason, "source_rule_id": rule.id if rule else None,
            "source_url": rule.source_url if rule else source_url}


def location_check(program: m.FundingProgram, org: m.Organization) -> dict:
    place = normalized(program.geography).strip()
    if not place:
        return criterion("Business location", "Location restriction not recorded", "unknown",
                         "The opportunity has no structured geographic restriction.",
                         unknown_reason="opportunity_data_missing")
    mapping = {"canada": ("country", "CA", "business_country"),
               "based in canada": ("country", "CA", "business_country"),
               "quebec": ("region", "QC", "business_province"),
               "montreal": ("city", "montreal", "business_city")}
    if place not in mapping:
        return criterion("Business location", program.geography, "unknown",
                         "This geographic label needs a manual check.", unknown_reason="unsupported_rule")
    attr, expected, field = mapping[place]
    value = normalized(getattr(org, attr)).strip()
    if attr == "region":
        value = "qc" if value in {"quebec", "qc", "pq"} else value
        expected = expected.lower()
    elif attr == "city":
        value = "montreal" if value in {"montreal"} else value
    else:
        expected = expected.lower()
    if not value:
        return criterion("Business location", program.geography, "unknown",
                         "Add your business location to assess this restriction.", field=field,
                         unknown_reason="profile_missing", source_url=program.url)
    status = "met" if value == expected else "not_met"
    return criterion("Business location", program.geography, status,
                     "Your saved business location matches this restriction." if status == "met" else
                     "Your saved business location differs from this restriction.", field=field,
                     source_url=program.url)


def applicant_type_check(program: m.FundingProgram, org: m.Organization) -> dict | None:
    allowed = set(program.organization_types or [])
    if not allowed:
        return None
    structure = org.legal_structure
    if not structure or structure == "other":
        return criterion("Applicant type", ", ".join(sorted(allowed)), "unknown",
                         "Clarify your legal structure to check eligible applicant types.",
                         field="legal_structure", unknown_reason="profile_missing", source_url=program.url)
    kind = "nonprofit" if structure == "nonprofit" else "cooperative" if structure == "cooperative" else "business"
    status = "met" if kind in allowed else "not_met"
    return criterion("Applicant type", ", ".join(sorted(allowed)), status,
                     "Your legal structure is listed as eligible." if status == "met" else
                     "Your legal structure is not among the listed applicant types.",
                     field="legal_structure", source_url=program.url)


def _rule_checks(rule: m.EligibilityRule, org: m.Organization, details: m.BusinessDetails,
                 intent: m.FundingIntent) -> list[dict]:
    text = normalized(rule.requirement).strip()
    remaining = text
    checks: list[dict] = []

    def add(label: str, field: str, value: object, passes: bool | None, matched: str):
        nonlocal remaining
        remaining = remaining.replace(matched, " ", 1)
        if value is None or value == "" or value == []:
            checks.append(criterion(label, rule.requirement, "unknown", "Add or clarify this profile field to assess the sourced requirement.",
                                    field=field, unknown_reason="profile_missing", rule=rule))
        elif passes is None:
            checks.append(criterion(label, rule.requirement, "unknown", "The available profile value is too imprecise to confirm this threshold.",
                                    field=field, unknown_reason="unsupported_rule", rule=rule))
        else:
            checks.append(criterion(label, rule.requirement, "met" if passes else "not_met",
                                    "Your profile supports this sourced requirement." if passes else
                                    "Your profile conflicts with this sourced requirement.", field=field, rule=rule))

    # Rules with alternatives or negation cannot be safely reduced to one required profile value.
    if re.search(r"\b(or|either|unless|except)\b|\b(ou|soit)\b", text):
        nonprofit = re.search(r"\bnot[- ]for[- ]profit\b|\bnon[- ]?profits?\b", text)
        if nonprofit and not re.search(r"\bor\s+(?:a\s+)?(?:business|company|corporation|individual)", text):
            add("Nonprofit structure", "legal_structure", None if org.legal_structure == "other" else org.legal_structure,
                org.legal_structure == "nonprofit", nonprofit.group())
        checks.append(criterion(rule.criterion, rule.requirement, "unknown",
                                "Alternative or exception clauses need manual review.",
                                unknown_reason="unsupported_rule", rule=rule))
        return checks
    if normalized(rule.criterion) in {"industry", "sector"}:
        industry = next((name for name, terms in INDUSTRY_TERMS.items() if text == name.replace("_", " ") or
                         any(text == term for term in terms)), None)
        if industry:
            known = org.industry or []
            match = industry in known or industry == "manufacturing" and "sustainable_manufacturing" in known
            return [criterion("Industry", rule.requirement, "met" if match else "not_met" if known else "unknown",
                              "Your industry matches the sourced sector." if match else "Your industry does not match this sourced sector." if known else "Add your industry to assess this requirement.",
                              field="industry", unknown_reason="profile_missing" if not known else None, rule=rule)]
    if normalized(rule.criterion) in {"business stage", "stage"}:
        stage = next((name for name in ("idea", "pre_launch", "prototype", "early_revenue", "growth", "established")
                      if text == name.replace("_", " ")), None)
        if stage:
            value = org.business_stage
            return [criterion("Business stage", rule.requirement, "met" if value == stage else "not_met" if value else "unknown",
                              "Your business stage matches." if value == stage else "Your business stage differs." if value else "Add your business stage.",
                              field="business_stage", unknown_reason="profile_missing" if not value else None, rule=rule)]
    size = re.fullmatch(r"(?:fewer than|less than|under)\s+(\d+)\s+employees?", text)
    if size and normalized(rule.criterion) in {"organization size", "employees", "size"}:
        count = details.employee_count
        return [criterion("Organization size", rule.requirement,
                          "unknown" if count is None else "met" if count < int(size.group(1)) else "not_met",
                          "Add your employee count." if count is None else "Your employee count is within this limit." if count < int(size.group(1)) else "Your employee count exceeds this limit.",
                          field="employee_count", unknown_reason="profile_missing" if count is None else None, rule=rule)]
    revenue = re.fullmatch(r"annual revenue (?:under|below|less than) \$?([\d,]+)", text)
    if revenue and normalized(rule.criterion) in {"annual revenue", "revenue"}:
        value = details.annual_revenue_range
        bounds = REVENUE_RANGES.get(value or "")
        threshold = int(revenue.group(1).replace(",", ""))
        status = "unknown" if not bounds else "met" if bounds[1] is not None and bounds[1] <= threshold else \
                 "not_met" if bounds[0] >= threshold else "unknown"
        reason = "profile_missing" if not bounds else "unsupported_rule" if status == "unknown" else None
        return [criterion("Annual revenue", rule.requirement, status,
                          "Add an annual revenue range." if not bounds else "Your range is within this limit." if status == "met" else
                          "Your range exceeds this limit." if status == "not_met" else "Your revenue range crosses this threshold.",
                          field="annual_revenue_range", unknown_reason=reason, rule=rule)]
    if re.search(r"\bcanadian\b", text) and re.search(r"\b(business(?:es)?|organizations?|nonprofits?|compan(?:y|ies))\b", text):
        add("Canadian business", "business_country", org.country, normalized(org.country) == "ca", "canadian")
    if "incorporated" in text:
        state = org.incorporation_status
        add("Incorporation", "incorporation_status", None if state in {None, "unsure", "in_progress"} else state,
            state == "incorporated", "incorporated")
    if re.search(r"\bnot[- ]for[- ]profit\b|\bnon[- ]?profits?\b", text):
        match = re.search(r"\bnot[- ]for[- ]profit\b|\bnon[- ]?profits?\b", remaining)
        if match:
            add("Nonprofit structure", "legal_structure", None if org.legal_structure == "other" else org.legal_structure,
                org.legal_structure == "nonprofit", match.group())
    years_match = re.search(rf"(?:at least|minimum of)\s+{YEAR_VALUE}\s+years?(?:\s+of\s+operation)?|(?:operating for )?{YEAR_VALUE}\s+years?\s+(?:of operation|or more)", text)
    if years_match:
        word = years_match.group(1) or years_match.group(2)
        years = int(word) if word.isdigit() else NUMBER_WORDS[word]
        actual = m.now().year - org.year_established if org.year_established else details.years_in_operation
        field = "year_established" if org.incorporation_status == "incorporated" else "years_in_operation"
        # A year alone does not establish the anniversary date at the exact threshold.
        passes = None if actual == years else actual is not None and actual > years
        add(f"At least {years} years operating", field, actual, passes, years_match.group())
    young_match = re.search(rf"(?:less than|fewer than|under)\s+{YEAR_VALUE}\s+years?\s+of\s+existence", text)
    if young_match:
        word = young_match.group(1)
        years = int(word) if word.isdigit() else NUMBER_WORDS[word]
        actual = m.now().year - org.year_established if org.year_established else details.years_in_operation
        field = "year_established" if org.incorporation_status == "incorporated" else "years_in_operation"
        passes = None if actual == years else actual is not None and actual < years
        add(f"Less than {years} years in operation", field, actual, passes, young_match.group())
    if normalized(rule.criterion) in {"funding purpose", "project purpose"}:
        purposes = [key for key, terms in PURPOSE_TERMS.items() if any(term in text for term in terms)]
        if len(purposes) == 1:
            key = purposes[0]
            add("Funding purpose", "funding_purposes", intent.funding_purposes,
                key in (intent.funding_purposes or []), text)
    leftover = re.sub(r"\b(?:business(?:es)?|organizations?|compan(?:y|ies)|operating|for|at|least|of|the|with|a|an|must|have|be|in|to|eligible)\b|[^a-z0-9]+", " ", remaining).strip()
    if leftover or not checks:
        checks.append(criterion(rule.criterion, rule.requirement, "unknown",
                                "Other sourced conditions cannot be checked from structured profile data.",
                                unknown_reason="unsupported_rule", rule=rule))
    return checks


def eligibility(program: m.FundingProgram, org: m.Organization, details: m.BusinessDetails,
                intent: m.FundingIntent) -> tuple[str, list[dict]]:
    checks = [location_check(program, org)]
    applicant = applicant_type_check(program, org)
    if applicant:
        checks.append(applicant)
    if program.eligibility_rules:
        for rule in program.eligibility_rules:
            checks.extend(_rule_checks(rule, org, details, intent))
    else:
        checks.append(criterion("Eligibility rules", "No sourced eligibility rules recorded", "unknown",
                                "Check the official program source for additional conditions.",
                                unknown_reason="opportunity_data_missing", source_url=program.url))
    status = "potentially_ineligible" if any(c["status"] == "not_met" for c in checks) else \
             "needs_information" if any(c["status"] == "unknown" for c in checks) else "likely_eligible"
    return status, checks


def _opportunity_text(program: m.FundingProgram) -> str:
    details = program.details or {}
    parts = [program.title, program.summary or "", str(details.get("description") or "")]
    for key in ("sectors", "objectives"):
        value = details.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    return normalized(" ".join(parts))


def industry_tags(program: m.FundingProgram) -> list[str]:
    text = _opportunity_text(program)
    tags = [name for name, terms in INDUSTRY_TERMS.items()
            if name != "sustainable_manufacturing" and any(has_term(text, term) for term in terms)]
    if "manufacturing" in tags and any(has_term(text, term) for term in INDUSTRY_TERMS["sustainable_manufacturing"]):
        tags.append("sustainable_manufacturing")
    return tags


def relevance(program: m.FundingProgram, org: m.Organization, intent: m.FundingIntent,
              location: dict) -> tuple[int, dict[str, int]]:
    text = _opportunity_text(program)
    breakdown = {key: 0 for key in SCORE_WEIGHTS}
    tags = industry_tags(program)
    if any(tag in tags or tag == "sustainable_manufacturing" and "manufacturing" in tags for tag in org.industry):
        breakdown["industry"] = SCORE_WEIGHTS["industry"]
    if any(any(term in text for term in PURPOSE_TERMS.get(purpose, ())) for purpose in intent.funding_purposes):
        breakdown["funding_purpose"] = SCORE_WEIGHTS["funding_purpose"]
    stage_terms = {"idea": ("startup", "launch", "new business"), "pre_launch": ("startup", "launch"),
                   "prototype": ("prototype", "pilot"), "early_revenue": ("startup", "growth", "expansion"),
                   "growth": ("growth", "expansion", "scale"), "established": ("established", "expansion")}
    if any(term in text for term in stage_terms.get(org.business_stage or "", ())):
        breakdown["business_stage"] = SCORE_WEIGHTS["business_stage"]
    profile_words = {word for word in re.findall(r"[a-z]{5,}", normalized((org.description or "") + " " +
                     (intent.project_description or ""))) if word not in STOPWORDS}
    opportunity_words = set(re.findall(r"[a-z]{5,}", text)) - STOPWORDS
    if len(profile_words & opportunity_words) >= 2:
        breakdown["project_text"] = SCORE_WEIGHTS["project_text"]
    if location["status"] == "met":
        breakdown["geography"] = SCORE_WEIGHTS["geography"]
    preferred = set(intent.preferred_funding_types)
    if program.funding_type.value in preferred or program.funding_type == m.FundingType.investment and "equity" in preferred:
        breakdown["funding_type"] = SCORE_WEIGHTS["funding_type"]
    return sum(breakdown.values()), breakdown


def current_deadline(program: m.FundingProgram) -> str | None:
    now = m.now()
    dates = [round_.deadline for round_ in program.rounds if round_.status != m.RoundStatus.closed and round_.deadline
             and (round_.deadline.replace(tzinfo=UTC) if round_.deadline.tzinfo is None else round_.deadline) >= now]
    if not dates:
        return None
    return min(date.replace(tzinfo=UTC) if date.tzinfo is None else date for date in dates).isoformat()


def expired(program: m.FundingProgram) -> bool:
    if not program.rounds:
        return False
    live = [r for r in program.rounds if r.status != m.RoundStatus.closed and
            (r.deadline is None or (r.deadline.replace(tzinfo=UTC) if r.deadline.tzinfo is None else r.deadline) >= m.now())]
    return not live


def assess(program: m.FundingProgram, org: m.Organization, intent: m.FundingIntent,
           details: m.BusinessDetails, *, ready: bool) -> dict:
    status, checks = eligibility(program, org, details, intent)
    score, breakdown = relevance(program, org, intent, checks[0]) if ready else (None, {})
    missing = {c["field"] for c in checks if c["unknown_reason"] == "profile_missing" and c["field"]}
    ordered_missing = [name for name in FIELD_ORDER if name in missing]
    matched = list(dict.fromkeys(c["label"] for c in checks if c["status"] == "met"))
    unmet = list(dict.fromkeys(c["label"] for c in checks if c["status"] == "not_met"))
    unknown = list(dict.fromkeys(c["label"] for c in checks if c["status"] == "unknown"))
    if status == "potentially_ineligible":
        explanation = "Your profile conflicts with one or more recorded requirements. Check the source before ruling it out."
    elif status == "needs_information":
        explanation = "This opportunity may fit, but some requirements need more profile information or a source review."
    else:
        explanation = "Your profile supports the recorded requirements. Confirm the full terms with the funder before applying."
    return {"opportunity_id": program.id, "opportunity": program, "relevance_score": score, "score_breakdown": breakdown,
            "eligibility_status": status, "criteria": checks, "matched_criteria": matched,
            "unmet_criteria": unmet, "unknown_criteria": unknown,
            "missing_profile_fields": ordered_missing, "industry_tags": industry_tags(program),
            "deadline": current_deadline(program), "explanation": explanation}


def readiness(org: m.Organization, intent: m.FundingIntent) -> list[str]:
    return [name for name, value in (("business_country", org.country), ("industry", org.industry),
                                     ("funding_purposes", intent.funding_purposes)) if not value]


def list_for_session(db: Session, session: m.DemoSession) -> dict:
    _, _, org, intent, details, *_ = onboarding.load(db, session)
    missing = readiness(org, intent)
    if missing:
        return {"ready": False, "missing_profile_fields": missing, "potentially_relevant_count": 0, "items": []}
    programs = db.scalars(select(m.FundingProgram).where(
        m.FundingProgram.review_status == m.ReviewStatus.approved,
        m.FundingProgram.verified_at.is_not(None), m.FundingProgram.published_at.is_not(None),
    )).all()
    items = [assess(program, org, intent, details, ready=True) for program in programs if not expired(program)]
    items.sort(key=lambda item: (-(item["relevance_score"] or 0), item["opportunity"].title))
    count = sum(item["relevance_score"] >= 20 and item["eligibility_status"] != "potentially_ineligible" for item in items)
    return {"ready": True, "missing_profile_fields": [], "potentially_relevant_count": count, "items": items}


def get_for_session(db: Session, session: m.DemoSession, opportunity_id: UUID) -> dict:
    _, _, org, intent, details, *_ = onboarding.load(db, session)
    program = db.get(m.FundingProgram, opportunity_id)
    if not program or program.review_status != m.ReviewStatus.approved or not program.verified_at or \
            not program.published_at or expired(program):
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return assess(program, org, intent, details, ready=not readiness(org, intent))
