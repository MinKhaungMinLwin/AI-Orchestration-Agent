set dotenv-load
export PROJECT_NAME := env("PROJECT_NAME", "tstation-ai")
export PROJECT_PREFIX := env("PROJECT_PREFIX", "tstation-agent")
export ENV := env("ENV", "local")
export COMPOSE_PROJECT_NAME := env("COMPOSE_PROJECT_NAME", PROJECT_PREFIX + "-" + ENV)
export REMOTE_COMPOSE_FILE := env("COMPOSE_FILE", "docker/docker-compose.yml")

# Default is helper
default:
    just help


# Export to .env
environment:
    cp .env.example .env


### Development ###
clear-venv:
    rm -rf .venv .uv_cache

dependency:
    # App
    uv export --only-group tstation-ai -o app/tstation-ai/requirements.txt
    # UI
    uv export --only-group tstation-ui-demo -o app/tstation-ui-demo/requirements.txt


install: dependency
    $HOME/.local/bin/uv sync --all-groups --cache-dir .uv_cache

install-hooks:
    uv run pre-commit install

setup: clear-venv install
    cp example/tstation-ai/router_local.py app/tstation-ai/api/router_local.py
    cp -r example/docker_local docker_local

    curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh

    echo "Setup done. Run 'source .venv/bin/activate' to activate the virtual environment."


# Format code
lint:
    ruff check .

fmt:
    uv run ruff check --fix
    uv run isort ./app


# Deploy Local
start-local:
    @echo "Starting PROJECT '{{PROJECT_NAME}}-{{ENV}}' with ENVIRONMENT: {{ENV}}"
    docker compose --env-file .env \
        -p {{PROJECT_NAME}}-{{ENV}} \
        -f docker_local/docker-compose-llm.yml \
        -f docker_local/docker-compose-app.yml \
        up --build -d

stop-local:
    docker compose --env-file .env \
        -p {{PROJECT_NAME}}-{{ENV}} \
        -f docker_local/docker-compose-llm.yml \
        -f docker_local/docker-compose-app.yml \
        down

### Deployment ###

# Hardcoded list of known-stale compose project names that should be swept
# before every deployment. Add to this list as you discover more orphans.
# Do NOT add the current deployment's project name or any active deployment.
KNOWN_ORPHAN_PROJECTS := "tstation-agent-dev tstation-agent docker"

# Sweep up orphaned compose projects with old PROJECT_NAME values.
# Uses `docker rm -f` because `compose down` can fail silently on stale state.
# Skip with: SKIP_CLEAN_ORPHANS=1 just start
clean-orphans:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "${SKIP_CLEAN_ORPHANS:-0}" = "1" ]; then
        echo "SKIP_CLEAN_ORPHANS=1 → skipping orphan cleanup"
        exit 0
    fi
    echo "Sweeping orphan compose projects..."
    for proj in {{KNOWN_ORPHAN_PROJECTS}}; do
        if [ "$proj" = "{{COMPOSE_PROJECT_NAME}}" ]; then
            echo "  '$proj' matches current deployment — skipping"
            continue
        fi
        cids=$(docker ps -aq --filter "label=com.docker.compose.project=$proj" 2>/dev/null || true)
        if [ -n "$cids" ]; then
            n=$(echo $cids | wc -w)
            echo "  Removing $n container(s) from orphan '$proj'"
            docker rm -f $cids >/dev/null
        fi
    done
    echo "Orphan cleanup done."

precreate-remote:
    @echo "Building Docker images without cache for PROJECT '{{COMPOSE_PROJECT_NAME}}'"
    docker compose --env-file .env \
        -p {{COMPOSE_PROJECT_NAME}} \
        -f {{REMOTE_COMPOSE_FILE}} \
        up --build --force-recreate --no-start

stop-remote:
    docker compose --env-file .env \
        -p {{COMPOSE_PROJECT_NAME}} \
        -f {{REMOTE_COMPOSE_FILE}} \
        down


start-remote: clean-orphans precreate-remote stop-remote
    @echo "Starting PROJECT '{{COMPOSE_PROJECT_NAME}}' with ENVIRONMENT: {{ENV}}"
    docker compose --env-file .env \
        -p {{COMPOSE_PROJECT_NAME}} \
        -f {{REMOTE_COMPOSE_FILE}} \
        up --build -d

