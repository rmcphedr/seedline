"""Conversation, confirmation, and recommendation flow through demo HTTP routes."""

from datetime import timedelta
from uuid import UUID, uuid4

import httpx
from sqlalchemy.orm import Session

from backend import assistant_provider, assistant_service
from backend import models as m

SCENARIO = ("I'm developing a small company in Montreal that creates sustainable packaging for food businesses. "
            "We're already generating revenue and want funding to purchase new manufacturing equipment.")


def setup(client, monkeypatch, *, example=False):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ENABLE_DEMO_MODE", "true")
    monkeypatch.setenv("SEEDLINE_ASSISTANT_MODE", "mock")
    assert client.post("/api/demo/example" if example else "/api/demo/create", json={}).status_code == 201


def start(client, opportunity_id=None):
    response = client.post("/api/demo/assistant/conversations", json={"opportunity_id": opportunity_id})
    assert response.status_code == 201, response.text
    return response.json()


def send(client, conversation_id, content, request_id=None):
    response = client.post(f"/api/demo/assistant/conversations/{conversation_id}/messages",
                           json={"content": content, "request_id": str(request_id or uuid4())})
    assert response.status_code == 200, response.text
    return response.json()


def decide(client, conversation_id, decisions):
    response = client.post(f"/api/demo/assistant/conversations/{conversation_id}/confirm", json={"decisions": decisions})
    assert response.status_code == 200, response.text
    return response.json()


def opportunity(db):
    item = m.FundingProgram(title="Montreal Equipment Fund", funding_type=m.FundingType.grant,
                            geography="Quebec", details={"sectors": ["sustainable manufacturing"],
                            "description": "Equipment funding for sustainable manufacturers"},
                            review_status=m.ReviewStatus.approved, verified_at=m.now(), published_at=m.now())
    db.add(item)
    db.flush()
    db.add(m.EligibilityRule(program_id=item.id, criterion="Applicants", requirement="Incorporated businesses",
                             source_url="https://fund.example/rules"))
    db.add(m.FundingRound(program_id=item.id, name="Current", status=m.RoundStatus.open,
                          deadline=m.now() + timedelta(days=50)))
    db.commit()
    return str(item.id)


def test_mock_scenario_confirms_profile_and_reassesses_opportunity(client, monkeypatch, db_engine):
    setup(client, monkeypatch)
    with Session(db_engine) as db:
        item_id = opportunity(db)
    first = start(client)
    assert first["mode"] == "mock"
    assert "Tell me" in first["messages"][0]["content"]
    initial = client.get("/api/demo/context").json()["completion"]["overall_completion"]
    result = send(client, first["id"], SCENARIO)
    fields = {s["field"]: s for s in result["suggestions"]}
    assert {"country", "province", "city", "industry", "business_stage", "funding_purposes"} <= fields.keys()
    assert fields["industry"]["value"] == ["sustainable_manufacturing"]
    assert "ownership_eligibility" not in fields
    assert client.get("/api/demo/context").json()["organization"]["country"] == ""
    assert client.get("/api/demo/recommendations").json()["ready"] is False
    result = decide(client, first["id"], [{"id": suggestion["id"], "action": "accept"}
                                           for suggestion in result["suggestions"]])
    context = client.get("/api/demo/context").json()
    assert context["organization"]["country"] == "CA"
    assert context["funding_intent"]["funding_purposes"] == ["equipment"]
    assert context["completion"]["overall_completion"] > initial
    assert result["provenance"]["industry"] == "ai_confirmed"
    listed = client.get("/api/demo/recommendations").json()
    assert listed["items"][0]["opportunity_id"] == item_id
    before = client.get(f"/api/demo/recommendations/{item_id}").json()
    assert "incorporation_status" in before["missing_profile_fields"]
    targeted = start(client, item_id)
    assert targeted["messages"][0]["target_field"] == "incorporation_status"
    assert "Montreal Equipment Fund" in targeted["messages"][0]["content"]
    assert "Incorporated businesses" in targeted["messages"][0]["content"]
    response = send(client, targeted["id"], "Yes, we are incorporated")
    assert any(s["field"] == "incorporation_status" for s in response["suggestions"])
    assert client.get(f"/api/demo/recommendations/{item_id}").json()["eligibility_status"] == before["eligibility_status"]
    decide(client, targeted["id"], [{"id": response["suggestions"][0]["id"], "action": "accept"}])
    after = client.get(f"/api/demo/recommendations/{item_id}").json()
    assert "incorporation_status" not in after["missing_profile_fields"]
    assert after["eligibility_status"] == "likely_eligible"


