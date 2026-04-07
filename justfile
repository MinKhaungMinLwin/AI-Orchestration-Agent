set dotenv-load
export PROJECT_NAME := env("PROJECT_NAME", "tstation-ai")
export ENV := env("ENV", "local")

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
    @echo "Starting PROJECT '{{PROJECT_NAME}}' with ENVIRONMENT: {{ENV}}"
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
start-remote:
    @echo "Starting PROJECT '{{PROJECT_NAME}}' with ENVIRONMENT: {{ENV}}"
    docker compose --env-file .env \
        -p {{PROJECT_NAME}}-{{ENV}} \
        -f docker/docker-compose.yml \
        up --build -d

stop-remote:
    docker compose --env-file .env \
        -p {{PROJECT_NAME}}-{{ENV}} \
        -f docker/docker-compose.yml \
        down

stop:
    @if [ "{{ENV}}" = "local" ]; then \
        just stop-local; \
    else \
        just stop-remote; \
    fi

start:
    @if [ "{{ENV}}" = "local" ]; then \
        just start-local; \
    else \
        just start-remote; \
    fi

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
    ./bin/trivy image --severity HIGH,CRITICAL --format table {{PROJECT_NAME}}-{{ENV}}-tstation-ai:latest || true
    @echo ""
    @echo "--- Scanning tstation-ui-demo ---"
    ./bin/trivy image --severity HIGH,CRITICAL --format table {{PROJECT_NAME}}-{{ENV}}-tstation-ui-demo:latest || true
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
    @echo "just start           Start servers with docker"
    @echo "just stop            Stop servers"
    @echo "just scan-images    Scan Docker images for vulnerabilities"

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
