"""Profile-to-opportunity decisions use only published facts and the active demo session."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from backend import models as m


def program(db, title, *, geography="Quebec", funding_type=m.FundingType.grant,
            sectors=None, organization_types=None, rules=(), deadline=None, round_status=None):
    item = m.FundingProgram(
        title=title, funding_type=funding_type, geography=geography,
        organization_types=organization_types or [],
        details={"sectors": sectors} if sectors else None,
        review_status=m.ReviewStatus.approved, verified_at=m.now(), published_at=m.now(),
    )
    db.add(item)
    db.flush()
    for criterion, requirement in rules:
        db.add(m.EligibilityRule(program_id=item.id, criterion=criterion, requirement=requirement,
                                 source_url="https://funding.example/rules"))
    if round_status:
        db.add(m.FundingRound(program_id=item.id, name="Current call", status=round_status,
                              deadline=deadline))
    db.commit()
    return str(item.id)


def example(client, monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "true")
    monkeypatch.setenv("APP_ENV", "development")
    assert client.post("/api/demo/example", json={}).status_code == 201


def test_eligibility_and_relevance_use_real_fields(client, monkeypatch, db_engine):
    example(client, monkeypatch)
    with Session(db_engine) as db:
        matching = program(db, "Quebec Manufacturing Equipment Grant", sectors=["manufacturing"],
                           rules=[("Applicants", "Canadian incorporated businesses operating for at least three years"),
                                  ("Funding purpose", "Equipment purchases")])
        nonprofit = program(db, "Montreal Nonprofit Support", geography="Montreal",
                            organization_types=["nonprofit"])
    response = client.get("/api/demo/recommendations")
    assert response.status_code == 200, response.text
    results = {item["opportunity"]["id"]: item for item in response.json()["items"]}
    match = results[matching]
    assert match["opportunity_id"] == matching
    assert response.json()["items"][0]["opportunity"]["id"] == matching
    assert match["eligibility_status"] == "needs_information"
    assert match["relevance_score"] > results[nonprofit]["relevance_score"]
    assert any(c["status"] == "met" and c["field"] == "funding_purposes" for c in match["criteria"])
    assert any(c["status"] == "unknown" and c["field"] == "year_established" for c in match["criteria"])
    assert "year_established" in match["missing_profile_fields"]
    assert results[nonprofit]["eligibility_status"] == "potentially_ineligible"
    assert any(c["status"] == "not_met" and c["field"] == "legal_structure" for c in results[nonprofit]["criteria"])
    assert all(c["source_url"] == "https://funding.example/rules" for c in match["criteria"] if c["source_rule_id"])


def test_profile_update_reassesses_and_session_isolates(client, monkeypatch, db_engine):
    example(client, monkeypatch)
    with Session(db_engine) as db:
        item_id = program(db, "Established Manufacturers Grant", sectors=["manufacturing"],
                          rules=[("Applicants", "Canadian incorporated businesses operating for at least three years")])
    before = client.get(f"/api/demo/recommendations/{item_id}").json()
    assert before["eligibility_status"] == "needs_information"
    assert "year_established" in before["missing_profile_fields"]
    assert client.patch("/api/demo/organization", json={"year_established": 2020}).status_code == 200
    after = client.get(f"/api/demo/recommendations/{item_id}").json()
    assert after["eligibility_status"] == "likely_eligible"
    assert "year_established" not in after["missing_profile_fields"]
    assert client.patch("/api/demo/organization", json={"country": "US"}).status_code == 200
    assert client.get(f"/api/demo/recommendations/{item_id}").json()["eligibility_status"] == "potentially_ineligible"
    assert client.post("/api/demo/create", json={}).status_code == 201
    assert client.get("/api/demo/recommendations").json()["ready"] is False
    assert client.get(f"/api/demo/recommendations/{item_id}").status_code == 200
    assert client.get(f"/api/demo/recommendations/{item_id}").json()["relevance_score"] is None


def test_expired_unpublished_and_sparse_opportunities(client, monkeypatch, db_engine):
    example(client, monkeypatch)
    with Session(db_engine) as db:
        expired = program(db, "Expired Grant", deadline=m.now() - timedelta(days=2),
                          round_status=m.RoundStatus.open)
        sparse = program(db, "Sparse Loan", geography=None, funding_type=m.FundingType.loan)
        hidden = m.FundingProgram(title="Pending Grant", funding_type=m.FundingType.grant,
                                  review_status=m.ReviewStatus.pending)
        db.add(hidden)
        db.commit()
        hidden_id = str(hidden.id)
    response = client.get("/api/demo/recommendations").json()
    ids = [item["opportunity"]["id"] for item in response["items"]]
    assert expired not in ids
    assert sparse in ids
    assert hidden_id not in ids
    assessment = next(item for item in response["items"] if item["opportunity"]["id"] == sparse)
    assert any(c["status"] == "unknown" and c["unknown_reason"] == "opportunity_data_missing" for c in assessment["criteria"])
    assert assessment["missing_profile_fields"] == []
    assert client.get(f"/api/demo/recommendations/{expired}").status_code == 404


def test_current_deadline_ignores_expired_rounds(client, monkeypatch, db_engine):
    example(client, monkeypatch)
    future = m.now() + timedelta(days=20)
    with Session(db_engine) as db:
        item_id = program(db, "Recurring Business Grant", deadline=m.now() - timedelta(days=20),
                          round_status=m.RoundStatus.open)
        db.add(m.FundingRound(program_id=UUID(item_id), name="Next call", status=m.RoundStatus.open,
                              deadline=future))
        db.commit()
    result = client.get(f"/api/demo/recommendations/{item_id}").json()
    assert result["deadline"] == future.isoformat()


def test_missing_profile_and_demo_guard(client, monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "false")
    assert client.get("/api/demo/recommendations").status_code == 404
    monkeypatch.setenv("ENABLE_DEMO_MODE", "true")
    monkeypatch.setenv("APP_ENV", "development")
    assert client.get("/api/demo/recommendations").status_code == 401
    assert client.post("/api/demo/create", json={}).status_code == 201
    response = client.get("/api/demo/recommendations").json()
    assert response["ready"] is False
    assert {"business_country", "industry", "funding_purposes"} <= set(response["missing_profile_fields"])
    assert response["items"] == []


def test_explicit_stage_industry_size_and_revenue_rules(client, monkeypatch, db_engine):
    example(client, monkeypatch)
    with Session(db_engine) as db:
        item_id = program(db, "Manufacturing Growth Program", rules=[
            ("Industry", "Manufacturing"),
            ("Business stage", "Early revenue"),
            ("Organization size", "Fewer than 10 employees"),
            ("Annual revenue", "Annual revenue under $1,000,000"),
        ])
    result = client.get(f"/api/demo/recommendations/{item_id}").json()
    fields = {c["field"]: c["status"] for c in result["criteria"] if c["field"]}
    assert fields["industry"] == "met"
    assert fields["business_stage"] == "met"
    assert fields["employee_count"] == "met"
    assert fields["annual_revenue_range"] == "met"
    assert client.patch("/api/demo/details", json={"employee_count": 20}).status_code == 200
    changed = client.get(f"/api/demo/recommendations/{item_id}").json()
    assert changed["eligibility_status"] == "potentially_ineligible"
    assert any(c["field"] == "employee_count" and c["status"] == "not_met" for c in changed["criteria"])


def test_other_legal_structure_is_not_assumed_to_be_a_business(client, monkeypatch, db_engine):
    example(client, monkeypatch)
    with Session(db_engine) as db:
        item_id = program(db, "Business Applicants Fund", organization_types=["business"])
    assert client.patch("/api/demo/organization", json={"legal_structure": "other"}).status_code == 200
    result = client.get(f"/api/demo/recommendations/{item_id}").json()
    applicant = next(c for c in result["criteria"] if c["label"] == "Applicant type")
    assert applicant["status"] == "unknown"
    assert "legal_structure" in result["missing_profile_fields"]
    with Session(db_engine) as db:
        nonprofit_id = program(db, "Nonprofit Applicants Fund", rules=[("Applicants", "Nonprofit organizations")])
    nonprofit = client.get(f"/api/demo/recommendations/{nonprofit_id}").json()
    assert any(c["label"] == "Nonprofit structure" and c["status"] == "unknown" for c in nonprofit["criteria"])


def test_unsupported_sourced_rule_does_not_become_a_false_match(client, monkeypatch, db_engine):
    example(client, monkeypatch)
    with Session(db_engine) as db:
        item_id = program(db, "Community Fund", rules=[
            ("Applicants", "Canadian nonprofits with board approval or signing authority"),
        ])
    result = client.get(f"/api/demo/recommendations/{item_id}").json()
    assert result["eligibility_status"] == "potentially_ineligible"
    assert any(c["unknown_reason"] == "unsupported_rule" for c in result["criteria"])
    assert any(c["field"] == "legal_structure" and c["status"] == "not_met" for c in result["criteria"])


def test_sustainable_manufacturing_needs_manufacturing_signal(client, monkeypatch, db_engine):
    example(client, monkeypatch)
    with Session(db_engine) as db:
        item_id = program(db, "Nonprofit Startup Fund", sectors=["social enterprise"], rules=[
            ("Applicants", "Non-profit organization founders, including new or existing non-profits, with signing authority or board approval"),
        ])
    result = client.get(f"/api/demo/recommendations/{item_id}").json()
    assert "sustainable_manufacturing" not in result["industry_tags"]
    assert "creative" not in result["industry_tags"]
    assert result["eligibility_status"] == "potentially_ineligible"


def test_less_than_five_years_rule_reassesses_from_year_established(client, monkeypatch, db_engine):
    example(client, monkeypatch)
    with Session(db_engine) as db:
        item_id = program(db, "Young Business Fund", rules=[
            ("Business age", "Business must have less than 5 years of existence"),
        ])
    before = client.get(f"/api/demo/recommendations/{item_id}").json()
    assert "year_established" in before["missing_profile_fields"]
    assert client.patch("/api/demo/organization", json={"year_established": m.now().year - 2}).status_code == 200
    assert client.get(f"/api/demo/recommendations/{item_id}").json()["eligibility_status"] == "likely_eligible"
    assert client.patch("/api/demo/organization", json={"year_established": m.now().year - 8}).status_code == 200
    assert client.get(f"/api/demo/recommendations/{item_id}").json()["eligibility_status"] == "potentially_ineligible"
