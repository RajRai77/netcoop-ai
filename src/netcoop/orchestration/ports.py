"""AgentPort implementations: how the coordinator reaches a specialist.

- A2AAgentPort: real A2A JSON-RPC to an independently running agent process. This is
  the only transport that counts as inter-agent interoperability.
- InProcessAgentPort: calls the same specialist runtime inside this process. Used by
  unit tests and evaluation baselines; reports are labeled transport='in-process'.

Both carry the identical NDEP JSON text, so semantics are the same.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field

from netcoop.agents.protocol import MEDIA_TYPE, SPECIALISTS


class TransportError(RuntimeError):
    def __init__(self, kind: str, message: str):
        self.kind = kind  # timeout | unreachable | protocol | unauthorized
        super().__init__(message)


@dataclass
class Discovery:
    agent_id: str
    metrics: set[str]
    skills: list[str]
    card: dict = field(default_factory=dict)


@dataclass
class Reply:
    text: str
    meta: dict


class InProcessAgentPort:
    transport = "in-process"

    def __init__(self, agent_id: str, scenarios_dir=None, uploads_dir=None):
        from netcoop.agents.runtime import make_config

        self.agent_id = agent_id
        self.cfg = make_config(agent_id, scenarios_dir, uploads_dir)

    async def discover(self, timeout_s: float) -> Discovery:
        spec = SPECIALISTS[self.agent_id]
        return Discovery(self.agent_id, set(spec["metrics"]), ["investigate", "verify"],
                         {"name": spec["name"], "transport": "in-process"})

    async def send(self, request_text: str, timeout_s: float) -> Reply:
        from netcoop.agents.runtime import handle

        try:
            text = await asyncio.wait_for(asyncio.to_thread(handle, self.cfg, request_text), timeout_s)
        except TimeoutError:
            raise TransportError("timeout", f"in-process {self.agent_id} exceeded {timeout_s}s") from None
        return Reply(text, {"transport": "in-process"})


class A2AAgentPort:
    """Allowlisted remote specialist. The expected agent_id and card name come from
    local configuration, never from the remote card itself."""

    transport = "a2a"

    def __init__(self, agent_id: str, url: str, token: str | None = None):
        if agent_id not in SPECIALISTS:
            raise ValueError(f"agent {agent_id!r} is not an allowlisted specialist")
        self.agent_id = agent_id
        self.url = url.rstrip("/") + "/"
        self.token = token
        self._card = None

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def discover(self, timeout_s: float) -> Discovery:
        import httpx
        from a2a.client import A2ACardResolver
        from google.protobuf.json_format import MessageToDict

        try:
            async with httpx.AsyncClient(timeout=timeout_s, headers=self._headers()) as http:
                card = await A2ACardResolver(http, self.url).get_agent_card()
        except httpx.TimeoutException:
            raise TransportError("timeout", f"agent card of {self.agent_id} not returned in {timeout_s}s") from None
        except Exception as exc:
            raise TransportError("unreachable", f"{self.agent_id} at {self.url}: {type(exc).__name__}: {exc}") from None
        expected = SPECIALISTS[self.agent_id]["name"]
        if card.name != expected:
            raise TransportError("protocol", f"card name {card.name!r} does not match allowlisted {expected!r}")
        ifaces = [(i.protocol_binding, i.protocol_version) for i in card.supported_interfaces]
        if ("JSONRPC", "1.0") not in ifaces:
            raise TransportError("protocol", f"{self.agent_id} offers {ifaces}; NetCoop requires JSONRPC with "
                                             "A2A protocol 1.0")
        skills = {s.id: s for s in card.skills}
        if not {"investigate", "verify"} <= set(skills):
            raise TransportError("protocol", f"{self.agent_id} card lacks investigate/verify skills")
        if f"agent:{self.agent_id}" not in skills["investigate"].tags:
            raise TransportError("protocol", f"card does not declare agent id {self.agent_id}")
        metrics = {t.split(":", 1)[1] for t in skills["investigate"].tags if t.startswith("metric:")}
        allowed = set(SPECIALISTS[self.agent_id]["metrics"])
        if not metrics <= allowed:  # a card cannot grant itself extra domains
            raise TransportError("protocol", f"card claims metrics outside its allowlisted domain: {sorted(metrics - allowed)}")
        self._card = card
        return Discovery(self.agent_id, metrics, sorted(skills), MessageToDict(card))

    async def send(self, request_text: str, timeout_s: float) -> Reply:
        import httpx
        from a2a.client import ClientConfig, ClientFactory
        from a2a.types import Message, Part, Role, SendMessageRequest

        if self._card is None:
            await self.discover(timeout_s)
        message_id = f"MSG-{uuid.uuid4().hex}"
        msg = Message(message_id=message_id, role=Role.ROLE_USER,
                      parts=[Part(text=request_text, media_type=MEDIA_TYPE)])
        try:
            async with httpx.AsyncClient(timeout=timeout_s, headers=self._headers()) as http:
                client = ClientFactory(ClientConfig(streaming=False, httpx_client=http)).create(self._card)
                responses = []

                async def collect():
                    async for r in client.send_message(SendMessageRequest(message=msg)):
                        responses.append(r)

                await asyncio.wait_for(collect(), timeout_s)
        except (TimeoutError, httpx.TimeoutException):
            raise TransportError("timeout", f"{self.agent_id} did not answer within {timeout_s}s") from None
        except httpx.HTTPStatusError as exc:
            kind = "unauthorized" if exc.response.status_code == 401 else "protocol"
            raise TransportError(kind, f"{self.agent_id}: HTTP {exc.response.status_code}") from None
        except TransportError:
            raise
        except Exception as exc:
            text = f"{type(exc).__name__}: {exc}"
            kind = "unauthorized" if "401" in text else ("unreachable" if "connect" in text.lower() else "protocol")
            raise TransportError(kind, f"{self.agent_id}: {text}") from None
        task = None
        for r in responses:
            if r.HasField("task"):
                task = r.task
        if task is None:
            raise TransportError("protocol", f"{self.agent_id} returned no A2A task")
        texts = [p.text for a in task.artifacts if a.name == "ndep-agent-result" for p in a.parts
                 if p.HasField("text") and p.media_type == MEDIA_TYPE]
        if len(texts) != 1:
            raise TransportError("protocol", f"{self.agent_id}: expected exactly one ndep-agent-result artifact")
        meta = {"transport": "a2a", "a2a_message_id": message_id, "a2a_task_id": task.id,
                "a2a_context_id": task.context_id, "a2a_task_state": int(task.status.state),
                "a2a_artifact_ids": [a.artifact_id for a in task.artifacts], "agent_url": self.url}
        return Reply(texts[0], meta)


def ports_from_config(spec: str | None, token: str | None) -> list[A2AAgentPort]:
    """NETCOOP_AGENTS: JSON {"performance-agent": "http://127.0.0.1:8101/", ...}."""
    if not spec:
        return []
    try:
        mapping = json.loads(spec)
    except ValueError as exc:
        raise ValueError(f"NETCOOP_AGENTS is not valid JSON: {exc}") from None
    return [A2AAgentPort(aid, url, token) for aid, url in sorted(mapping.items())]
