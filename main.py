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

import chromadb
from chromadb.utils import embedding_functions

from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient

# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()

app = App(token=os.getenv("SLACK_BOT_TOKEN"))

# -----------------------------
# Connect to ChromaDB
# -----------------------------
print("Connecting to ChromaDB...")

client = chromadb.PersistentClient(path="./chroma_db")

embedding_function = embedding_functions.DefaultEmbeddingFunction()

projects_collection = client.get_collection(
    name="pbs_projects",
    embedding_function=embedding_function
)

print("ChromaDB connected.")


# # -----------------------------
# # Content Routing
# # -----------------------------
def route_query(query: str) -> str:
     q = query.lower()

     if "task" in q:
         return "tasks"

     if "contact" in q or "email" in q or "phone" in q:
         return "contacts"

     if "staff" in q or "who is" in q:
         return "staff"

     return "projects"


# # -----------------------------
# # Retrieval from ChromaDB
# # -----------------------------
def search_projects(query: str) -> str:

     results = projects_collection.query(
         query_texts=[query],
         n_results=2
     )

     docs = results.get("documents", [[]])[0]

     if not docs:
         return "I couldn't find anything related to that project."

     return docs[0]


# -----------------------------
# Slack Event Handlers
# -----------------------------
@app.event("app_mention")
def handle_mention(event, say):
    user = event["user"]
    text = event.get("text", "")

    route = route_query(text)

    if route == "projects":
        answer = search_projects(text)
    else:
        answer = "That data type isn't indexed yet."

    say(f"<@{user}>\n{answer}")


@app.event("message")
def handle_dm(message, say):
    # Ignore bot messages and subtypes
    if message.get("bot_id") or message.get("subtype"):
        return

    # Only handle DMs
    if message.get("channel_type") == "im":

        user = message.get("user")
        text = message.get("text", "")

        route = route_query(text)

        if route == "projects":
            answer = search_projects(text)
        else:
            answer = "Right now I can answer questions about projects."

        say(f"<@{user}>\n{answer}")

@app.event("app_home_opened")
def publish_home_tab(user_id):
    print(f"Testing Home tab")
    try:
        app.client.views_publish(
            user_id=user_id,
            view={
                "type": "home",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Welcome home, <@{user_id}>! :house:*"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "Learn how home tabs can be more useful and interactive in the [documentation](https://docs.slack.dev/surfaces/app-home)."
                        }
                    }
                ]
            }
        )
        print(f"Home tab published for user {user_id}")
    except Exception as e:
        print(f"Error publishing home tab: {e}")

# -----------------------------
# Start Slack Bot
# -----------------------------
if __name__ == "__main__":
    handler = SocketModeHandler(
        app,
        os.getenv("SLACK_APP_TOKEN")
    )
    print("🤖 PBS Bot is running!")
    handler.start()

    test_user_id = "U0AJPLXNA4B"
    publish_home_tab(test_user_id)