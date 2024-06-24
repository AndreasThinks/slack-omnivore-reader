import os
import json
import httpx
import uuid
import logging
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from fastapi import FastAPI, Request
from collections import deque
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the Slack app
app = AsyncApp(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
)

# Initialize FastAPI app
fastapi_app = FastAPI()
handler = AsyncSlackRequestHandler(app)

# Omnivore API endpoint
OMNIVORE_API_URL = "https://api-prod.omnivore.app/api/graphql"
OMNIVORE_API_KEY = os.environ["OMNIVORE_API_KEY"]

# Store recent events for debugging
recent_events = deque(maxlen=10)

@app.event("reaction_added")
async def handle_reaction(event, say, client):
    logger.info(f"Received reaction_added event: {json.dumps(event, indent=2)}")
    channel_id = event["item"]["channel"]
    message_ts = event["item"]["ts"]
    
    try:
        logger.info(f"Fetching message from channel {channel_id} with timestamp {message_ts}")
        result = await client.conversations_history(
            channel=channel_id,
            latest=message_ts,
            limit=1,
            inclusive=True
        )
        
        # Extract the data from AsyncSlackResponse
        result_data = result.data
        logger.info(f"Conversation history result: {json.dumps(result_data, indent=2)}")
        
        if result_data["messages"]:
            message = result_data["messages"][0]
            logger.info(f"Retrieved message: {json.dumps(message, indent=2)}")
            url = extract_url_from_message(message)
            
            if url:
                logger.info(f"URL extracted: {url}")
                await save_to_omnivore(url)
                await say(f"Saved URL to Omnivore: {url}")
            else:
                logger.warning("No URL found in the message")
        else:
            logger.warning("No message found in the conversation history")
    except Exception as e:
        logger.error(f"Error handling reaction: {str(e)}", exc_info=True)

def extract_url_from_message(message):
    # Check for URLs in the main text
    text = message.get("text", "")
    urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)
    if urls:
        return urls[0]
    
    # Check for URLs in attachments
    attachments = message.get("attachments", [])
    for attachment in attachments:
        attachment_text = attachment.get("text", "")
        attachment_urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', attachment_text)
        if attachment_urls:
            return attachment_urls[0]
    
    # Check for URLs in blocks (for messages with rich layouts)
    blocks = message.get("blocks", [])
    for block in blocks:
        if block["type"] == "section":
            text = block.get("text", {}).get("text", "")
            block_urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)
            if block_urls:
                return block_urls[0]
    
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
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(OMNIVORE_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        logger.info(f"Successfully saved URL to Omnivore: {url}")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error occurred while saving to Omnivore: {e}")
    except Exception as e:
        logger.error(f"An error occurred while saving to Omnivore: {str(e)}", exc_info=True)

@app.event("*")
async def capture_all_events(event):
    recent_events.appendleft(event)

@fastapi_app.post("/slack/events")
async def slack_events(req: Request):
    try:
        body = await req.json()
        logger.info(f"Received Slack event: {json.dumps(body, indent=2)}")
        
        # Handle URL verification
        if body.get("type") == "url_verification":
            return {"challenge": body["challenge"]}
        
        return await handler.handle(req)
    except Exception as e:
        logger.error(f"Error handling Slack event: {str(e)}", exc_info=True)
        return {"error": "An error occurred processing the Slack event"}

@fastapi_app.get("/")
async def health_check():
    logger.info("Health check endpoint accessed")
    return {"status": "healthy"}

@fastapi_app.get("/debug/recent-events")
async def get_recent_events():
    return {"recent_events": list(recent_events)}

@fastapi_app.get("/test-slack-app")
async def test_slack_app():
    if hasattr(app, 'dispatch'):
        return {"status": "Slack app initialized correctly"}
    else:
        return {"status": "Slack app initialization issue", "app_attributes": dir(app)}

# Middleware for request logging
@fastapi_app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Request received: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting FastAPI application")
    uvicorn.run("app:fastapi_app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))