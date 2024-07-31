import logging
from slack_bolt.async_app import AsyncApp
from config import settings
from omnivore_client import OmnivoreClient
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
omnivore_client = OmnivoreClient(settings.OMNIVORE_API_KEY)
trigger_emojis = get_trigger_emojis()
deduplicator = EventDeduplicator()

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
                url_exists = await omnivore_client.search_url(url)
                if url_exists:
                    logger.info(f"URL already exists in Omnivore, skipping: {url}")
                    # No message is posted to Slack for duplicate URLs
                else:
                    # If the URL doesn't exist, save it
                    result = await omnivore_client.save_url(url)
                    if result and "data" in result and "saveUrl" in result["data"]:
                        saved_url = result["data"]["saveUrl"].get("url")
                        if saved_url:
                            reply_text = f"Saved URL to Omnivore with label '{settings.OMNIVORE_LABEL}': {saved_url}"
                            await client.chat_postMessage(
                                channel=channel_id,
                                text=reply_text,
                                thread_ts=message_ts
                            )
                        else:
                            logger.warning(f"Attempted to save URL to Omnivore, but encountered an issue: {url}")
                    else:
                        logger.error(f"Failed to save URL to Omnivore: {url}")
        else:
            logger.warning("No message found in the conversation history")
    except Exception as e:
        logger.error(f"Error handling reaction: {str(e)}")