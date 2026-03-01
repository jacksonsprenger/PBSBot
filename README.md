# PBSBot

Welcome to the PBSBot Project!

## Run the bot

1. **Create a `.env` file** (copy from `.env.example`):
   ```bash
   cp .env.example .env
   ```
2. **Add your Slack tokens** to `.env`:
   - **SLACK_BOT_TOKEN** (`xoxb-...`): Slack app → **OAuth & Permissions** → Bot User OAuth Token
   - **SLACK_APP_TOKEN** (`xapp-...`): Slack app → **Basic Information** → **App-Level Tokens** (create one with `connections:write`)
   - Turn on **Socket Mode** in the app settings.
3. **Run:**
   ```bash
   venv/bin/python3 main.py
   ```
   or `./run.sh`
