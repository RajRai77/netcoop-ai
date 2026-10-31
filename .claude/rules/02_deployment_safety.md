# Security and deployment (always applicable)

- The complete core must start on Linux using checked-in Docker Compose manifests with persistent DB volume and health checks. The production compose file must not mount source code writable into runtime containers.
- Expose only HTTPS/reverse-proxy entrypoint publicly; keep agents, DB and internal service ports on private networks. Use service-name DNS, never container localhost for cross-container calls.
- Read-only telemetry by default. No unauthorized scans, writes, interface changes, DHCP actions or privileged access to production systems.
- No API keys, passwords, access tokens or real telemetry secrets in code, `.env.example`, fixtures, output reports or logs. Protect uploaded data and limit size.
- Avoid privileged containers or Docker socket mounts in the web application.
- A failing dependency is not hidden: health, task coverage and output limitations must reflect it.
- Preserve migrations, DB backups and restoration steps; `docker compose down -v` destroys volumes.
