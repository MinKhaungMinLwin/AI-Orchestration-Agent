#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

TAG="dev-latest"
REG="10.171.10.119:5000/tstation-ai"
STACK_NAME="tstation-agent-dev"

export AGENT_AI_IMAGE="${REG}/aichatbot-agent-ai:${TAG}"
export AGENT_INGESTION_IMAGE="${REG}/aichatbot-agent-ingestion:${TAG}"

set -a
source .env
set +a

echo "=== Removing old stack to clear corrupted tasks ==="
docker stack rm "${STACK_NAME}" || true

echo "Waiting for stack services to clear..."
sleep 10

echo "=== Deploying Stack: ${STACK_NAME} ==="

docker stack deploy \
  -c docker-compose.swarm.yml \
  --with-registry-auth \
  "${STACK_NAME}"

echo ""
echo "Deployment command sent. Waiting 10 seconds to check status..."
sleep 10
docker stack services "${STACK_NAME}"
