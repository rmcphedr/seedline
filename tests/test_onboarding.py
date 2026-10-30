from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import models as m
from backend.models import now


def test_demo_mode_fails_closed(client, monkeypatch):
    assert client.post("/api/demo/create", json={}).status_code == 404
    monkeypatch.setenv("ENABLE_DEMO_MODE", "true")
    monkeypatch.setenv("APP_ENV", "production")
    assert client.post("/api/demo/create", json={}).status_code == 404
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    assert client.post("/api/demo/create", json={}).status_code == 404


def test_fresh_demo_persists_and_is_isolated(client, db_engine, monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "true")
    monkeypatch.setenv("APP_ENV", "development")
    first = client.post("/api/demo/create", json={"display_name": "Amina"})
    assert first.status_code == 201
    assert first.cookies.get("seedline_demo")
    first_id = first.json()["founder"]["id"]
    assert first.json()["completion"]["overall_completion"] < 10
    with Session(db_engine) as db:
        assert db.scalar(select(m.Founder).where(m.Founder.id == UUID(first_id))) is not None
        assert db.scalar(select(m.OrganizationMembership).where(m.OrganizationMembership.founder_id == UUID(first_id))) is not None
        assert db.scalar(select(m.DemoSession)).token_hash != first.cookies.get("seedline_demo")

    second = client.post("/api/demo/create", json={"display_name": "Jules"})
    assert second.status_code == 201
    assert second.json()["founder"]["id"] != first_id
    assert client.get("/api/demo/context").json()["founder"]["display_name"] == "Jules"
    client.cookies.set("seedline_demo", first.cookies.get("seedline_demo"))
    assert client.get("/api/demo/context").json()["founder"]["display_name"] == "Amina"
    assert client.patch("/api/demo/organization", json={"name": "Amina Co"}).json()["name"] == "Amina Co"
    client.cookies.set("seedline_demo", second.cookies.get("seedline_demo"))
    assert client.get("/api/demo/organization").json()["name"] != "Amina Co"


def test_autosave_completion_and_conditional_fields(client, monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "true")
    monkeypatch.setenv("APP_ENV", "development")
    client.post("/api/demo/create", json={})
    blank = client.get("/api/demo/completion").json()
    assert blank["overall_completion"] == 0
    assert client.patch("/api/demo/founder", json={"display_name": "Maya", "city": "Montreal", "province": "QC", "country": "CA", "role": "Founder"}).status_code == 200
    assert client.patch("/api/demo/organization", json={"name": "Maya Works", "industry": ["manufacturing"], "business_stage": "idea", "incorporation_status": "not_incorporated", "year_established": 2025}).status_code == 422
    organization = client.patch("/api/demo/organization", json={"name": "Maya Works", "industry": ["manufacturing"], "business_stage": "idea", "incorporation_status": "not_incorporated", "country": "CA", "province": "QC"})
    assert organization.status_code == 200
    assert client.patch("/api/demo/details", json={"annual_revenue_range": "pre_revenue", "previous_funding": "no", "previous_funding_details": "No grants"}).status_code == 422
    assert client.patch("/api/demo/details", json={"annual_revenue_range": "pre_revenue", "previous_funding": "no"}).status_code == 200
    before_skip = client.get("/api/demo/completion").json()
    skipped = client.patch("/api/demo/onboarding", json={"current_step": "founder_interests", "section_status": "skipped"})
    assert skipped.status_code == 200
    assert client.get("/api/demo/completion").json() == before_skip
    assert before_skip["overall_completion"] <= 100
    assert before_skip["overall_completion"] > 0
    assert "funding_purposes" in before_skip["important_missing_fields"]


def test_funding_validation_and_resume(client, monkeypatch, db_engine):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "true")
    monkeypatch.setenv("APP_ENV", "development")
    client.post("/api/demo/create", json={})
    assert client.patch("/api/demo/funding-intent", json={"amount_min": 90000, "amount_max": 10000}).status_code == 422
    assert client.patch("/api/demo/funding-intent", json={"amount_unsure": True, "amount_min": 10000}).status_code == 422
    assert client.patch("/api/demo/organization", json={"website": "not-a-url"}).status_code == 422
    assert client.patch("/api/demo/organization", json={"name": None}).status_code == 422
    assert client.patch("/api/demo/organization", json={"year_established": 2100}).status_code == 422
    saved = client.patch("/api/demo/funding-intent", json={"funding_purposes": ["equipment"], "amount_min": 10000, "amount_max": 90000, "funding_timeline": "within_6_months"})
    assert saved.status_code == 200
    assert saved.json()["funding_purposes"] == ["equipment"]
    assert client.patch("/api/demo/onboarding", json={"current_step": "business_details", "section_status": "completed"}).status_code == 200
    context = client.get("/api/demo/context").json()
    assert context["funding_intent"]["amount_max"] == 90000
    assert context["onboarding"]["current_step"] == "business_details"
    with Session(db_engine) as db:
        assert db.scalar(select(m.FundingIntent)).amount_max == 90000


