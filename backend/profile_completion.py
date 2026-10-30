"""Authoritative, configurable coverage score for founder profiles.

The score measures supplied profile data, not funding eligibility or onboarding status.
"""

from backend import models as m

SECTION_WEIGHTS = {
    "founder_basics": 10,
    "business_overview": 30,
    "funding_goals": 25,
    "business_details": 25,
    "founder_interests": 10,
}


def answered(value: object) -> bool:
    return value is not None and value != "" and value != []


def calculate(
    founder: m.Founder,
    membership: m.OrganizationMembership,
    organization: m.Organization,
    intent: m.FundingIntent,
    details: m.BusinessDetails,
    interests: m.FounderInterests,
) -> dict:
    fields: dict[str, list[tuple[str, object]]] = {
        "founder_basics": [
            ("display_name", founder.display_name), ("role", membership.role),
            ("founder_city", founder.city), ("founder_province", founder.province),
            ("founder_country", founder.country),
        ],
        "business_overview": [
            ("business_name", organization.name), ("business_description", organization.description),
            ("industry", organization.industry), ("business_stage", organization.business_stage),
            ("business_country", organization.country), ("business_province", organization.region),
            ("business_city", organization.city), ("legal_structure", organization.legal_structure),
            ("incorporation_status", organization.incorporation_status), ("business_model", organization.business_model),
        ],
        "funding_goals": [
            ("funding_purposes", intent.funding_purposes),
            ("funding_amount", True if intent.amount_unsure is True or (intent.amount_min is not None and intent.amount_max is not None) else None),
            ("funding_timeline", intent.funding_timeline),
            ("preferred_funding_types", intent.preferred_funding_types),
            ("project_description", intent.project_description),
        ],
        "business_details": [
            ("employee_count", details.employee_count),
            ("annual_revenue_range", details.annual_revenue_range),
            ("previous_funding", details.previous_funding),
            ("current_funding_status", details.current_funding_status),
        ],
        "founder_interests": [
            ("expertise", interests.expertise), ("challenges", interests.challenges),
            ("support_areas", interests.support_areas),
            ("mentorship_interest", interests.mentorship_interest),
            ("collaboration_interest", interests.collaboration_interest),
            ("connections_opt_in", interests.connections_opt_in),
        ],
    }
    # A negative answer counts, while genuinely irrelevant follow-up questions do not enter the denominator.
    if organization.incorporation_status == "incorporated":
        fields["business_overview"].append(("year_established", organization.year_established))
    if organization.incorporation_status in {"not_incorporated", "in_progress", "unsure"}:
        fields["business_details"].append(("years_in_operation", details.years_in_operation))
    if details.previous_funding == "yes":
        fields["business_details"].append(("previous_funding_details", details.previous_funding_details))

    sections = []
    overall = 0.0
    missing: set[str] = set()
    for section_id, weight in SECTION_WEIGHTS.items():
        section_fields = fields[section_id]
        supplied = sum(1 for _, value in section_fields if answered(value))
        completion = round(100 * supplied / len(section_fields))
        sections.append({"id": section_id, "completion": completion, "weight": weight})
        overall += weight * supplied / len(section_fields)
        missing.update(name for name, value in section_fields if not answered(value))
    priority = [
        "business_country", "business_province", "business_stage", "legal_structure", "industry",
        "incorporation_status", "funding_purposes", "funding_amount", "funding_timeline",
        "annual_revenue_range", "employee_count", "business_description", "business_name",
    ]
    return {
        "overall_completion": min(100, round(overall)),
        "sections": sections,
        "important_missing_fields": [name for name in priority if name in missing],
    }
