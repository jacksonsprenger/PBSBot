# Setting Up a Slack App

The basis for this project is having a functioning Slack App, using the Slack API. These instructions will walk users through setting up their own app.

## 1. Create a new app in Slack

1. Go to **https://api.slack.com/apps**
2. Sign in to your Slack account
3. You should see a screen labelled **Your Apps**
4. Select **Create a New App**
5. You will be prompted to select **From a manifest** or **From scratch**. For the sake of this project, simply select **From scratch**
6. When prompted, add your **App Name** and the Workspace you would like to add it to, then select **Create App**

This will create the basic structure of a Slack App

---

## 2. Turn on Socket Mode

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
7. **Copy the token** (it starts with `xapp-`).
8. In your project, open **`.env`** and replace `replace-with-your-app-token` with this value (no quotes):


**To access your token after the intial stage, do the following:**

1. Go to the **Basic Information** tab
2. Scroll to **App-Level Tokens**.
3. You should see a list of **Tokens**, click on the token you created previouisly
4. A modal will pop up with the token name, who generated, what date is was generated, the scope of the token, and finally the respective `xapp-` token
5. Copy the token

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

*Note: Tokens are intended to be protected, do not make them publicly accessible*

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

## 7. Updating the App Later On

If you ever change any permissions, update tokens, switch modes, or any other change within the Slack App API, follow these steps:

1. Navigate to the **Install App** tab using the lefthand navigation
2. Select **Reinstall to [workspace name]**
3. You will be led to a secondary screen, which will ask you to confirm the Workspace you would like the App updated to and the permissions. Select **Allow**

This step only needs to be repeated if there are changes made to the structure of the App, it doesn't need to be updated when there are changes made to the code.




