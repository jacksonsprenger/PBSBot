import ssl
import certifi

# SSL fix - 반드시 다른 import보다 먼저!
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

load_dotenv()

app = App(token=os.getenv("SLACK_BOT_TOKEN"))

@app.event("app_mention")
def handle_mention(event, say):
    user = event["user"]
    say(f"<@{user}> 안녕! 뭘 도와줄까?")

@app.event("message")
def handle_dm(message, say):
    if message.get("bot_id"):
        return
    say("DM 받았어!")

if __name__ == "__main__":
    handler = SocketModeHandler(
        app,
        os.getenv("SLACK_APP_TOKEN")
    )
    print("🤖 PBS Bot is running!")
    handler.start()