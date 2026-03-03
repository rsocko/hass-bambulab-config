#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "Missing .env. Copy .env.example to .env and set ACCESS_TOKEN first."
  exit 1
fi

docker compose pull
docker compose up -d

echo "Runner stack deployed. Check GitHub repo Settings -> Actions -> Runners."
