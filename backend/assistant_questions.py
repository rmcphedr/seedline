"""Choose the next useful field independently of question wording."""

from backend import models as m
from backend import onboarding, recommendations

TEMPLATES = {
    "description": "What does your business make or do, and who is it for?",
    "country": "Which country is your business based in?",
    "province": "Which province or state is your business based in?",
    "city": "Which city is your business based in?",
    "industry": "Which industry best describes your business?",
    "funding_purposes": "What would you use funding for first?",
    "business_stage": "Are you developing a prototype, making sales, or growing an established business?",
    "incorporation_status": "Is your business currently incorporated?",
    "legal_structure": "What legal structure does your business have?",
    "year_established": "What year was your business established?",
    "years_in_operation": "How many years has your business been operating?",
    "employee_count": "How many employees does your business have?",
    "annual_revenue_range": "Which annual revenue range best describes your business?",
    "project_description": "What project are you hoping to fund?",
    "preferred_funding_types": "Are you mainly looking for grants, loans, or investment?",
    "amount_max": "About how much funding do you need?",
}

BASELINE = ("country", "industry", "funding_purposes")
CONTEXT = ("description", "business_stage", "project_description", "preferred_funding_types", "amount_max")
ELIGIBILITY_PRIORITY = ("incorporation_status", "legal_structure", "year_established", "years_in_operation",
                        "employee_count", "annual_revenue_range", "province", "city", "country", "industry",
                        "business_stage", "funding_purposes")


def profile_values(db, session: m.DemoSession) -> dict:
    _, _, org, intent, details, *_ = onboarding.load(db, session)
    return {
        "name": org.name, "country": org.country, "province": org.region, "city": org.city, "description": org.description,
        "industry": org.industry, "business_stage": org.business_stage, "legal_structure": org.legal_structure,
        "incorporation_status": org.incorporation_status, "year_established": org.year_established,
        "years_in_operation": details.years_in_operation, "employee_count": details.employee_count,
        "annual_revenue_range": details.annual_revenue_range, "funding_purposes": intent.funding_purposes,
        "project_description": intent.project_description, "preferred_funding_types": intent.preferred_funding_types,
        "amount_max": intent.amount_max,
    }


def missing(value: object) -> bool:
    return value is None or value == "" or value == [] or value == "other" or value == "unsure"


def applicable(field: str, profile: dict) -> bool:
    if field == "year_established" and profile["incorporation_status"] == "not_incorporated":
        return False
    return not (field == "years_in_operation" and profile["incorporation_status"] == "incorporated")


def _requirement(item: dict, field: str) -> str | None:
    return next((check["requirement"] for check in item["criteria"] if check["field"] == field and
                 check["unknown_reason"] == "profile_missing"), None)


def select_field(db, session: m.DemoSession, opportunity_id, asked: set[str]) -> tuple[str | None, str | None, str | None]:
    profile = profile_values(db, session)
    if opportunity_id:
        result = recommendations.get_for_session(db, session, opportunity_id)
        fields = result["missing_profile_fields"]
        for field in ELIGIBILITY_PRIORITY:
            if field in fields and field not in asked and applicable(field, profile):
                return field, result["opportunity"].title, _requirement(result, field)
    for field in BASELINE:
        if missing(profile[field]) and field not in asked and applicable(field, profile):
            return field, None, None
    if not opportunity_id:
        listing = recommendations.list_for_session(db, session)
        relevant = [item for item in listing["items"][:5] if item["relevance_score"] >= 20 and
                    item["eligibility_status"] != "potentially_ineligible"]
        for field in ELIGIBILITY_PRIORITY:
            if field not in asked and applicable(field, profile):
                item = next((candidate for candidate in relevant if field in candidate["missing_profile_fields"]), None)
                if item:
                    return field, item["opportunity"].title, _requirement(item, field)
    for field in CONTEXT:
        if missing(profile[field]) and field not in asked and applicable(field, profile):
            return field, None, None
    return None, None, None


def question(field: str, opportunity_title: str | None = None, requirement: str | None = None) -> str:
    text = TEMPLATES.get(field, "Could you tell me more about your business?")
    if opportunity_title and requirement:
        return f"{opportunity_title} lists “{requirement[:180]}”. {text}"
    return f"To assess {opportunity_title}, {text[0].lower()}{text[1:]}" if opportunity_title else text
