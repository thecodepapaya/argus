# Production deployment

ARGUS deploys to one Linux VM with Docker Compose, Caddy, GitHub Container Registry (GHCR), and a protected GitHub Actions environment.

```text
main → CI tests → immutable GHCR image → production approval → VM deploy → Caddy/TLS
```

The application binds to `127.0.0.1:8000`; Caddy is the only public entry point. Operational SQLite state lives in the `argus_data` Docker volume and survives image updates.

## VM prerequisites

- Docker Engine with the Docker Compose v2 plugin
- Git, curl, and Caddy
- A dedicated deployment account with Docker access
- DNS pointing the public hostname to the VM
- Inbound TCP 80 and 443; SSH access; no public TCP 8000 rule

Ubuntu/Debian host packages:

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates caddy
sudo useradd --create-home --shell /bin/bash argusdeploy
sudo usermod -aG docker argusdeploy
sudo install -d -o argusdeploy -g argusdeploy /opt/argus
```

`docker` group membership provides privileged host access. The deployment account and its SSH key require the same protection as an administrative account.

## Bootstrap

```bash
git clone --depth=1 --branch main https://github.com/thecodepapaya/argus.git /opt/argus
cd /opt/argus
./scripts/bootstrap_production_vm.sh
chmod 600 .env
```

`bootstrap_production_vm.sh` creates `.env` from `.env.production.example` when absent and never replaces an existing `.env`.

| Variable | Required | Purpose |
| --- | --- | --- |
| `ARGUS_ADMIN_TOKEN` | Yes | Admin API token. |
| `ARGUS_PUBLIC_URL` | Yes | Public HTTPS URL; also supplied to OpenRouter as the application referer. |
| `OPENROUTER_API_KEY` | No | Discovery and admin draft-profile assistance. |
| `GITHUB_TOKEN` | No | Fine-grained read-only token for source collection. |
| `GHCR_USERNAME`, `GHCR_READ_TOKEN` | Private package only | Registry pull credential. |

`ARGUS_IMAGE` is supplied by the deployment workflow and must not be present in `.env`.

## Caddy

Replace the example hostname in `infra/caddy/Caddyfile.example`, then install the resulting configuration as `/etc/caddy/Caddyfile` and reload Caddy:

```bash
sudo cp infra/caddy/Caddyfile.example /etc/caddy/Caddyfile
sudoedit /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

With DNS and ports 80/443 in place, Caddy provisions and renews TLS certificates.

## GitHub Actions environment

The workflow in `.github/workflows/ci.yml` publishes `ghcr.io/thecodepapaya/argus:<commit-sha>` after the test matrix completes. It deploys successful pushes to `main` and can also be started manually. The deployment job runs only when the repository variable `DEPLOY_ENABLED` is `true`.

Environment secrets:

| Secret | Value |
| --- | --- |
| `VM_HOST` | VM hostname or IP address |
| `VM_USER` | `ubuntu` on the current VM, or a dedicated deployment account |
| `VM_SSH_PRIVATE_KEY` | Deployment-only private key |
| `VM_KNOWN_HOSTS` | Verified, hashed host-key entry |

Environment variables:

| Variable | Value |
| --- | --- |
| `VM_DEPLOY_PATH` | `/opt/argus` |
| `VM_PORT` | `22` or the configured SSH port |
| `ARGUS_PUBLIC_URL` | Public HTTPS URL |

Set `DEPLOY_ENABLED=true` as a repository variable after VM setup is complete. It is repository-scoped because GitHub evaluates the deployment job condition before loading its `production` environment.

The workflow pins host-key verification, restores full Git history if the VM checkout is shallow, and deploys the same source revision as the immutable image tag. A public GHCR package pulls anonymously. Private packages use the optional VM-only registry credentials.

## Health and operations

```bash
curl --fail http://127.0.0.1:8000/api/ready
curl --fail https://argus.example.com/api/ready
docker compose --env-file .env -f compose.production.yaml ps
docker compose --env-file .env -f compose.production.yaml logs --follow --tail=100
```

`docker compose down -v` removes the production database volume and is not an operational command. Backups belong to the VM provider's snapshot or volume-backup process. Reverting a deployment commit triggers a deployment of the corresponding immutable image.
