def test_source_and_opportunity_lifecycle(client):
    source = client.post(
        "/sources",
        json={"name": "Women Funding Network", "base_url": "https://example.org", "kind": "website"},
    )
    assert source.status_code == 201
    source_id = source.json()["id"]
    assert client.get("/sources").json()[0]["id"] == source_id

    program = client.post(
        "/opportunities",
        json={
            "source_id": source_id,
            "title": "Growth Grant",
            "funding_type": "grant",
            "summary": "Growth support",
            "url": "https://example.org/grant",
            "rounds": [{"name": "2027 cycle", "status": "open", "deadline": "2027-05-01T00:00:00Z"}],
        },
    )
    assert program.status_code == 201
    program_id = program.json()["id"]
    assert program.json()["review_status"] == "pending"
    assert len(program.json()["rounds"]) == 1
    assert client.get("/opportunities?search=Growth&funding_type=grant").json()[0]["id"] == program_id
    assert client.get("/opportunities?review_status=approved").json() == []

    queue = client.get("/review-queue")
    assert queue.status_code == 200
    review_id = queue.json()[0]["id"]
    approved = client.post(f"/review-queue/{review_id}/approve", json={"note": "Verified"})
    assert approved.status_code == 200
    assert client.get(f"/opportunities/{program_id}").json()["review_status"] == "approved"
    assert client.get("/review-queue").json() == []


def test_jobs_and_organizations(client):
    source = client.post("/sources", json={"name": "Directory", "base_url": "https://example.com", "kind": "directory"}).json()
    job = client.post("/ingestion-jobs", json={"source_id": source["id"]})
    assert job.status_code == 201
    assert job.json()["status"] == "queued"
    assert client.get("/ingestion-jobs").json()[0]["id"] == job.json()["id"]
    organization = client.post("/organizations", json={"name": "Example Co", "kind": "business", "country": "CA"})
    assert organization.status_code == 201
    oid = organization.json()["id"]
    assert client.get(f"/organizations/{oid}").json()["name"] == "Example Co"
    assert client.patch(f"/organizations/{oid}", json={"name": "Renamed Co"}).json()["name"] == "Renamed Co"


def test_invalid_relationships_and_missing_records(client):
    missing = "00000000-0000-0000-0000-000000000001"
    assert client.post("/ingestion-jobs", json={"source_id": missing}).status_code == 404
    assert client.post("/opportunities", json={"source_id": missing, "title": "X", "funding_type": "grant"}).status_code == 404
    assert client.get(f"/opportunities/{missing}").status_code == 404
    assert client.get("/health").json()["status"] == "ok"


def test_source_management_and_rejection(client):
    source = client.post("/sources", json={"name": "Fund", "base_url": "https://fund.example", "kind": "website"}).json()
    source_id = source["id"]
    changed = client.patch(f"/sources/{source_id}", json={"active": False})
    assert changed.json()["active"] is False
    assert client.post("/sources", json={"name": "Fund", "base_url": "https://other.example", "kind": "website"}).status_code == 409
    program = client.post("/opportunities", json={"source_id": source_id, "title": "Pilot", "funding_type": "loan"}).json()
    review_id = client.get("/review-queue").json()[0]["id"]
    rejected = client.post(f"/review-queue/{review_id}/reject", json={"note": "No official page"})
    assert rejected.json()["status"] == "rejected"
    assert client.get(f"/opportunities/{program['id']}").json()["review_status"] == "rejected"
    assert client.post(f"/review-queue/{review_id}/approve", json={}).status_code == 409
    assert client.delete(f"/sources/{source_id}").status_code == 409


def test_invalid_amount_range(client):
    response = client.post("/opportunities", json={"title": "Invalid", "funding_type": "grant", "amount_min": 200, "amount_max": 100})
    assert response.status_code == 422
    assert client.get("/opportunities").json() == []


def test_eligibility_rule_requires_source_reference(client):
    response = client.post("/opportunities", json={
        "title": "Unverified requirements",
        "funding_type": "grant",
        "eligibility_rules": [{"criterion": "location", "requirement": "Canada"}],
    })
    assert response.status_code == 422
    assert client.get("/opportunities").json() == []
