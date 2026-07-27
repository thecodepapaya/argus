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
use_sudo=false
if ! docker info >/dev/null 2>&1; then
  if sudo -n docker info >/dev/null 2>&1; then
    use_sudo=true
  else
    echo "Docker is unavailable to this account (directly or through passwordless sudo)." >&2
    exit 1
  fi
fi

run_docker() {
  if [ "$use_sudo" = true ]; then
    # sudo intentionally sanitizes the caller environment. Pass only the
    # immutable image reference required for Compose interpolation.
    sudo -n env ARGUS_IMAGE="$ARGUS_IMAGE" docker "$@"
  else
    docker "$@"
  fi
}

run_docker compose --env-file .env -f "$compose_file" config --quiet
run_docker compose --env-file .env -f "$compose_file" pull
run_docker compose --env-file .env -f "$compose_file" up --detach --remove-orphans
http_endpoint="$(run_docker compose --env-file .env -f "$compose_file" port argus 8000 | sed -n '1p')"

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
run_docker compose --env-file .env -f "$compose_file" logs --tail=100 >&2
exit 1
