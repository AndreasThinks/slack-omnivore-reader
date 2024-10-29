import logging
from slack_bolt.async_app import AsyncApp
from config import settings
import requests
from utils import extract_and_validate_url, get_trigger_emojis
from functools import wraps
import time

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class EventDeduplicator:
    def __init__(self):
        self.processed_events = {}

    def deduplicate(self, ttl=60):
        def decorator(func):
            @wraps(func)
            async def wrapper(event, say, client):
                event_key = f"{event['event_ts']}:{event['item']['channel']}:{event['item']['ts']}"
                current_time = time.time()

                if event_key in self.processed_events:
                    if current_time - self.processed_events[event_key] < ttl:
                        logger.info(f"Duplicate event detected, skipping: {event_key}")
                        return

                self.processed_events[event_key] = current_time
                self.processed_events = {k: v for k, v in self.processed_events.items() if current_time - v < ttl}

                return await func(event, say, client)
            return wrapper
        return decorator

app = AsyncApp(
    token=settings.SLACK_BOT_TOKEN,
    signing_secret=settings.SLACK_SIGNING_SECRET
)
trigger_emojis = get_trigger_emojis()
deduplicator = EventDeduplicator()

async def save_url_to_readwise(url: str) -> bool:
    """Save a URL to Readwise Reader with the configured tag."""
    try:
        response = requests.post(
            "https://readwise.io/api/v3/save/",
            headers={
                "Authorization": f"Token {settings.READWISE_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "url": url,
                "tags": [settings.DOCUMENT_TAG],
                "location": "new"  # Save to "new" items
            }
        )
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        logger.error(f"Error saving URL to Readwise: {str(e)}")
        return False

async def check_url_exists(url: str) -> bool:
    """Check if a URL already exists in Readwise Reader."""
    try:
        response = requests.get(
            "https://readwise.io/api/v3/list/",
            headers={
                "Authorization": f"Token {settings.READWISE_API_KEY}"
            },
            params={
                "url": url
            }
        )
        response.raise_for_status()
        data = response.json()
        return len(data.get("results", [])) > 0
    except requests.RequestException as e:
        logger.error(f"Error checking URL in Readwise: {str(e)}")
        return False

@app.event("reaction_added")
@deduplicator.deduplicate(ttl=60)  # Set TTL to 60 seconds
async def handle_reaction(event, say, client):
    if trigger_emojis is not None and event['reaction'] not in trigger_emojis:
        return
    channel_id = event["item"]["channel"]
    message_ts = event["item"]["ts"]
    try:
        result = await client.conversations_history(
            channel=channel_id,
            latest=message_ts,
            limit=1,
            inclusive=True
        )
        if result.data.get("messages"):
            message = result.data["messages"][0]
            url = extract_and_validate_url(message)
            if url:
                # First, check if the URL already exists
                url_exists = await check_url_exists(url)
                if url_exists:
                    logger.info(f"URL already exists in Readwise, skipping: {url}")
                    # No message is posted to Slack for duplicate URLs
                else:
                    # If the URL doesn't exist, save it
                    if await save_url_to_readwise(url):
                        reply_text = f"Saved URL to Readwise Reader with tag '{settings.DOCUMENT_TAG}': {url}"
                        await client.chat_postMessage(
                            channel=channel_id,
                            text=reply_text,
                            thread_ts=message_ts
                        )
                    else:
                        logger.error(f"Failed to save URL to Readwise: {url}")
        else:
            logger.warning("No message found in the conversation history")
    except Exception as e:
        logger.error(f"Error handling reaction: {str(e)}")
