# syntax=docker/dockerfile:1
# NetCoop AI image (web/coordinator and the three specialist agents share it;
# compose.yaml chooses the command). Build stage installs locked deps; runtime is non-root.

FROM python:3.12-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.24 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first for layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY README.md ./
COPY spec ./spec
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12-slim-bookworm AS runtime
RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
    && mkdir -p /app/var/archives && chown -R app:app /app/var
WORKDIR /app
COPY --from=build --chown=app:app /app/.venv /app/.venv
# Packaged synthetic scenarios (read-only data; ground truth is only used by the evaluator).
COPY --chown=app:app data/scenarios /app/data/scenarios
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 \
    NETCOOP_SCENARIOS_DIR=/app/data/scenarios NETCOOP_ARCHIVE_UPLOADS_DIR=/app/var/archives
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2).status == 200 else 1)"]
# Apply schema migrations, then serve. Migrations are idempotent (no-op at head).
CMD ["sh", "-c", "netcoop db upgrade && exec uvicorn netcoop.api.app:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'"]
