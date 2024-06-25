import logging
from slack_bolt.async_app import AsyncApp
from config import settings
from omnivore_client import OmnivoreClient
from utils import extract_and_validate_url, get_trigger_emojis

logger = logging.getLogger(__name__)

app = AsyncApp(
    token=settings.SLACK_BOT_TOKEN,
    signing_secret=settings.SLACK_SIGNING_SECRET
)

omnivore_client = OmnivoreClient(settings.OMNIVORE_API_KEY)
trigger_emojis = get_trigger_emojis()


@app.event("reaction_added")
async def handle_reaction(event, say, client):
    logger.info(f"Received reaction_added event: {event}")
    
    # Check if the reaction should trigger the bot
    if trigger_emojis is not None and event['reaction'] not in trigger_emojis:
        logger.info(f"Reaction {event['reaction']} is not in the trigger list. Ignoring.")
        return

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
        
        if result.data.get("messages"):
            message = result.data["messages"][0]
            logger.info(f"Retrieved message: {message}")
            url = extract_and_validate_url(message)
            
            if url:
                logger.info(f"URL extracted: {url}")
                result = await omnivore_client.save_url(url, settings.OMNIVORE_LABEL)
                if result:
                    reply_text = f"Saved URL to Omnivore with label '{settings.OMNIVORE_LABEL}': {result}"
                    await client.chat_postMessage(
                        channel=channel_id,
                        text=reply_text,
                        thread_ts=message_ts
                    )
                else:
                    logger.warning("Failed to save URL to Omnivore")
            else:
                logger.info("No URL found in the message. Remaining silent.")
        else:
            logger.warning("No message found in the conversation history")
    except Exception as e:
        logger.error(f"Error handling reaction: {str(e)}", exc_info=True)
