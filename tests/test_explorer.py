from fastapi.testclient import TestClient

from apps.api.main import app


def test_admin_requires_key_and_public_routes_do_not(client):
    with TestClient(app) as anonymous:
        assert anonymous.get("/sources").status_code == 401
        assert anonymous.post("/opportunities", json={"title": "No access", "funding_type": "grant"}).status_code == 401
        assert anonymous.get("/public/opportunities").status_code == 200


def test_approval_and_publication_are_separate(client):
    created = client.post("/opportunities", json={
        "title": "Community Growth Fund", "funding_type": "grant", "geography": "Quebec",
        "organization_types": ["nonprofit"], "url": "https://example.org/growth",
        "rounds": [{"name": "2027 round", "status": "open", "application_url": "https://example.org/apply"}],
        "eligibility_rules": [{"criterion": "organization", "requirement": "Registered nonprofit", "source_url": "https://example.org/growth"}],
    })
    assert created.status_code == 201
    program_id = created.json()["id"]
    assert created.json()["application_status"] == "open"
    assert created.json()["verification_status"] == "pending"
    assert created.json()["publication_status"] == "unpublished"
    assert [item["id"] for item in client.get("/opportunities?geography=Quebec&organization_type=nonprofit&application_status=open").json()] == [program_id]
    assert client.get("/opportunities?organization_type=business").json() == []
    assert client.get("/public/opportunities").json() == []
    assert client.post(f"/opportunities/{program_id}/publish").status_code == 409

    review_id = client.get("/review-queue").json()[0]["id"]
    approved = client.post(f"/review-queue/{review_id}/approve", json={"note": "Checked source"})
    assert approved.status_code == 200
    assert approved.json()["program"]["verified_at"] is not None
    assert client.get("/public/opportunities").json() == []

    published = client.post(f"/opportunities/{program_id}/publish")
    assert published.status_code == 200
    assert published.json()["publication_status"] == "published"
    public = client.get("/public/opportunities?search=Growth&funding_type=grant&geography=Quebec&organization_type=nonprofit&application_status=open")
    assert [item["id"] for item in public.json()] == [program_id]
    assert client.get("/public/opportunities?organization_type=business").json() == []
    assert client.get("/public/opportunities?application_status=closed").json() == []
    assert client.get(f"/public/opportunities/{program_id}").status_code == 200

    edited = client.patch(f"/opportunities/{program_id}", json={
        "title": "Community Growth Fund, revised",
        "rounds": [{"name": "2028 round", "status": "unknown"}],
        "eligibility_rules": [],
    })
    assert edited.status_code == 200
    assert edited.json()["verification_status"] == "pending"
    assert edited.json()["publication_status"] == "unpublished"
    assert edited.json()["verified_at"] is None
    assert edited.json()["application_status"] == "unknown"
    assert edited.json()["eligibility_rules"] == []
    assert client.get(f"/public/opportunities/{program_id}").status_code == 404
    assert len(client.get("/review-queue").json()) == 1


def test_source_category_and_version_history(client):
    source = client.post("/sources", json={
        "name": "Local grantmaker", "base_url": "https://example.org/funding",
        "kind": "directory", "resource_type": "grantmaker_programs",
    })
    assert source.status_code == 201
    assert source.json()["resource_type"] == "grantmaker_programs"
    changed = client.patch(f"/sources/{source.json()['id']}", json={"resource_type": "funding_directory"})
    assert changed.json()["resource_type"] == "funding_directory"

    program = client.post("/opportunities", json={"title": "Pilot", "funding_type": "loan"}).json()
    versions = client.get(f"/opportunities/{program['id']}/versions")
    assert versions.status_code == 200
    assert versions.json()[0]["change_note"] == "Created"


def test_publish_requires_verified_record_even_after_rejection(client):
    program = client.post("/opportunities", json={"title": "Unverified", "funding_type": "grant"}).json()
    review_id = client.get("/review-queue").json()[0]["id"]
    client.post(f"/review-queue/{review_id}/reject", json={})
    assert client.post(f"/opportunities/{program['id']}/publish").status_code == 409


def test_unpublish_keeps_verification_and_invalid_edit_is_rejected(client):
    program = client.post("/opportunities", json={"title": "Valid", "funding_type": "grant"}).json()
    program_id = program["id"]
    review_id = client.get("/review-queue").json()[0]["id"]
    client.post(f"/review-queue/{review_id}/approve", json={"note": "Checked"})
    client.post(f"/opportunities/{program_id}/publish")
    assert client.patch(f"/opportunities/{program_id}", json={"title": None}).status_code == 422
    assert client.patch(f"/opportunities/{program_id}", json={"rounds": None}).status_code == 422
    assert client.get(f"/public/opportunities/{program_id}").status_code == 200
    unpublished = client.post(f"/opportunities/{program_id}/unpublish")
    assert unpublished.status_code == 200
    assert unpublished.json()["verification_status"] == "approved"
    assert unpublished.json()["publication_status"] == "unpublished"
    assert client.get(f"/public/opportunities/{program_id}").status_code == 404
