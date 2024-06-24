import os
import json
import httpx
import uuid
import logging
import html
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from collections import deque
import re
from urllib.parse import urlparse
from limits import parse_many
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter
from dotenv import load_dotenv

load_dotenv()

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost").split(",")

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

# Add secure HTTP headers
fastapi_app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
fastapi_app.add_middleware(HTTPSRedirectMiddleware)


# Set up rate limiting
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", 20))
RATE_LIMIT = f"{RATE_LIMIT_PER_MINUTE}/minute"
limiter = MovingWindowRateLimiter(MemoryStorage())
rate_limits = parse_many(RATE_LIMIT)

OMNIVORE_API_URL = "https://api-prod.omnivore.app/api/graphql"
OMNIVORE_API_KEY = os.environ["OMNIVORE_API_KEY"]

# Get the label from an environment variable
OMNIVORE_LABEL = os.environ.get("OMNIVORE_LABEL", "slack-import")

# Store recent events for debugging
recent_events = deque(maxlen=10)

def escape_user_input(input_string):
    return html.escape(input_string)

@app.event("reaction_added")
async def handle_reaction(event, say, client):
    logger.info(f"Received reaction_added event: {escape_user_input(json.dumps(event, indent=2))}")
    channel_id = event["item"]["channel"]
    message_ts = event["item"]["ts"]
    
    try:
        logger.info(f"Fetching message from channel {escape_user_input(channel_id)} with timestamp {escape_user_input(message_ts)}")
        result = await client.conversations_history(
            channel=channel_id,
            latest=message_ts,
            limit=1,
            inclusive=True
        )
        
        result_data = result.data if isinstance(result.data, dict) else {}
        logger.info(f"Conversation history result: {escape_user_input(json.dumps(result_data, indent=2))}")
        
        if result_data.get("messages"):
            message = result_data["messages"][0]
            logger.info(f"Retrieved message: {escape_user_input(json.dumps(message, indent=2))}")
            url = extract_and_validate_url(message)
            
            if url:
                logger.info(f"URL extracted: {escape_user_input(url)}")
                result = await save_to_omnivore(url)
                if result and "data" in result and isinstance(result["data"], dict) and "saveUrl" in result["data"]:
                    saved_url = result["data"]["saveUrl"].get("url")
                    saved_url = saved_url.rstrip('/') if saved_url else saved_url
                    if saved_url and saved_url.endswith('/'):
                        saved_url = saved_url[:-1]
                    if saved_url:
                        reply_text = f"Saved URL to Omnivore with label '{escape_user_input(OMNIVORE_LABEL)}': {escape_user_input(saved_url)}"
                        await client.chat_postMessage(
                            channel=channel_id,
                            text=reply_text,
                            thread_ts=message_ts
                        )
                    else:
                        logger.warning("Attempted to save URL to Omnivore, but encountered an issue.")
                else:
                    logger.error("Failed to save URL to Omnivore. Please check the logs for more information.")
            else:
                logger.info("No URL found in the message. Remaining silent.")
        else:
            logger.warning("No message found in the conversation history")
    except Exception as e:
        logger.error(f"Error handling reaction: {str(e)}", exc_info=True)



def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def sanitize_url(url):
    # Remove any whitespace and quotes
    sanitized = url.strip().strip('"\'')
    # Ensure the URL starts with http:// or https://
    if not sanitized.startswith(('http://', 'https://')):
        sanitized = 'http://' + sanitized
    return sanitized

def extract_and_validate_url(message):
    url = extract_url_from_message(message)
    if url and is_valid_url(url):
        return sanitize_url(url)
    return None

def extract_url_from_message(message):
    text = message.get("text", "")
    urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)
    if urls:
        return urls[0]
    
    attachments = message.get("attachments", [])
    if isinstance(attachments, list):
        for attachment in attachments:
            attachment_text = attachment.get("text", "")
            attachment_urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', attachment_text)
            if attachment_urls:
                return attachment_urls[0]
    
    blocks = message.get("blocks", [])
    if isinstance(blocks, list):
        for block in blocks:
            if block.get("type") == "section":
                text = block.get("text", {}).get("text", "")
                block_urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)
                if block_urls:
                    return block_urls[0]
    
    return None



async def save_to_omnivore(url):
    url = url.rstrip('>') if url else url

    headers = {
        "Content-Type": "application/json",
        "Authorization": OMNIVORE_API_KEY
    }
    
    label = os.environ.get("OMNIVORE_LABEL", "SlackSaved")
    
    payload = {
        "query": """
        mutation SaveUrl($input: SaveUrlInput!) {
            saveUrl(input: $input) {
                ... on SaveSuccess {
                    url
                    clientRequestId
                }
                ... on SaveError {
                    errorCodes
                    message
                }
            }
        }
        """,
        "variables": {
            "input": {
                "clientRequestId": str(uuid.uuid4()),
                "source": "api",
                "url": url,
                "labels": [{"name": label}]
            }
        }
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(OMNIVORE_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        logger.info(f"Successfully saved URL to Omnivore: {url} with label: {label}")
        logger.debug(f"Omnivore API response: {json.dumps(result, indent=2)}")
        
        if "data" in result and isinstance(result["data"], dict):
            return result
        else:
            logger.error("Unexpected response format from Omnivore API")
            return None
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error occurred while saving to Omnivore: {e}")
        raise
    except Exception as e:
        logger.error(f"An error occurred while saving to Omnivore: {str(e)}", exc_info=True)
        raise


@app.event("*")
async def capture_all_events(event):
    recent_events.appendleft(event)

# Then, in your slack_events function:
@fastapi_app.post("/slack/events")
async def slack_events(req: Request):
    try:
        # Check rate limits
        for rate_limit in rate_limits:
            if not limiter.hit(rate_limit, "global", *req.client.host):
                logger.warning("Rate limit exceeded")
                raise HTTPException(status_code=429, detail="Too many requests")
        
        body = await req.json()
        logger.info(f"Received Slack event: {escape_user_input(json.dumps(body, indent=2))}")
        
        # Handle URL verification
        if body.get("type") == "url_verification":
            return {"challenge": body["challenge"]}
        
        return await handler.handle(req)
    except Exception as e:
        logger.error(f"Error handling Slack event: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An error occurred processing the Slack event")

@fastapi_app.get("/")
async def health_check():
    logger.info("Health check endpoint accessed")
    return {"status": "healthy"}

@fastapi_app.get("/debug/recent-events")
async def get_recent_events():
    return {"recent_events": [escape_user_input(json.dumps(event)) for event in list(recent_events)]}

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

# Error handling middleware
@fastapi_app.middleware("http")
async def errors_handling(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        logger.error(f"An error occurred: {str(exc)}", exc_info=True)
        return JSONResponse(status_code=500, content={"message": "An internal error occurred"})

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting FastAPI application")
    uvicorn.run("app:fastapi_app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))