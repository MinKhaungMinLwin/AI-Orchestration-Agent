set dotenv-load
export PROJECT_NAME := env("PROJECT_NAME", "tstation-ai")
export ENV := env("ENV", "local")
## Docker Environment
DOCKER_SHARED_FILES_NAME := "$PROJECT_NAME-shared-files-$ENV"
DOCKER_LOG_FOLDER_NAME := "$PROJECT_NAME-log-folder-$ENV"
DOCKER_NETWORK_NAME := "$PROJECT_NAME-$ENV-net"

# Default is helper
default:
    just help

# Export env.docker
export-env-docker:
    echo "# Volumes" > .env.docker
    echo "DOCKER_SHARED_FILES_NAME={{DOCKER_SHARED_FILES_NAME}}" >> .env.docker
    echo "DOCKER_LOG_FOLDER_NAME={{DOCKER_LOG_FOLDER_NAME}}" >> .env.docker
    echo "# Networks" >> .env.docker
    echo "DOCKER_NETWORK_NAME={{DOCKER_NETWORK_NAME}}" >> .env.docker

# Export to .env
environment: export-env-docker
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

    echo "Setup done. Run 'source .venv/bin/activate' to activate the virtual environment."


# Format code
lint:
    ruff check .

fmt:
    uv run ruff check --fix
    uv run isort ./app


# Deploy Local
precreate-local: export-env-docker
    docker compose --env-file .env.docker --env-file .env \
        -p {{PROJECT_NAME}}-{{ENV}} \
        -f docker_local/docker-compose-llm.yml \
        -f docker_local/docker-compose-app.yml \
        up --build --force-recreate --no-start

stop-local:
    docker compose --env-file .env.docker --env-file .env \
        -p {{PROJECT_NAME}}-{{ENV}} \
        -f docker_local/docker-compose-llm.yml \
        -f docker_local/docker-compose-app.yml \
        down

start-local: precreate-local stop-local create-volumes
    @echo "Starting PROJECT '{{PROJECT_NAME}}' with ENVIRONMENT: {{ENV}}"
    docker compose --env-file .env.docker --env-file .env \
        -p {{PROJECT_NAME}}-{{ENV}} \
        -f docker_local/docker-compose-llm.yml \
        -f docker_local/docker-compose-app.yml \
        up -d

### Deployment ###
create-volumes:
    docker volume create {{DOCKER_SHARED_FILES_NAME}}
    docker volume create {{DOCKER_LOG_FOLDER_NAME}}

build-images:
    # Docker Container Background System
    # docker build -t $CONTAINER_DEFAULT_NAME-$CONTAINER_A_TAGNAME:$ENV app/containers/container_a

precreate-remote: export-env-docker create-volumes
    docker compose --env-file .env.docker --env-file .env \
        -p {{PROJECT_NAME}}-{{ENV}} \
        -f docker/docker-compose-llm.yml \
        -f docker/docker-compose-app.yml \
        -f docker/docker-compose-nginx.yml \
        up --build --force-recreate --no-start

stop-remote:
    docker compose --env-file .env.docker --env-file .env \
        -p {{PROJECT_NAME}}-{{ENV}} \
        -f docker/docker-compose-llm.yml \
        -f docker/docker-compose-app.yml \
        -f docker/docker-compose-nginx.yml \
        down

start-remote: precreate-remote stop-remote
    @echo "Starting PROJECT '{{PROJECT_NAME}}' with ENVIRONMENT: {{ENV}}"
    docker compose --env-file .env.docker --env-file .env \
        -p {{PROJECT_NAME}}-{{ENV}} \
        -f docker/docker-compose-llm.yml \
        -f docker/docker-compose-app.yml \
        -f docker/docker-compose-nginx.yml \
        up -d

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


## Deploy in Runway, dont have docker-compose
start-runway-ai:
    set -a && . .env && set +a && nohup uv run app/tstation-ai/main.py > /dev/null 2>&1 &

stop-runway-ai:
    pkill -f "app/tstation-ai/main.py" || true

start-runway-be:
    set -a && . app/tstation-be/.env && set +a && nohup uv run app/tstation-be/main.py > /dev/null 2>&1 &

stop-runway-be:
    pkill -f "app/tstation-be/main.py" || true

start-runway-ui-demo:
    set -a && . .env && set +a && nohup uv run streamlit run app/tstation-ui-demo/Home.py --server.port 7777 --server.address 0.0.0.0 > /dev/null 2>&1 &

stop-runway-ui-demo:
    pkill -f "streamlit run app/tstation-ui-demo/Home.py" || true

start-runway:
    set -a && . .env && set +a && nohup uv run app/tstation-ai/main.py > /dev/null 2>&1 &
    set -a && . app/tstation-be/.env && set +a && nohup uv run app/tstation-be/main.py > /dev/null 2>&1 &
    set -a && . .env && set +a && nohup uv run streamlit run app/tstation-ui-demo/Home.py --server.port 7777 --server.address 0.0.0.0 > /dev/null 2>&1 &

stop-runway:
    pkill -f uv


## Helper
help:
    @echo "### For Deployment (dev, stag, prod)"
    @echo "just environment     Setup .env file"
    @echo "just start           Start servers with docker"
    @echo "just stop            Stop servers"

    @echo "### For Development (local)"
    @echo "just environment     Setup .env file"
    @echo "just setup           Setup python environment at [local]"
    @echo "just fmt             Format python code at [local]"
    @echo "just lint            Check rule of python code at [local]"
    @echo "just dependency      Add requirement.txt dependency for python project at [local]"
    @echo "just install         Update environment with new dependency"
    @echo "just start           Start servers with docker"
    @echo "just stop            Stop servers"
