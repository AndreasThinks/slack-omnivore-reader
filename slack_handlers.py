import logging
from slack_bolt.async_app import AsyncApp
from config import settings
from omnivore_client import OmnivoreClient
from utils import extract_and_validate_url, get_trigger_emojis

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app = AsyncApp(
    token=settings.SLACK_BOT_TOKEN,
    signing_secret=settings.SLACK_SIGNING_SECRET
)

omnivore_client = OmnivoreClient(settings.OMNIVORE_API_KEY)
trigger_emojis = get_trigger_emojis()

@app.event("reaction_added")
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