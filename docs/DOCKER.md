# Docker on a VM

Slack **Socket Mode** opens an outbound connection to Slack. The VM needs **egress HTTPS (443)** only.

## Apple Silicon Mac → AMD64 VM (`exec format error`)

Images built on a Mac (arm64) **will not run** on typical cloud/VM CPUs (amd64). Rebuild for Intel/AMD:

```bash
./scripts/docker-build-amd64.sh thugken/pbs_bot:latest --push
```

Then on the VM: `docker compose -f docker-compose.hub.yml pull && docker compose -f docker-compose.hub.yml up -d`

## Quick start

```bash
cp .env.example .env
# Edit .env: SLACK_BOT_TOKEN, SLACK_APP_TOKEN, AIRTABLE_* (for sync)

docker compose up -d --build
docker compose logs -f pbsbot
```

**Hub image on VM:** put `.env` next to `docker-compose.hub.yml`, then:

```bash
docker compose -f docker-compose.hub.yml pull
docker compose -f docker-compose.hub.yml up -d
```

## Chroma index (first deploy or after Airtable changes)

```bash
docker compose run --rm pbsbot python scripts/sync_airtable_to_chroma.py
# Full rebuild:
docker compose run --rm pbsbot python scripts/sync_airtable_to_chroma.py --reset
```

While the bot is running, sync updates the same volume; `main.py` will reopen Chroma once if a query hits a stale index. You can still `docker compose restart pbsbot` after a large `--reset` sync if anything looks off.

Inside the container, `CHROMA_PERSIST_DIR` is `/app/chroma_db` (set by Compose). Your `.env` may still say `./chroma_db` for local runs; Compose overrides it for the service.

## Ollama (local on the VM, not “external” SaaS)

Compose and `main.py` default to **`http://host.docker.internal:11434`** when `OLLAMA_BASE_URL` is unset (Docker) so the bot reaches Ollama on the **VM host**.

On the **host**, if Ollama only listens on `127.0.0.1`, Docker may not reach it. Prefer:

```bash
export OLLAMA_HOST=0.0.0.0
# or in systemd / service env for ollama
```

Then `ollama serve` (or restart the service) so it accepts traffic from the Docker bridge.

- **Ollama in another Compose service:** set `OLLAMA_BASE_URL=http://ollama:11434` in `.env`.

## Cron sync (host)

```cron
0 6 * * * cd /path/to/PBSBot && docker compose run --rm pbsbot python scripts/sync_airtable_to_chroma.py >> /var/log/pbsbot-sync.log 2>&1
```

## Troubleshooting

| Issue | Check |
|--------|--------|
| Bot not connecting | Tokens, outbound internet, `docker compose logs pbsbot` |
| Empty RAG | Run sync; logs may warn that the collection is empty |
| LLM errors | `OLLAMA_BASE_URL` reachable from the container; model pulled on Ollama host |
| `exec format error` | Image is wrong CPU arch; build/push `linux/amd64` (see above) |

Do not copy a laptop `chroma_db/` into the image; it is ignored by `.dockerignore`. Use the named volume and sync on the server.