def test_resume_isolation_duplicate_message_and_confirm(client, monkeypatch, db_engine):
    setup(client, monkeypatch)
    first = start(client)
    request_id = uuid4()
    response = send(client, first["id"], "We have three employees", request_id)
    duplicate = send(client, first["id"], "We have three employees", request_id)
    assert len(duplicate["messages"]) == len(response["messages"])
    assert start(client)["id"] == first["id"]
    assert client.get(f"/api/demo/assistant/conversations/{first['id']}").json()["suggestions"]
    suggestion = response["suggestions"][0]
    decide(client, first["id"], [{"id": suggestion["id"], "action": "accept"}])
    repeat = decide(client, first["id"], [{"id": suggestion["id"], "action": "accept"}])
    assert repeat["suggestions"][0]["status"] == "accepted"
    assert client.post("/api/demo/reset", json={}).status_code == 201
    assert client.get(f"/api/demo/assistant/conversations/{first['id']}").status_code == 404
    assert client.post(f"/api/demo/assistant/conversations/{first['id']}/messages",
                       json={"request_id": str(uuid4()), "content": "hello"}).status_code == 404


def test_reject_edit_stale_and_manual_provenance(client, monkeypatch):
    setup(client, monkeypatch)
    conversation = start(client)
    result = send(client, conversation["id"], "We have three employees and need $150,000 for equipment")
    suggestions = {item["field"]: item for item in result["suggestions"]}
    assert client.post(f"/api/demo/assistant/conversations/{conversation['id']}/messages",
                       json={"request_id": str(uuid4()), "content": "another answer"}).status_code == 409
    decide(client, conversation["id"], [{"id": suggestions["amount_max"]["id"], "action": "reject"}])
    result = decide(client, conversation["id"], [{"id": suggestions["employee_count"]["id"],
                                                   "action": "accept", "value": 4}])
    assert result["provenance"]["employee_count"] == "ai_confirmed"
    assert client.get("/api/demo/context").json()["details"]["employee_count"] == 4
    assert client.patch("/api/demo/details", json={"employee_count": 5}).status_code == 200
    assert client.get(f"/api/demo/assistant/conversations/{conversation['id']}").json()["provenance"]["employee_count"] == "manual"
    assert client.post(f"/api/demo/assistant/conversations/{conversation['id']}/confirm",
                       json={"decisions": [{"id": suggestions["funding_purposes"]["id"], "action": "accept",
                                             "value": ["unsupported"]}]}).status_code == 422
    assert client.patch("/api/demo/funding-intent", json={"funding_purposes": ["hiring"]}).status_code == 200
    assert client.post(f"/api/demo/assistant/conversations/{conversation['id']}/confirm",
                       json={"decisions": [{"id": suggestions["funding_purposes"]["id"], "action": "accept"}]}).status_code == 409


def test_question_skip_and_provider_failures(client, monkeypatch):
    setup(client, monkeypatch)
    conversation = start(client)
    skipped = client.post(f"/api/demo/assistant/conversations/{conversation['id']}/skip", json={})
    assert skipped.status_code == 200
    assert skipped.json()["messages"][-1]["target_field"] != "description"
    monkeypatch.setenv("SEEDLINE_ASSISTANT_MODE", "live")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert client.post("/api/demo/assistant/conversations", json={"restart": True}).status_code == 503
    # A live-mode provider failure cannot interfere with the existing manual profile API.
    assert client.patch("/api/demo/organization", json={"country": "CA"}).status_code == 200


