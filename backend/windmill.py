"""Small client for Windmill's asynchronous flow webhook."""

import os
from uuid import UUID

import httpx


class WindmillClient:
    def __init__(self, url: str, workspace: str, flow_path: str, token: str):
        if not all((url, workspace, flow_path, token)) or not flow_path.startswith(("f/", "u/", "g/")):
            raise ValueError("Windmill URL, workspace, flow path, and API token are required")
        self.url = url.rstrip("/")
        self.workspace = workspace
        self.flow_path = flow_path
        self.token = token
        self.http_client = None

    @classmethod
    def from_env(cls):
        return cls(
            os.getenv("WINDMILL_URL", ""),
            os.getenv("WINDMILL_WORKSPACE", ""),
            os.getenv("WINDMILL_FLOW_PATH", ""),
            os.getenv("WINDMILL_API_TOKEN", ""),
        )

    async def trigger(self, opportunity_id: UUID, enrichment_job_id: UUID) -> UUID:
        url = f"{self.url}/api/w/{self.workspace}/jobs/run/f/{self.flow_path}"
        client = self.http_client or httpx.AsyncClient(timeout=15)
        try:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {self.token}"},
                json={"opportunity_id": str(opportunity_id), "enrichment_job_id": str(enrichment_job_id)},
            )
            response.raise_for_status()
            try:
                job_id = response.json()
            except ValueError:
                job_id = response.text.strip()
            return UUID(str(job_id).strip('"'))
        finally:
            if self.http_client is None:
                await client.aclose()
