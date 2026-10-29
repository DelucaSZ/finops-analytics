#!/usr/bin/env bash
set -euo pipefail

project_dir="${1:-/opt/nuvemiq}"

if [[ ! -f "${project_dir}/compose.yaml" ]]; then
  echo "compose.yaml not found in ${project_dir}" >&2
  exit 1
fi

if [[ ! -f "${project_dir}/.env" ]]; then
  echo "Create ${project_dir}/.env from .env.example before deploying." >&2
  exit 1
fi

cd "${project_dir}"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Tracked local changes detected; commit or stash them before deploying." >&2
  exit 1
fi

git pull --ff-only

build_sha="$(git rev-parse --short=12 HEAD)"
export NEXT_PUBLIC_BUILD_SHA="${build_sha}"

echo "Building release ${build_sha}. Existing containers remain untouched until every image builds successfully."
docker compose pull --ignore-buildable
docker compose build --pull --no-cache

echo "Build completed for ${build_sha}; recreating containers."
docker compose up -d --force-recreate --remove-orphans
docker compose ps

running_sha="$(docker compose exec -T web printenv NEXT_PUBLIC_BUILD_SHA)"
if [[ "${running_sha}" != "${build_sha}" ]]; then
  echo "Web build SHA mismatch: expected ${build_sha}, running ${running_sha:-unset}." >&2
  exit 1
fi

echo "Deploy complete. Web build SHA: ${running_sha}"
