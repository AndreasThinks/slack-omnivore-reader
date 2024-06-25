import httpx
import logging
from typing import Optional, Dict, Any
import secrets


logger = logging.getLogger(__name__)

class OmnivoreClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_url = "https://api-prod.omnivore.app/api/graphql"

    async def save_url(self, url: str, label: str) -> Optional[str]:

        # TODO improve this, currently cleaning weird trailng > bug
        url = url.rstrip('>') if url else url

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
            
            return self._process_omnivore_response(result, url, label)
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error occurred while saving to Omnivore: {e}")
            logger.error(f"Response content: {e.response.text}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Request error occurred while saving to Omnivore: {e}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred while saving to Omnivore: {str(e)}", exc_info=True)
            return None

    def _process_omnivore_response(self, result: Dict[str, Any], url: str, label: str) -> Optional[str]:
        if "data" in result and "saveUrl" in result["data"]:
            save_url_result = result["data"]["saveUrl"]
            if "url" in save_url_result:
                logger.info(f"Successfully saved URL to Omnivore: {url} with label: {label}")
                return save_url_result["url"]
            elif "errorCodes" in save_url_result:
                error_codes = save_url_result["errorCodes"]
                error_message = save_url_result.get("message", "No error message provided")
                logger.error(f"Failed to save URL to Omnivore. Error codes: {error_codes}, Message: {error_message}")
            else:
                logger.error(f"Unexpected saveUrl response format: {save_url_result}")
        else:
            logger.error(f"Unexpected response format from Omnivore API: {result}")
        return None