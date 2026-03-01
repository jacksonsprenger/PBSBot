import ssl
import certifi
import os

# SSL fix for Mac
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
ssl._create_default_https_context = ssl.create_default_context

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

load_dotenv()

app = App(token=os.getenv("SLACK_BOT_TOKEN"))

@app.event("app_mention")
def handle_mention(event, say):
    user = event["user"]
    say(f"<@{user}> Hey! How can I help you?")

@app.event("message")
def handle_dm(message, say):
    # Ignore bot messages and subtypes
    if message.get("bot_id") or message.get("subtype"):
        return
    # Only handle DMs
    if message.get("channel_type") == "im":
        user = message.get("user")
        text = message.get("text", "")
        say(f"<@{user}> Got your message: {text}")

if __name__ == "__main__":
    handler = SocketModeHandler(
        app,
        os.getenv("SLACK_APP_TOKEN")
    )
    print("🤖 PBS Bot is running!")
    handler.start()