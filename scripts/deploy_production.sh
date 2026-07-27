#!/usr/bin/env sh
# Deploy one immutable ARGUS image on a prepared VM. This script intentionally
# reads application secrets only from the VM's .env file, never from GitHub.
set -eu

: "${ARGUS_IMAGE:?ARGUS_IMAGE must name an immutable container image tag}"

compose_file="${ARGUS_COMPOSE_FILE:-compose.production.yaml}"

if [ ! -f "$compose_file" ]; then
  echo "Missing $compose_file. Run this from the ARGUS deployment directory." >&2
  exit 1
fi

if [ ! -f .env ]; then
  echo "Missing .env. Copy .env.production.example to .env and configure it first." >&2
  exit 1
fi

# A public GHCR image is pulled anonymously. These optional variables support a
# private package without sending its read token through the GitHub workflow.
if [ -n "${GHCR_READ_TOKEN:-}" ]; then
  : "${GHCR_USERNAME:?GHCR_USERNAME is required with GHCR_READ_TOKEN}"
  printf '%s' "$GHCR_READ_TOKEN" | docker login ghcr.io --username "$GHCR_USERNAME" --password-stdin
fi

export ARGUS_IMAGE

# Production hosts commonly restrict the Docker socket to root. Prefer direct
# access when available, otherwise use the host's existing passwordless sudo
# policy instead of granting the deployment account permanent docker-group
# membership (which is effectively root access).
docker_command="docker"
if ! docker info >/dev/null 2>&1; then
  if sudo -n docker info >/dev/null 2>&1; then
    docker_command="sudo -n docker"
  else
    echo "Docker is unavailable to this account (directly or through passwordless sudo)." >&2
    exit 1
  fi
fi

# Intentional word splitting lets docker_command include the sudo arguments.
# shellcheck disable=SC2086
$docker_command compose --env-file .env -f "$compose_file" config --quiet
# shellcheck disable=SC2086
$docker_command compose --env-file .env -f "$compose_file" pull
# shellcheck disable=SC2086
$docker_command compose --env-file .env -f "$compose_file" up --detach --remove-orphans
# shellcheck disable=SC2086
http_endpoint="$($docker_command compose --env-file .env -f "$compose_file" port argus 8000 | sed -n '1p')"

if [ -z "$http_endpoint" ]; then
  echo "Could not determine the published ARGUS application port." >&2
  exit 1
fi

attempt=1
while [ "$attempt" -le 30 ]; do
  if curl --fail --silent --show-error "http://${http_endpoint}/api/ready" >/dev/null; then
    echo "ARGUS is ready with ${ARGUS_IMAGE}"
    exit 0
  fi
  sleep 2
  attempt=$((attempt + 1))
done

echo "ARGUS did not become ready; recent container logs follow:" >&2
# shellcheck disable=SC2086
$docker_command compose --env-file .env -f "$compose_file" logs --tail=100 >&2
exit 1
