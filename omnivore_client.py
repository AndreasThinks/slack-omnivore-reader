import httpx
import logging
import secrets
from typing import Optional

logger = logging.getLogger(__name__)

class OmnivoreClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_url = "https://api-prod.omnivore.app/api/graphql"

    async def save_url(self, url: str, label: str) -> Optional[str]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.api_key
        }
        
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
                    "clientRequestId": secrets.token_urlsafe(),
                    "source": "api",
                    "url": url,
                    "labels": [{"name": label}]
                }
            }
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.api_url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            logger.info(f"Successfully saved URL to Omnivore: {url} with label: {label}")
            
            if "data" in result and "saveUrl" in result["data"]:
                return result["data"]["saveUrl"].get("url")
            else:
                logger.error("Unexpected response format from Omnivore API")
                return None
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error occurred while saving to Omnivore: {e}")
        except Exception as e:
            logger.error(f"An error occurred while saving to Omnivore: {str(e)}", exc_info=True)
        return None