def test_invalid_extraction_is_ignored_and_timeout_preserves_conversation(client, monkeypatch):
    setup(client, monkeypatch)
    conversation = start(client)
    def invalid(_provider, message, target, context):
        return [
            {"field": "ownership_eligibility", "value": ["woman_owned"], "source_text": message, "confidence": "high"},
            {"field": "business_stage", "value": "prototype_mvp", "source_text": message, "confidence": "high"},
            {"field": "employee_count", "value": 20, "source_text": "not in the answer", "confidence": "high"},
        ]
    monkeypatch.setattr(assistant_provider.MockProvider, "extract", invalid)
    result = send(client, conversation["id"], "We build packaging")
    assert result["suggestions"] == []
    assert client.get("/api/demo/context").json()["organization"]["business_stage"] is None

    def timeout(_provider, message, target, context):
        raise httpx.TimeoutException("provider timeout")
    monkeypatch.setattr(assistant_provider.MockProvider, "extract", timeout)
    before = len(result["messages"])
    failed = client.post(f"/api/demo/assistant/conversations/{conversation['id']}/messages",
                         json={"request_id": str(uuid4()), "content": "Another answer"})
    assert failed.status_code == 503
    assert len(client.get(f"/api/demo/assistant/conversations/{conversation['id']}").json()["messages"]) == before
    assert client.patch("/api/demo/organization", json={"country": "CA"}).status_code == 200


def test_mock_does_not_treat_revenue_as_requested_funding(client, monkeypatch):
    setup(client, monkeypatch)
    conversation = start(client)
    response = send(client, conversation["id"], "We make about $80,000 in annual revenue.")
    assert all(item["field"] != "amount_max" for item in response["suggestions"])
    assert any(item["field"] == "annual_revenue_range" and item["value"] == "under_100k"
               for item in response["suggestions"])


def test_question_selection_respects_incorporation_and_resume(client, monkeypatch, db_engine):
    setup(client, monkeypatch, example=True)
    assert client.patch("/api/demo/organization", json={"incorporation_status": "not_incorporated"}).status_code == 200
    with Session(db_engine) as db:
        item_id = opportunity(db)
        db.add(m.EligibilityRule(program_id=UUID(item_id), criterion="Business age",
                                 requirement="At least three years of operation", source_url="https://fund.example/age"))
        db.commit()
    conversation = start(client, item_id)
    assert conversation["messages"][0]["target_field"] != "year_established"
    assert start(client, item_id)["id"] == conversation["id"]


def test_correction_requires_confirmation(client, monkeypatch):
    setup(client, monkeypatch)
    conversation = start(client)
    first = send(client, conversation["id"], "We make sustainable packaging in Montreal")
    decide(client, conversation["id"], [{"id": item["id"], "action": "accept"} for item in first["suggestions"]])
    assert client.get("/api/demo/context").json()["organization"]["city"] == "Montreal"
    correction = send(client, conversation["id"], "Actually, we're in Toronto, not Montreal")
    city = next(item for item in correction["suggestions"] if item["field"] == "city" and item["status"] == "pending")
    assert city["base_value"] == "Montreal" and city["value"] == "Toronto"
    assert client.get("/api/demo/context").json()["organization"]["city"] == "Montreal"
    decide(client, conversation["id"], [{"id": city["id"], "action": "accept"}])
    assert client.get("/api/demo/context").json()["organization"]["city"] == "Toronto"