def test_expired_session_and_example_profile(client, monkeypatch, db_engine):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "true")
    monkeypatch.setenv("APP_ENV", "development")
    example = client.post("/api/demo/example", json={})
    assert example.status_code == 201
    assert example.json()["organization"]["name"] == "EcoPack Solutions"
    assert example.json()["founder"]["demo_kind"] == "example"
    assert 0 < example.json()["completion"]["overall_completion"] < 100
    with Session(db_engine) as db:
        session = db.scalar(select(m.DemoSession))
        session.expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/demo/context").status_code == 401


def test_weighted_score_and_not_applicable_answers(client, monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "true")
    monkeypatch.setenv("APP_ENV", "development")
    client.post("/api/demo/create", json={})
    client.patch("/api/demo/founder", json={"display_name": "Maya", "role": "Founder"})
    client.patch("/api/demo/organization", json={"incorporation_status": "not_incorporated"})
    client.patch("/api/demo/details", json={"previous_funding": "no"})
    result = client.get("/api/demo/completion").json()
    assert result["overall_completion"] == 12  # 2/5*10 + 1/10*30 + 1/5*25 = 12
    assert result["sections"][3]["completion"] == 20
    assert "year_established" not in result["important_missing_fields"]
    assert client.patch("/api/demo/onboarding", json={"current_step": "business_details", "section_status": "skipped", "onboarding_status": "finished"}).status_code == 200
    assert client.get("/api/demo/completion").json()["overall_completion"] == 12
    assert client.get("/api/demo/onboarding").json()["onboarding_status"] == "finished"
    monkeypatch.setenv("ENABLE_DEMO_MODE", "false")
    assert client.get("/api/demo/context").status_code == 404


def test_start_fresh_creates_a_new_empty_profile(client, monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "true")
    monkeypatch.setenv("APP_ENV", "development")
    original = client.post("/api/demo/example", json={}).json()
    fresh = client.post("/api/demo/reset", json={})
    assert fresh.status_code == 201
    assert fresh.json()["founder"]["id"] != original["founder"]["id"]
    assert fresh.json()["founder"]["demo_kind"] == "fresh"
    assert fresh.json()["completion"]["overall_completion"] == 0


def test_years_in_operation_for_unincorporated_business(client, monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "true")
    monkeypatch.setenv("APP_ENV", "development")
    client.post("/api/demo/create", json={})
    client.patch("/api/demo/organization", json={"incorporation_status": "not_incorporated"})
    before = client.get("/api/demo/completion").json()["overall_completion"]
    assert client.patch("/api/demo/details", json={"years_in_operation": 201}).status_code == 422
    changed = client.patch("/api/demo/details", json={"years_in_operation": 3})
    assert changed.status_code == 200
    assert changed.json()["years_in_operation"] == 3
    assert client.get("/api/demo/completion").json()["overall_completion"] > before
    client.patch("/api/demo/organization", json={"incorporation_status": "incorporated", "year_established": 2022})
    assert client.get("/api/demo/details").json()["years_in_operation"] is None


def test_complete_profile_scores_100_then_edit_recalculates(client, monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "true")
    monkeypatch.setenv("APP_ENV", "development")
    client.post("/api/demo/create", json={})
    client.patch("/api/demo/founder", json={"display_name": "Maya", "role": "Founder", "city": "Montreal", "province": "QC", "country": "CA"})
    client.patch("/api/demo/organization", json={
        "name": "Maya Works", "description": "Recycled packaging", "industry": ["manufacturing"],
        "business_stage": "growth", "country": "CA", "province": "QC", "city": "Montreal",
        "legal_structure": "corporation", "incorporation_status": "not_incorporated", "business_model": "b2b",
    })
    client.patch("/api/demo/funding-intent", json={
        "funding_purposes": ["equipment"], "amount_unsure": True, "funding_timeline": "unsure",
        "preferred_funding_types": ["grant"], "project_description": "Buy equipment",
    })
    client.patch("/api/demo/details", json={
        "employee_count": 0, "years_in_operation": 2, "annual_revenue_range": "pre_revenue",
        "previous_funding": "no", "current_funding_status": "exploring",
    })
    client.patch("/api/demo/interests", json={
        "expertise": ["design"], "challenges": ["sales"], "support_areas": ["marketing"],
        "mentorship_interest": False, "collaboration_interest": False, "connections_opt_in": False,
    })
    complete = client.get("/api/demo/completion").json()
    assert complete["overall_completion"] == 100
    assert all(section["completion"] == 100 for section in complete["sections"])
    client.patch("/api/demo/organization", json={"description": None})
    assert client.get("/api/demo/completion").json()["overall_completion"] < 100
