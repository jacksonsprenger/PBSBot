# PBSBot

A Slack chatbot for PBS Wisconsin that connects to their Airtable project base. The bot can answer questions about projects, tasks, and video promotions using data from Airtable.

## What's in this repo

- **main.py** — Slack bot (Socket Mode). Responds to @mentions and DMs. You’ll add RAG/Airtable answers here later.
- **explore_schema.py** — Script to explore the Airtable base: lists tables, fields, and sample records. Useful for demos and to confirm the API works.
- **requirements.txt** — Python dependencies.

## Quick start

1. **Clone and go into the project**
   ```bash
   cd PBSBot
   ```

2. **Create a virtual environment and install dependencies**
   ```bash
   python3 -m venv 
   venv/bin/pip install -r requirements.txt
   ```

3. **Add your `.env` file** in the project root with:
   - `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` (for the Slack app — see SETUP.md).
   - `AIRTABLE_API_KEY` and `AIRTABLE_BASE_ID` (for Airtable — create a token at [airtable.com/create/tokens](https://airtable.com/create/tokens) and use your base ID from the URL).
   - `OPENAI_API_KEY` (for question clarification before retrieval).
   - Optional: `OPENAI_MODEL` (defaults to `gpt-4o-mini`).

4. **Run the Slack bot**
   ```bash
   venv/bin/python3 main.py
   ```
   Or use `./run.sh` if you prefer.

5. **Explore Airtable (optional)**  
   To list tables and sample data from the base:
   ```bash
   venv/bin/python3 explore_schema.py
   ```

## More help

- **Slack setup** — See **SETUP.md** for step-by-step Slack app and token setup.
- **Airtable** — Base ID is in the base URL (`appXXXX...`). Create a personal access token with `data.records:read` and `schema.bases:read`, and give it access to your base.
