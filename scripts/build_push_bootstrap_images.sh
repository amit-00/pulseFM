#!/bin/bash
set -euo pipefail

PROJECT_ID=${PROJECT_ID:-pulsefm-484500}
REGION=${REGION:-northamerica-northeast1}
REPO=${REPO:-pulsefm}
TAG=${TAG:-bootstrap}

registry="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"

build_and_push() {
  local name=$1
  local dockerfile=$2
  echo "Building ${name}..."
  docker build --platform linux/amd64 -t "${registry}/${name}:${TAG}" -f "${dockerfile}" .
  echo "Pushing ${name}..."
  docker push "${registry}/${name}:${TAG}"
}

build_and_push vote-api services/vote-api/Dockerfile
build_and_push vote-orchestrator services/vote-orchestrator/Dockerfile
build_and_push encoder services/encoder/Dockerfile
build_and_push playback-orchestrator services/playback-orchestrator/Dockerfile
build_and_push vote-stream services/vote-stream/Dockerfile

echo "Done. Images pushed to ${registry} with tag ${TAG}."
