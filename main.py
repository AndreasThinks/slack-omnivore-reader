import os
import json
import requests
import uuid
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.fastapi import SlackRequestHandler
from fastapi import FastAPI, Request

# Initialize the Slack app
app = AsyncApp(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
)

# Initialize FastAPI app
fastapi_app = FastAPI()
handler = SlackRequestHandler(app)

# Omnivore API endpoint
OMNIVORE_API_URL = "https://api-prod.omnivore.app/api/graphql"
OMNIVORE_API_KEY = os.environ["OMNIVORE_API_KEY"]

@app.event("reaction_added")
async def handle_reaction(event, say, client):
    channel_id = event["item"]["channel"]
    message_ts = event["item"]["ts"]
    
    # Fetch the message that was reacted to
    result = await client.conversations_history(
        channel=channel_id,
        latest=message_ts,
        limit=1,
        inclusive=True
    )
    
    message = result["messages"][0]
    url = extract_url_from_message(message)
    
    if url:
        await save_to_omnivore(url)
        await say(f"Saved URL to Omnivore: {url}")

def extract_url_from_message(message):
    text = message.get("text", "")
    words = text.split()
    for word in words:
        if word.startswith("http://") or word.startswith("https://"):
            return word
    return None

async def save_to_omnivore(url):
    headers = {
        "Content-Type": "application/json",
        "Authorization": OMNIVORE_API_KEY
    }
    
    payload = {
        "query": "mutation SaveUrl($input: SaveUrlInput!) { saveUrl(input: $input) { ... on SaveSuccess { url clientRequestId } ... on SaveError { errorCodes message } } }",
        "variables": {
            "input": {
                "clientRequestId": str(uuid.uuid4()),
                "source": "api",
                "url": url
            }
        }
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(OMNIVORE_API_URL, headers=headers, json=payload)
    # You might want to add error handling here

@fastapi_app.post("/slack/events")
async def slack_events(req: Request):
    return await handler.handle(req)

# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:fastapi_app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))