up service="tstation-ai":
    @if [ "{{ENV}}" = "local" ]; then \
        docker compose --env-file .env \
            -p {{PROJECT_NAME}}-{{ENV}} \
            -f docker_local/docker-compose-llm.yml \
            -f docker_local/docker-compose-app.yml \
            up --build -d {{service}}; \
    else \
        docker compose --env-file .env \
            -p {{COMPOSE_PROJECT_NAME}} \
            -f {{REMOTE_COMPOSE_FILE}} \
            up -d --build {{service}}; \
    fi

down:
    @if [ "{{ENV}}" = "local" ]; then \
        just stop-local; \
    else \
        docker compose --env-file .env \
            -p {{COMPOSE_PROJECT_NAME}} \
            -f {{REMOTE_COMPOSE_FILE}} \
            down; \
    fi

logs service="tstation-ai":
    @if [ "{{ENV}}" = "local" ]; then \
        docker compose --env-file .env \
            -p {{PROJECT_NAME}}-{{ENV}} \
            -f docker_local/docker-compose-llm.yml \
            -f docker_local/docker-compose-app.yml \
            logs -f {{service}}; \
    else \
        docker compose --env-file .env \
            -p {{COMPOSE_PROJECT_NAME}} \
            -f {{REMOTE_COMPOSE_FILE}} \
            logs -f {{service}}; \
    fi

ps:
    @if [ "{{ENV}}" = "local" ]; then \
        docker compose --env-file .env \
            -p {{PROJECT_NAME}}-{{ENV}} \
            -f docker_local/docker-compose-llm.yml \
            -f docker_local/docker-compose-app.yml \
            ps; \
    else \
        docker compose --env-file .env \
            -p {{COMPOSE_PROJECT_NAME}} \
            -f {{REMOTE_COMPOSE_FILE}} \
            ps; \
    fi

stop:
    @just down

start:
    @just up

## Update OpenAPI
update-openapi:
    openapi-python-client generate \
      --path app/tstation-be-openapi.json \
      --output-path app/tstation-ai/common/tstation_be_api_client \
      --overwrite

## Security
scan-images:
    @echo "=== Scanning Docker images with Trivy ==="
    @echo "NOTE: Install trivy first: curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh"
    @echo ""
    @echo "--- Scanning litellm ---"
    ./bin/trivy image --severity HIGH,CRITICAL --format table ghcr.io/berriai/litellm:v1.83.4-nightly || true
    @echo ""
    @echo "--- Scanning tstation-ai ---"
    ./bin/trivy image --severity HIGH,CRITICAL --format table {{COMPOSE_PROJECT_NAME}}-tstation-ai:latest || true
    @echo ""
    @echo "--- Scanning tstation-ui-demo ---"
    ./bin/trivy image --severity HIGH,CRITICAL --format table {{COMPOSE_PROJECT_NAME}}-tstation-ui-demo:latest || true
    @echo ""
    @echo "--- Scanning nginx ---"
    ./bin/trivy image --severity HIGH,CRITICAL --format table nginx:alpine || true
    @echo ""
    @echo "--- Scanning redis ---"
    ./bin/trivy image --severity HIGH,CRITICAL --format table redis || true
    @echo ""
    @echo "--- Scanning qdrant ---"
    ./bin/trivy image --severity HIGH,CRITICAL --format table qdrant/qdrant:latest || true
    @echo "=== Scan complete ==="

## Helper
help:
    @echo "### For Deployment (dev, stag, prod)"
    @echo "just environment     Setup .env file"
    @echo "just up              Build + start tstation-ai service"
    @echo "just logs            Follow tstation-ai logs"
    @echo "just down            Stop compose project"
    @echo "just ps              Show compose services"
    @echo "just start-remote    Build (no cache) + Start servers"
    @echo "just stop-remote     Stop servers"
    @echo "just scan-images     Scan Docker images for vulnerabilities"

    @echo "### For Development (local)"
    @echo "just environment     Setup .env file"
    @echo "just setup           Setup python environment at [local]"
    @echo "just fmt             Format python code at [local]"
    @echo "just lint            Check rule of python code at [local]"
    @echo "just dependency      Add requirement.txt dependency for python project at [local]"
    @echo "just install         Update environment with new dependency"
    @echo "just start           Start servers with docker"
    @echo "just stop            Stop servers"
    @echo "just scan-images     Scan Docker images for vulnerabilities"
