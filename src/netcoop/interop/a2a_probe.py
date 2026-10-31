"""A2A SDK compatibility probe - NOT a NetCoop diagnostic agent.

Gate 1 asks us to check early that the pinned a2a-sdk works on this platform
across two OS processes. This module runs a tiny A2A server whose only skill is
to return a structural receipt for a submitted JSON document (its SHA-256 and
the type of each top-level field). It performs no diagnosis.

Run the server:  python -m netcoop.interop.a2a_probe serve --port 8710
Run the client:  python -m netcoop.interop.a2a_probe call http://127.0.0.1:8710
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys

PROBE_MEDIA_TYPE = "application/json"


def build_app(port: int):
    import uvicorn  # noqa: F401  (import check only)
    from a2a.helpers.proto_helpers import get_text_parts, new_text_message
    from a2a.server.agent_execution import AgentExecutor, RequestContext
    from a2a.server.events import EventQueue
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.routes import (
        add_a2a_routes_to_fastapi,
        create_agent_card_routes,
        create_jsonrpc_routes,
    )
    from a2a.server.tasks import InMemoryTaskStore
    from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
    from fastapi import FastAPI

    card = AgentCard(
        name="netcoop-a2a-sdk-probe",
        description="SDK compatibility probe. Returns a structural receipt; performs no diagnosis.",
        version="0.0.1",
        supported_interfaces=[
            AgentInterface(
                url=f"http://127.0.0.1:{port}/",
                protocol_binding="JSONRPC",
                protocol_version="1.0",
            )
        ],
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(
                id="receipt",
                name="Structural receipt",
                description="Hash a JSON document and list its top-level field types.",
                tags=["probe"],
            )
        ],
    )

    class ReceiptExecutor(AgentExecutor):
        async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
            texts = get_text_parts(context.message.parts) if context.message else []
            raw = texts[0] if texts else ""
            try:
                doc = json.loads(raw)
                receipt = {
                    "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    "field_types": {k: type(v).__name__ for k, v in doc.items()},
                }
            except (ValueError, AttributeError) as exc:
                receipt = {"error": f"not a JSON object ({type(exc).__name__})"}
            await event_queue.enqueue_event(new_text_message(json.dumps(receipt, sort_keys=True)))

        async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
            raise NotImplementedError

    handler = DefaultRequestHandler(
        agent_executor=ReceiptExecutor(), task_store=InMemoryTaskStore(), agent_card=card
    )
    app = FastAPI(title="netcoop-a2a-sdk-probe")
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url="/"),
    )
    return app


async def call(base_url: str, document: dict) -> dict:
    """Resolve the agent card over HTTP and send one A2A message. Returns the receipt."""
    from a2a.client import create_client
    from a2a.helpers.proto_helpers import get_text_parts, new_text_message
    from a2a.types import Role, SendMessageRequest

    payload = json.dumps(document, sort_keys=True)
    client = await create_client(base_url)
    request = SendMessageRequest(message=new_text_message(payload, role=Role.ROLE_USER))
    replies = []
    async for resp in client.send_message(request):
        replies.append(resp)
    for resp in replies:
        if resp.HasField("message"):
            texts = get_text_parts(resp.message.parts)
            receipt = json.loads(texts[0])
            receipt["_sent_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            return receipt
    raise RuntimeError(f"no message in A2A response: {replies!r}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="a2a_probe")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8710)
    c = sub.add_parser("call")
    c.add_argument("url")
    args = p.parse_args(argv)
    if args.cmd == "serve":
        import uvicorn

        uvicorn.run(build_app(args.port), host="127.0.0.1", port=args.port, log_level="warning")
        return 0
    receipt = asyncio.run(call(args.url, {"probe": True, "count": 4326, "unit": "count"}))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
