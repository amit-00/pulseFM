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
build_and_push encoder services/encoder/Dockerfile
build_and_push playback-service services/playback-service/Dockerfile
build_and_push playback-stream services/playback-stream/Dockerfile
build_and_push modal-dispatch-service services/modal-dispatch-service/Dockerfile

echo "Done. Images pushed to ${registry} with tag ${TAG}."
