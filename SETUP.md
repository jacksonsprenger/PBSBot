# How to get your Slack tokens for PBS Bot

Your app needs two tokens. Get them from the Slack API dashboard for **PBS_BOT**.

---

## 1. Open your app in Slack

1. Go to **https://api.slack.com/apps**
2. Sign in if needed.
3. Click your app **PBS_BOT** (the one you use in the "620 Capstone" workspace).

---

## 2. Turn on Socket Mode (required)

1. In the left sidebar, click **Socket Mode**.
2. Turn **Enable Socket Mode** **On**.
3. When asked for an App-Level Token, you can create it in the next step and come back, or create it now (see step 3).

---

## 3. Get SLACK_APP_TOKEN (starts with `xapp-`)

1. In the left sidebar, click **Basic Information**.
2. Scroll to **App-Level Tokens**.
3. Click **Generate Token and Scopes**.
4. Name it (e.g. `socket-mode`).
5. Add scope: **`connections:write`**.
6. Click **Generate**.
7. **Copy the token** (it starts with `xapp-`). You won’t see it again.
8. In your project, open **`.env`** and replace `replace-with-your-app-token` with this value (no quotes):

   ```
   SLACK_APP_TOKEN=xapp-1-...
   ```

---

## 4. Get SLACK_BOT_TOKEN (starts with `xoxb-`)

1. In the left sidebar, click **OAuth & Permissions**.
2. Under **OAuth Tokens for Your Workspace**, find **Bot User OAuth Token**.
3. Click **Copy** (or show and copy). It starts with `xoxb-`.
4. In **`.env`**, replace `replace-with-your-bot-token` with this value (no quotes):

   ```
   SLACK_BOT_TOKEN=xoxb-...
   ```

---

## 5. Bot and app permissions (if the bot can’t read/send messages)

Under **OAuth & Permissions** → **Scopes** → **Bot Token Scopes**, ensure you have at least:

- **`app_mentions:read`** – read when someone @mentions the bot  
- **`chat:write`** – send messages  
- **`im:history`** – read DM history  
- **`im:read`** – view DMs  
- **`im:write`** – send DMs  

If any are missing, add them, then go to **OAuth & Permissions** and **Reinstall to Workspace** so the new scopes apply.

---

## 6. Your `.env` when done

`.env` should look like this (with your real tokens, no quotes):

```
SLACK_BOT_TOKEN=xoxb-1234-5678-...
SLACK_APP_TOKEN=xapp-1-1234-5678-...
```

Save the file, then run:

```bash
.venv/bin/python3 -m pbsbot
```

or

```bash
./run.sh
```

You should see **🤖 PBS Bot is running!** and the bot will reply in Slack when you DM it or mention it.
