# PBSBot

A Slack chatbot for PBS Wisconsin that connects to their Airtable project base. The bot answers questions about projects, tasks, and video promotions using natural language queries over Airtable data.

## What's in this repo

- **main.py** — Slack bot (Socket Mode). Responds to @mentions and DMs.
- **explore_schema.py** — Explores the Airtable base: lists tables, fields, and sample records. Useful for confirming the API works.
- **scripts/llm_connect.py** — CLI script for testing the remote LLM over SSH tunnel (requires UW-Madison VPN).
- **requirements.txt** — Python dependencies.

## Quick Start

### 1. Create a virtual environment and install dependencies

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (Command Prompt):**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> **Note for Windows PowerShell users:** If you get an execution policy error, run this first:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### 2. Add your `.env` file

Create a `.env` file in the project root with the following variables:
```
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
AIRTABLE_API_KEY=pat...
AIRTABLE_BASE_ID=app...
```

- Slack tokens: see **SETUP.md** for step-by-step instructions.
- Airtable token: create a personal access token at [airtable.com/create/tokens](https://airtable.com/create/tokens) with `data.records:read` and `schema.bases:read` scopes. Your base ID is in the base URL (`appXXXX...`).

### 3. Run the bot
```bash
python main.py
```

### 4. Explore Airtable schema (optional)
```bash
python explore_schema.py
```

---

## Docker (VM)

```bash
cp .env.example .env
docker compose up -d --build
docker compose run --rm pbsbot python scripts/sync_airtable_to_chroma.py
```

**Docker Hub on an AMD64 VM:** build with `./scripts/docker-build-amd64.sh thugken/pbs_bot:latest --push`, then on the VM use `docker compose -f docker-compose.hub.yml up -d` (see **docs/DOCKER.md**).

Details: **[docs/DOCKER.md](docs/DOCKER.md)** (Ollama on the host, `exec format error` / multi-arch, cron).

---

## Connecting to the Remote LLM

The `scripts/llm_connect.py` script connects to a remote LLM over SSH tunnel for local testing.

### Prerequisites

- **UW-Madison VPN** — Must be connected before running. Download at [it.wisc.edu/services/wiscvpn](https://it.wisc.edu/services/wiscvpn/).

### Configure and run

Open `scripts/llm_connect.py` and update the config block:
```python
SSH_HOST = "144.92.195.30"
SSH_USER = "capstone"
MODEL    = "llama3.1:8b"
```

Then run:
```bash
python scripts/llm_connect.py
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