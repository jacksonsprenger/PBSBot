# Docker on a VM

Slack **Socket Mode** opens an outbound connection to Slack. The VM needs **egress HTTPS (443)** only.

## Quick start

```bash
cp .env.example .env
# Edit .env: SLACK_BOT_TOKEN, SLACK_APP_TOKEN, AIRTABLE_* (for sync), OLLAMA_* if you use LLM

docker compose up -d --build
docker compose logs -f pbsbot
```

## Chroma index (first deploy or after Airtable changes)

```bash
docker compose run --rm pbsbot python scripts/sync_airtable_to_chroma.py
# Full rebuild:
docker compose run --rm pbsbot python scripts/sync_airtable_to_chroma.py --reset
```

Inside the container, `CHROMA_PERSIST_DIR` is `/app/chroma_db` (set by Compose). Your `.env` may still say `./chroma_db` for local runs; Compose overrides it for the service.

## Ollama

- **Ollama in another container** on the same Compose project: add a service and set `OLLAMA_BASE_URL=http://ollama:11434`.
- **Ollama on the VM host** (listening on `127.0.0.1:11434`): set in `.env`:
  ```env
  OLLAMA_BASE_URL=http://host.docker.internal:11434
  ```
  `docker-compose.yml` maps `host.docker.internal` to the host (Linux `host-gateway`).

Ensure Ollama listens on `0.0.0.0` or the Docker bridge IP if `127.0.0.1` from inside the container cannot reach it; adjust firewall/bind address as needed.

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

Do not copy a laptop `chroma_db/` into the image; it is ignored by `.dockerignore`. Use the named volume and sync on the server.
