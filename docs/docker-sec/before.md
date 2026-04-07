# Scout Report: Docker Security Compliance

## Reference
- Security requirements: `playground/security.md`

---

## Security Requirements vs Current State

| Requirement | Status | Finding |
|-------------|--------|---------|
| **3.1 Non-root User** | :x: MISSING | Dockerfiles use default root user from `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`. No `USER appuser` configured |
| **3.2 Privileged Mode** | :warning: NOT SET | No `privileged: false` explicit in compose files |
| **3.3 Filesystem Restriction** | :x: MISSING | No `read_only: true`; volumes not read-only |
| **3.4 Network Isolation** | :warning: PARTIAL | `project-net` is bridge but NOT `internal: true` |
| **3.5 Port Restriction** | :x: MISSING | Nginx: `"${NGINX_PORT}:80"` binds to `0.0.0.0`, not `127.0.0.1` |
| **3.6 Security Options** | :x: MISSING | No `security_opt: no-new-privileges:true` or `cap_drop: ALL` |
| **3.7 Resource Limits** | :x: MISSING | No `deploy.resources.limits` in any service |
| **3.8 Logging** | :x: MISSING | No `logging` driver configuration |
| **TLS/HTTPS** | :x: MISSING | nginx.conf only listens on port 80, no TLS configured |

---

## Files Analyzed

### Docker Compose
| File | Services |
|------|----------|
| `docker/docker-compose-app.yml` | tstation-ai, redis-conversation-management, tstation-ui-demo, monitor-agent |
| `docker/docker-compose-llm.yml` | ai-gateway (LiteLLM) |
| `docker/docker-compose-nginx.yml` | nginx proxy |

### Dockerfiles
| File | Base Image | User |
|------|------------|------|
| `app/tstation-ai/Dockerfile` | `uv:python3.12-bookworm-slim` | root |
| `app/tstation-ui-demo/Dockerfile` | `uv:python3.12-bookworm-slim` | root |

### Config
- `docker/config/nginx.conf` - HTTP only (port 80), no TLS

---

## Checklist

| Item | Status |
|------|--------|
| No root user | :x: |
| No privileged mode | :warning: Not set |
| Network isolation | :warning: Partial |
| TLS enabled | :x: |
| Logging configured | :x: |
| Image scanned | :x: Not done |

---

## Summary

**Compliance: 0/6 items fully met**

All mandatory security settings from `playground/security.md` are missing:
- All containers run as root
- No resource limits, logging, or security options
- Network is not isolated (`internal: true` not set)
- Nginx exposes HTTP only (no TLS)
- Port binding not restricted to localhost

---

## Recommended Fixes

1. Add non-root user in Dockerfiles (`RUN adduser -D appuser && USER appuser`)
2. Add `security_opt: no-new-privileges:true` and `cap_drop: ALL` to all services
3. Set `read_only: true` for containers with tmpfs for writable paths
4. Add `internal: true` to `project-net` network definition
5. Change nginx port binding to `127.0.0.1:${NGINX_PORT}:80`
6. Add `deploy.resources.limits` (cpus, memory) to all services
7. Add `logging` driver with `max-size: "10m"` and `max-file: "3"`
8. Configure TLS in nginx for HTTPS (or terminate at load balancer)

---

**Status:** DONE
