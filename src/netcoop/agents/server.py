"""A2A server for one NetCoop specialist (independent OS process).

  python -m netcoop.agents.server --agent performance-agent --port 8101

Protocol: A2A JSON-RPC binding (a2a-sdk 1.3.0, protocol 1.0). Each request is a
message with ONE text part of media type application/vnd.netcoop.ndep+json holding
an NDEP AgentTask. The agent answers with an A2A Task whose artifact
'ndep-agent-result' holds the NDEP AgentResult as exact JSON text.

Authentication: when NETCOOP_AGENT_TOKEN is set, every request except the public
agent card must carry 'Authorization: Bearer <token>'.
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import os
import sys

from netcoop.agents.protocol import AGENT_VERSION, MEDIA_TYPE, PROTOCOL_VERSION, SPECIALISTS
from netcoop.agents.runtime import AgentConfig, handle, make_config


def build_card(agent_id: str, public_url: str):
    from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill

    spec = SPECIALISTS[agent_id]
    return AgentCard(
        name=spec["name"],
        description=f"{spec['description']} NDEP protocol {PROTOCOL_VERSION}. Agent id: {agent_id}.",
        version=AGENT_VERSION,
        supported_interfaces=[AgentInterface(url=public_url, protocol_binding="JSONRPC", protocol_version="1.0")],
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=[MEDIA_TYPE],
        default_output_modes=[MEDIA_TYPE],
        skills=[
            AgentSkill(id="investigate", name="Investigate incident evidence",
                       description=f"Analyse NDEP observations for: {', '.join(spec['metrics'])}. Returns NDEP findings.",
                       tags=["ndep", f"agent:{agent_id}", *[f"metric:{m}" for m in spec["metrics"]]],
                       input_modes=[MEDIA_TYPE], output_modes=[MEDIA_TYPE]),
            AgentSkill(id="verify", name="Answer a verification challenge",
                       description="Query an authorized recorded source for a requested observation; "
                                   "returns recorded records or 'unavailable'. Never synthesizes values.",
                       tags=["ndep", f"agent:{agent_id}", "recorded_replay"],
                       input_modes=[MEDIA_TYPE], output_modes=[MEDIA_TYPE]),
        ],
    )


def build_app(cfg: AgentConfig, public_url: str, token: str | None):
    from a2a.helpers.proto_helpers import new_task_from_user_message
    from a2a.server.agent_execution import AgentExecutor, RequestContext
    from a2a.server.events import EventQueue
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.routes import add_a2a_routes_to_fastapi, create_agent_card_routes, create_jsonrpc_routes
    from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
    from a2a.types import Part
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    card = build_card(cfg.agent_id, public_url)

    class SpecialistExecutor(AgentExecutor):
        async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
            msg = context.message
            task = context.current_task or new_task_from_user_message(msg)
            await event_queue.enqueue_event(task)
            updater = TaskUpdater(event_queue, task.id, task.context_id)
            await updater.start_work()
            texts = [p.text for p in msg.parts if p.HasField("text")] if msg else []
            request_text = texts[0] if texts else ""
            # domain work runs off the event loop (CPU-bound, deterministic)
            result_text = await asyncio.to_thread(handle, cfg, request_text)
            await updater.add_artifact([Part(text=result_text, media_type=MEDIA_TYPE)], name="ndep-agent-result")
            await updater.complete()

        async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
            raise NotImplementedError("tasks complete synchronously")

    handler = DefaultRequestHandler(agent_executor=SpecialistExecutor(), task_store=InMemoryTaskStore(),
                                    agent_card=card)
    app = FastAPI(title=f"NetCoop {cfg.agent_id}")

    @app.middleware("http")
    async def auth(request: Request, call_next):
        if token and not request.url.path.startswith("/.well-known/") and request.url.path != "/health":
            header = request.headers.get("authorization", "")
            supplied = header[7:] if header.lower().startswith("bearer ") else ""
            if not hmac.compare_digest(supplied.encode(), token.encode()):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

    @app.get("/health")
    def health() -> dict:
        return {"status": "live", "agent_id": cfg.agent_id, "version": AGENT_VERSION}

    add_a2a_routes_to_fastapi(app, agent_card_routes=create_agent_card_routes(card),
                              jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url="/"))
    return app


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="netcoop-agent")
    p.add_argument("--agent", required=True, choices=sorted(SPECIALISTS))
    p.add_argument("--host", default=os.environ.get("NETCOOP_AGENT_HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--public-url", default=None, help="URL advertised in the agent card (default http://host:port/)")
    p.add_argument("--scenarios-dir", default=os.environ.get("NETCOOP_SCENARIOS_DIR"))
    p.add_argument("--uploads-dir", default=os.environ.get("NETCOOP_ARCHIVE_UPLOADS_DIR"))
    args = p.parse_args(argv)
    import uvicorn

    from netcoop.procwatch import start_parent_watchdog

    start_parent_watchdog()
    cfg = make_config(args.agent, args.scenarios_dir, args.uploads_dir)
    url = args.public_url or f"http://{args.host}:{args.port}/"
    token = os.environ.get("NETCOOP_AGENT_TOKEN") or None
    uvicorn.run(build_app(cfg, url, token), host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
