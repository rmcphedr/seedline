"""Generate the checked-in OpenFlow YAML from one small Bridge HTTP step."""

from pathlib import Path

import yaml

CALL = """import json
import urllib.request
import urllib.error
import wmill

def main(enrichment_job_id: str, stage: str, opportunity_id: str = ""):
    base = wmill.get_variable("f/bridge/api_url").rstrip("/")
    key = wmill.get_variable("f/bridge/worker_api_key")
    endpoint = f"{base}/api/internal/enrichment-jobs/{enrichment_job_id}/{stage}"
    if stage == "load":
        endpoint += f"?opportunity_id={opportunity_id}"
    request = urllib.request.Request(endpoint, method="GET" if stage == "load" else "POST",
        headers={"X-Worker-Key": key, "Content-Type": "application/json"},
        data=None if stage == "load" else b"{}")
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Bridge {stage} failed ({exc.code}): {exc.read(1000).decode()}") from exc
"""

FAIL = """import json
import urllib.request
import wmill

def main(enrichment_job_id: str, error: dict):
    base = wmill.get_variable("f/bridge/api_url").rstrip("/")
    key = wmill.get_variable("f/bridge/worker_api_key")
    message = str(error.get("message", error) if isinstance(error, dict) else error)[:4000]
    request = urllib.request.Request(
        f"{base}/api/internal/enrichment-jobs/{enrichment_job_id}/fail",
        data=json.dumps({"error": message}).encode(), method="POST",
        headers={"X-Worker-Key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)
"""


def js(expression):
    return {"type": "javascript", "expr": expression}


def static(value):
    return {"type": "static", "value": value}


def stage(name):
    return {
        "id": name,
        "summary": {
            "load": "Load opportunity",
            "fetch": "Fetch and store source",
            "extract": "Extract structured fields",
            "validate": "Validate source evidence and proposed fields",
            "stage": "Stage proposal for admin review",
            "smoke_complete": "Complete Bridge smoke job",
        }[name],
        "value": {
            "type": "rawscript",
            "language": "python3",
            "content": CALL,
            "input_transforms": {
                "enrichment_job_id": js("flow_input.enrichment_job_id"),
                "stage": static(name),
                "opportunity_id": js("flow_input.opportunity_id"),
            },
        },
    }


def flow(stages, summary):
    step = {
        "summary": summary,
        "description": "Bridge owns fetching, extraction, validation, persistence and review. Windmill orchestrates only.",
        "schema": {
            "type": "object",
            "required": ["opportunity_id", "enrichment_job_id"],
            "properties": {
                "opportunity_id": {"type": "string", "format": "uuid"},
                "enrichment_job_id": {"type": "string", "format": "uuid"},
            },
        },
        "value": {
            "modules": [stage(name) for name in stages],
            "failure_module": {
                "id": "failure",
                "summary": "Report failure to Bridge",
                "value": {
                    "type": "rawscript",
                    "language": "python3",
                    "content": FAIL,
                    "input_transforms": {
                        "enrichment_job_id": js("flow_input.enrichment_job_id"),
                        "error": js("previous_result.error"),
                    },
                },
            },
        },
    }
    if name == "load":
        step["stop_after_if"] = {"expr": "result.classification === 'directory'", "skip_if_stopped": False}
    if name in {"fetch", "extract"}:
        step["retry"] = {"constant": {"attempts": 2, "seconds": 3}}
    return step


if __name__ == "__main__":
    root = Path(__file__).parent
    for name, stages, summary in (
        ("enrich_funding_opportunity", ["load", "fetch", "extract", "validate", "stage"], "enrich_funding_opportunity"),
        ("enrichment_smoke", ["load", "smoke_complete"], "Bridge enrichment smoke test"),
    ):
        folder = root / f"{name}.flow"
        folder.mkdir(exist_ok=True)
        (folder / "flow.yaml").write_text(yaml.safe_dump(flow(stages, summary), sort_keys=False))
