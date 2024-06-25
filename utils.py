import re
import logging
from typing import Optional, List
from urllib.parse import urlparse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

from config import settings

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Reduce logging for some verbose libraries
    # TODO decide if we want to add these back
    # logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('slack_bolt').setLevel(logging.WARNING)


def setup_rate_limiter():
    return MovingWindowRateLimiter(MemoryStorage())
def get_trigger_emojis() -> Optional[List[str]]:
    if settings.TRIGGER_EMOJIS:
        return [emoji.strip() for emoji in settings.TRIGGER_EMOJIS.split(',')]
    return None

def sanitize_url(url: str) -> str:
    # Remove any trailing '>' characters and whitespace
    sanitized = url.rstrip('>').strip()
    # Ensure the URL starts with http:// or https://
    if not sanitized.startswith(('http://', 'https://')):
        sanitized = 'http://' + sanitized
    return sanitized

def is_valid_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def extract_and_validate_url(message: dict) -> Optional[str]:
    url = extract_url_from_message(message)
    if url:
        sanitized_url = sanitize_url(url)
        if is_valid_url(sanitized_url):
            return sanitized_url
    return None

def extract_url_from_message(message: dict) -> Optional[str]:
    text = message.get("text", "")
    urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)
    if urls:
        return urls[0]
    
    attachments = message.get("attachments", [])
    for attachment in attachments:
        attachment_text = attachment.get("text", "")
        attachment_urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-F]))+', attachment_text)
        if attachment_urls:
            return attachment_urls[0]
    
    blocks = message.get("blocks", [])
    for block in blocks:
        if block.get("type") == "section":
            text = block.get("text", {}).get("text", "")
            block_urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-F]))+', text)
            if block_urls:
                return block_urls[0]
    
    return None