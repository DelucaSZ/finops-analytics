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
docker compose pull --ignore-buildable
docker compose build --pull
docker compose up -d
docker compose ps
