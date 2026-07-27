#!/usr/bin/env sh
# One-time VM bootstrap. Run as the dedicated deployment user after Docker,
# Docker Compose, Git, and curl have been installed by an administrator.
set -eu

repository_url="${1:-https://github.com/thecodepapaya/argus.git}"
deploy_dir="${2:-/opt/argus}"

for command in docker git curl; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Required command is unavailable: $command" >&2
    exit 1
  fi
done

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required." >&2
  exit 1
fi

if [ -d "$deploy_dir/.git" ]; then
  git -C "$deploy_dir" fetch --depth=1 origin main
  git -C "$deploy_dir" checkout main
  git -C "$deploy_dir" merge --ff-only origin/main
else
  git clone --depth=1 --branch main "$repository_url" "$deploy_dir"
fi

if [ ! -f "$deploy_dir/.env" ]; then
  cp "$deploy_dir/.env.production.example" "$deploy_dir/.env"
  chmod 600 "$deploy_dir/.env"
  echo "Created $deploy_dir/.env. Edit it with production secrets, then deploy through GitHub Actions."
else
  echo "$deploy_dir is ready; its existing .env was preserved."
fi