def test_openrouter_usage_recorded_before_invalid_output(client, monkeypatch, db_engine):
    setup(client, monkeypatch)
    conversation = start(client)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("SEEDLINE_ASSISTANT_MODEL", "test/model")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "response-1", "usage": {"prompt_tokens": 12, "completion_tokens": 4,
                                                     "total_tokens": 16},
                    "choices": [{"message": {"content": "not json"}}]}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(assistant_provider.httpx, "Client", FakeClient)
    with Session(db_engine) as db:
        session = db.query(m.DemoSession).order_by(m.DemoSession.created_at.desc()).first()
        engine = assistant_service._engine(db, session, UUID(conversation["id"]), "live")
        try:
            engine.extract("We build packaging", None, {})
            assert False, "invalid JSON should fail extraction"
        except ValueError:
            pass
    with Session(db_engine) as db:
        usage = db.query(m.AssistantUsage).one()
        assert usage.provider == "openrouter"
        assert usage.model == "test/model"
        assert usage.total_tokens == 16
        assert usage.operation == "profile_extraction"


def test_live_mode_uses_structured_output_and_confirm_path(client, monkeypatch, db_engine):
    setup(client, monkeypatch)
    monkeypatch.setenv("SEEDLINE_ASSISTANT_MODE", "live")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("SEEDLINE_ASSISTANT_MODEL", raising=False)
    monkeypatch.setenv("BRIDGE_ENRICHMENT_MODEL", "nvidia/nemotron-3.5-super-vl:free")

    class FakeResponse:
        def __init__(self, kind):
            self.kind = kind

        def raise_for_status(self):
            return None

        def json(self):
            content = ('{"extracted_fields":[{"field":"country","value_json":"\\\"CA\\\"",'
                       '"confidence":"high","source_text":"Canada"}]}') if self.kind == "profile_extraction" else \
                      '{"question":"What industry best describes your business?"}'
            return {"id": str(uuid4()), "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                                                   "total_tokens": 15},
                    "choices": [{"message": {"content": content}}]}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, headers, json):
            assert json["model"] == "nvidia/nemotron-3.5-super-vl:free"
            assert json["reasoning"] == {"enabled": False}
            return FakeResponse(json["response_format"]["json_schema"]["name"])

    monkeypatch.setattr(assistant_provider.httpx, "Client", FakeClient)
    conversation = start(client)
    assert conversation["mode"] == "live"
    result = send(client, conversation["id"], "Our business is in Canada")
    suggestion = next(item for item in result["suggestions"] if item["field"] == "country")
    assert client.get("/api/demo/context").json()["organization"]["country"] == ""
    result = decide(client, conversation["id"], [{"id": suggestion["id"], "action": "accept"}])
    assert client.get("/api/demo/context").json()["organization"]["country"] == "CA"
    assert result["messages"][-1]["content"] == "What industry best describes your business?"
    with Session(db_engine) as db:
        usage = db.query(m.AssistantUsage).all()
        assert len(usage) == 2
        assert {item.operation for item in usage} == {"profile_extraction", "profile_question"}


def test_live_question_wording_stays_on_selected_field(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("SEEDLINE_ASSISTANT_MODEL", "test/model")
    provider = assistant_provider.OpenRouterProvider()
    monkeypatch.setattr(provider, "_complete", lambda *args: {"question": "What is your favorite color?"})
    template = "Is your business currently incorporated?"
    assert provider.word_question("incorporation_status", template, {}) == template


def test_validated_quebec_location_completes_country_from_evidence():
    fields = assistant_service._validated_fields("Our company is in Montreal", [
        {"field": "province", "value": "QC", "confidence": "medium", "source_text": "Montreal"},
    ], {"province": "", "country": ""})
    assert {item["field"]: item["value"] for item in fields} == {"province": "QC", "country": "CA"}


def test_confirmed_update_survives_live_question_provider_outage(client, monkeypatch, db_engine):
    setup(client, monkeypatch)
    conversation = start(client)
    result = send(client, conversation["id"], "Our business is in Canada")
    with Session(db_engine) as db:
        record = db.get(m.AssistantConversation, UUID(conversation["id"]))
        record.mode = "live"
        db.commit()
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    suggestion = next(item for item in result["suggestions"] if item["field"] == "country")
    after = decide(client, conversation["id"], [{"id": suggestion["id"], "action": "accept"}])
    assert client.get("/api/demo/context").json()["organization"]["country"] == "CA"
    assert after["messages"][-1]["target_field"] == "industry"
