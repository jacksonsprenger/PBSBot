#!/usr/bin/env bash
# Build a linux/amd64 image on Apple Silicon (or any host) for x86_64 VMs.
# Usage:
#   ./scripts/docker-build-amd64.sh thugken/pbs_bot:latest          # load into local Docker
#   ./scripts/docker-build-amd64.sh thugken/pbs_bot:latest --push   # push to Hub

set -euo pipefail
TAG="${1:?Usage: $0 <image:tag> [--push]}"
PUSH=0
if [[ "${2:-}" == "--push" ]]; then
  PUSH=1
fi

cd "$(dirname "$0")/.."

docker buildx version >/dev/null 2>&1 || {
  echo "Install Docker Buildx (included in Docker Desktop)." >&2
  exit 1
}

docker buildx create --name pbsbot-amd64 --driver docker-container --use 2>/dev/null \
  || docker buildx use pbsbot-amd64 2>/dev/null \
  || true

if [[ "$PUSH" -eq 1 ]]; then
  docker buildx build --platform linux/amd64 -t "$TAG" --push .
  echo "Pushed $TAG (linux/amd64). On the VM: docker compose pull && docker compose up -d"
else
  docker buildx build --platform linux/amd64 -t "$TAG" --load .
  echo "Loaded $TAG into local Docker (linux/amd64)."
fi
