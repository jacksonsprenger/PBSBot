# PBSBot

A Slack chatbot for PBS Wisconsin that connects to their Airtable project base. The bot answers questions about projects, tasks, staff, contacts, and video promotions using natural language queries over Airtable data.

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

## For Slack App setup steps, see `SETUP.md`

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

Edit **`.env`**: `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`, the route-specific Airtable table IDs, and Ollama vars if needed.

Required Airtable table IDs:

```env
AIRTABLE_PROJECTS_TABLE_ID=tbl...
AIRTABLE_TASKS_TABLE_ID=tbl...
AIRTABLE_STAFF_TABLE_ID=tbl...
AIRTABLE_CONTACTS_TABLE_ID=tbl...
```

Slack setup: **SETUP.md**. Airtable token: [airtable.com/create/tokens](https://airtable.com/create/tokens) (`data.records:read`, `schema.bases:read`).

**Index Airtable → Chroma** (needed before RAG returns real data):

```bash
python -m pbsbot.ingestion.sync_airtable --reset --all-tables
```

For later updates without clearing the collection:

```bash
python -m pbsbot.ingestion.sync_airtable --all-tables
```

To answer across projects, tasks, contacts, and staff, index every Airtable table:

```bash
python -m pbsbot.ingestion.sync_airtable --reset --all-tables
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
docker compose run --rm pbsbot python -m pbsbot.ingestion.sync_airtable --reset --all-tables
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
docker compose -f docker-compose.hub.yml run --rm pbsbot python -m pbsbot.ingestion.sync_airtable --reset --all-tables
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

```bash
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

## Next Steps

With more time, our next step for this project would be improving the RAG pipeline and response quality for the four supported question categories: project information, staff and roles, tasks and deadlines, and contacts and partners.

The current system uses route-based retrieval to select the relevant Airtable table before querying ChromaDB. This improves over a single-table retrieval flow, but there is still room to improve how nested Airtable data is represented. Some linked records can still appear as record IDs instead of fully readable names or details, especially when information is stored across related tables. A future version could expand the ingestion step to resolve linked records before indexing them.

Another area for future work is stronger guardrails to ensure that data returned by the LLM is accurate to what is in Airtable. From our testing, most information appeared to be accurate or produced the expected fail statement, but different phrasings of questions could still produce different results. This would likely require improving the retrieval logic, prompt structure, and ChromaDB indexing strategy so user intent is consistently interpreted into the correct route and table lookup.

A recommendation for future versions of this project would be to test the system with more Airtable data. One issue we ran into during our testing was that some entries had been removed or edited to protect privacy. This limited our ability to test edge cases, such as asking who the director or producer was for certain projects when that information was not included in our version of the database.