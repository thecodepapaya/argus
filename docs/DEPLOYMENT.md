# Production deployment

ARGUS deploys to a single Linux VM without putting application credentials in
GitHub or in the repository. A push to `main` first runs the test matrix, then
publishes an immutable container image to GitHub Container Registry (GHCR), and
finally waits for the protected GitHub `production` environment before it uses
SSH to update the VM.

```text
main push → CI tests → GHCR image tagged with commit SHA → production approval
          → SSH to VM → matching source revision + Docker Compose → Caddy/TLS
```

The public web server is Caddy. ARGUS itself binds only to `127.0.0.1:8000`, so
the application port is never exposed directly to the internet. SQLite state is
stored in the persistent Docker volume `argus_data`; deploying a new image does
not remove it.

## 1. Prepare the VM

These instructions assume a current Ubuntu or Debian VM and a DNS name pointed
at its public IP address. Use a small VM initially; the app and scheduler are
lightweight, but source collection depends on outbound internet access.

Install Docker Engine with the Docker Compose v2 plugin using Docker's official
instructions, then install the remaining host tools:

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates caddy
```

Create a dedicated deployment user and directory. Membership in the `docker`
group is privileged access to the host, so protect this account's SSH key as
carefully as a root credential.

```bash
sudo useradd --create-home --shell /bin/bash argusdeploy
sudo usermod -aG docker argusdeploy
sudo install -d -o argusdeploy -g argusdeploy /opt/argus
```

Log in as `argusdeploy` (or start a new login session so its group membership is
refreshed), then bootstrap the checked-out deployment directory:

```bash
git clone --depth=1 --branch main https://github.com/thecodepapaya/argus.git /opt/argus
cd /opt/argus
./scripts/bootstrap_production_vm.sh
```

The bootstrap script creates `/opt/argus/.env` from the production example if
needed and preserves it on later runs. Set restrictive permissions and edit the
actual values:

```bash
chmod 600 /opt/argus/.env
nano /opt/argus/.env
```

Required setting:

| Variable | Purpose |
| --- | --- |
| `ARGUS_ADMIN_TOKEN` | A unique, long random token for the `/admin` API. |

Optional settings:

| Variable | Purpose |
| --- | --- |
| `GITHUB_TOKEN` | Fine-grained, read-only token to reduce GitHub collection rate-limit failures. |
| `OPENROUTER_API_KEY` | Enables the weekly OpenRouter web-search discovery scheduler and draft-profile assistant. Leave empty to disable them. |
| `ARGUS_PUBLIC_URL` | The public HTTPS URL; used as the OpenRouter application referer. |
| `ARGUS_DISCOVERY_*` | Controls discovery model, cadence, and plateau duration. |
| `GHCR_USERNAME`, `GHCR_READ_TOKEN` | Needed only if the container package stays private. |

Do not set `ARGUS_IMAGE` in `.env`: GitHub Actions supplies the exact immutable
image tag for each deploy.

## 2. Configure HTTPS and networking

Replace `argus.example.com` in `infra/caddy/Caddyfile.example` with the real
DNS hostname, then install it:

```bash
sudoedit /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy obtains and renews TLS automatically once DNS is correct and inbound ports
80 and 443 reach the VM. In the cloud firewall/security list and any host
firewall, allow SSH plus TCP 80 and 443. Do **not** allow TCP 8000 publicly;
Compose publishes it only on the loopback interface.

Before changing firewall rules, confirm you have a second SSH session available
so an accidental SSH rule can be corrected without losing access.

## 3. Configure GitHub Actions

In the repository's **Settings → Environments**, create an environment named
`production`. Restrict it to the `main` branch and add a required reviewer if
you want an explicit production approval. Environment protection makes the
deployment job wait before the VM credentials are made available.

Add these **environment secrets** to `production`:

| Secret | Value |
| --- | --- |
| `VM_HOST` | VM public IP address or DNS hostname. |
| `VM_USER` | `argusdeploy`. |
| `VM_SSH_PRIVATE_KEY` | Private key for the deployment-only SSH keypair. |
| `VM_KNOWN_HOSTS` | The exact trusted host-key line from `ssh-keyscan -H YOUR_VM_HOST`, verified out of band. |

Add these **environment variables** (not secrets):

| Variable | Value |
| --- | --- |
| `VM_DEPLOY_PATH` | `/opt/argus` |
| `VM_PORT` | `22` (or your non-default SSH port) |
| `ARGUS_PUBLIC_URL` | `https://your-argus-domain.example` (use the same value in the VM `.env`) |
| `DEPLOY_ENABLED` | Set to `true` only after the VM and secrets above are ready. |

The workflow publishes the GHCR image after tests even while deployment is
disabled. Its SSH job is skipped until `DEPLOY_ENABLED=true`, which lets you
validate image publishing before giving the workflow access to a VM. The
workflow does not use `ssh-keyscan` at deploy time; pinning the verified
host key prevents a first-connection trust-on-use failure. Verify the displayed
fingerprint from your VM provider console before saving `VM_KNOWN_HOSTS`.

The workflow uses the repository `GITHUB_TOKEN` with `packages: write` to push
`ghcr.io/thecodepapaya/argus:<commit-sha>`. After the first successful build,
make that package public in its GitHub Packages settings so the VM can pull it
without a registry credential. If it must stay private, set `GHCR_USERNAME` and
a package-read token in the VM's `.env`; they never pass through the workflow.

## 4. First deploy and verification

Push a commit to `main`, wait for CI, then approve the pending `production`
environment deployment. The workflow fetches the same commit on the VM and
runs:

```bash
ARGUS_IMAGE=ghcr.io/thecodepapaya/argus:COMMIT_SHA ./scripts/deploy_production.sh
```

The script validates Compose configuration, pulls the image, starts services,
and polls `/api/ready`. Verify from the VM and then through the public hostname:

```bash
curl --fail http://127.0.0.1:8000/api/ready
curl --fail https://your-argus-domain.example/api/ready
docker compose --env-file .env -f compose.production.yaml ps
```

## Operations and rollback

Tail service logs on the VM:

```bash
cd /opt/argus
docker compose --env-file .env -f compose.production.yaml logs --follow --tail=100
```

To roll back, select a previously successful commit SHA and redeploy its exact
image after checking out its matching source revision. The fastest controlled
path is to revert the production commit in GitHub and let the workflow deploy
the new revert commit. For an emergency image-only rollback, check out the
matching prior commit first, then run `scripts/deploy_production.sh` with that
prior image tag.

The named Docker volume is the operational database. Back it up using your VM
provider's volume/snapshot mechanism or a scheduled, tested volume backup;
never use `docker compose down -v` in production because it removes the data.

See [the operations runbook](runbooks/OPERATIONS.md) for collection and source
health investigation.
