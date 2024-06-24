import os
import httpx
import uuid
import logging
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.fastapi import SlackRequestHandler
from fastapi import FastAPI, Request

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
handler = SlackRequestHandler(app)

# Omnivore API endpoint
OMNIVORE_API_URL = "https://api-prod.omnivore.app/api/graphql"
OMNIVORE_API_KEY = os.environ["OMNIVORE_API_KEY"]

@app.event("reaction_added")
async def handle_reaction(event, say, client):
    logger.info(f"Reaction added event received: {event}")
    channel_id = event["item"]["channel"]
    message_ts = event["item"]["ts"]
    
    try:
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
            logger.info(f"URL extracted: {url}")
            await save_to_omnivore(url)
            await say(f"Saved URL to Omnivore: {url}")
        else:
            logger.warning("No URL found in the message")
    except Exception as e:
        logger.error(f"Error handling reaction: {str(e)}", exc_info=True)

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
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(OMNIVORE_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        logger.info(f"Successfully saved URL to Omnivore: {url}")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error occurred while saving to Omnivore: {e}")
    except Exception as e:
        logger.error(f"An error occurred while saving to Omnivore: {str(e)}", exc_info=True)

@fastapi_app.post("/slack/events")
async def slack_events(req: Request):
    logger.info("Received Slack event")
    try:
        return await handler.handle(req)
    except Exception as e:
        logger.error(f"Error handling Slack event: {str(e)}", exc_info=True)
        raise

@fastapi_app.get("/")
async def health_check():
    logger.info("Health check endpoint accessed")
    return {"status": "healthy"}

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