# PBSBot

A Slack chatbot for PBS Wisconsin that connects to their Airtable project base. The bot answers questions about projects, tasks, and video promotions using natural language queries over Airtable data.

## Layout (by feature)

| Path | Responsibility |
|------|----------------|
| **`pbsbot/slack/`** | Bolt app, Socket Mode, DM/channel flow, confirmations |
| **`pbsbot/rag/`** | Retrieval routing, Chroma query + answer assembly |
| **`pbsbot/llm/`** | Ollama HTTP client (clarify + synthesize) |
| **`pbsbot/chroma/`** | Persistent Chroma client, reconnect-on-stale |
| **`pbsbot/ingestion/`** | Airtable → Chroma sync, schema explorer |
| **`pbsbot/config.py`** | Environment-backed settings |
| **`tools/`** | SSH tunnel LLM test, Chroma verify script |
| **`deploy/`** | `docker-build-amd64.sh`, `crontab.example` |

Entry points: **`python -m pbsbot`** or **`python main.py`** (shim).

## How to run (in order)

### A. Local machine (venv)

Run these from the **repository root**, in order:

```bash
cd PBSBot
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate / Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```

Edit **`.env`**: `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `AIRTABLE_*`, and Ollama vars if needed. Slack setup: **SETUP.md**. Airtable token: [airtable.com/create/tokens](https://airtable.com/create/tokens) (`data.records:read`, `schema.bases:read`).

**Index Airtable → Chroma** (needed before RAG returns real data):

```bash
python -m pbsbot.ingestion.sync_airtable
```

**Start Ollama** on your machine if you use the default local LLM URL.

**Start the bot:**

```bash
python -m pbsbot
```

Optional — inspect Airtable schema:

```bash
python -m pbsbot.ingestion.explore_schema
```

> **Windows PowerShell:** if activation fails, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` once.

---

### B. Docker — build from this repo (`docker-compose.yml`)

```bash
cd PBSBot
cp .env.example .env
# Edit .env (Slack, Airtable, Ollama as needed)
docker compose up -d --build
docker compose run --rm pbsbot python -m pbsbot.ingestion.sync_airtable
docker compose logs -f pbsbot
```

---

### C. Docker — VM pulls a Hub image (`docker-compose.hub.yml`)

**1. On your dev machine** (use this if the VM is **linux/amd64** and you build on Apple Silicon):

```bash
cd PBSBot
docker login
./deploy/docker-build-amd64.sh YOUR_USER/pbs_bot:latest --push
```

**2. On the VM** (folder must contain `docker-compose.hub.yml` and `.env`):

```bash
cd /path/to/pbsbot
docker compose -f docker-compose.hub.yml pull
docker compose -f docker-compose.hub.yml up -d
docker compose -f docker-compose.hub.yml run --rm pbsbot python -m pbsbot.ingestion.sync_airtable
docker compose -f docker-compose.hub.yml logs -f pbsbot
```

More detail (Ollama from the container, multi-arch, cron): **[docs/DOCKER.md](docs/DOCKER.md)**.

---

## Connecting to the Remote LLM

The **`tools/llm_connect.py`** script connects to a remote LLM over SSH tunnel for local testing.

### Prerequisites

- **UW-Madison VPN** — Must be connected before running. Download at [it.wisc.edu/services/wiscvpn](https://it.wisc.edu/services/wiscvpn/).

### Configure and run

Open `tools/llm_connect.py` and update the config block:
```
ssh capstone@144.92.195.30
```

Then run:
```bash
python tools/llm_connect.py
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `slack-bolt` | Slack Bolt framework for handling events |
| `slack-sdk` | Slack SDK for API interactions |
| `python-dotenv` | Loads environment variables from `.env` |
| `certifi` | SSL certificate fix for macOS |
| `chromadb` | Vector store for RAG pipeline |
| `requests` | HTTP client |
| `paramiko` | SSH tunnel for remote LLM connection |
