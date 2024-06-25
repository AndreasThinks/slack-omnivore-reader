import httpx
import logging
import json
import secrets
from typing import Optional, Dict, Any

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
        
        logger.debug(f"Sending request to Omnivore API. URL: {url}, Label: {label}")
        logger.debug(f"Request payload: {json.dumps(payload, indent=2)}")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.api_url, headers=headers, json=payload)
            
            logger.debug(f"Response status code: {response.status_code}")
            logger.debug(f"Response headers: {dict(response.headers)}")
            logger.debug(f"Response content: {response.text}")

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
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON response: {e}")
            logger.error(f"Raw response content: {response.text}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred while saving to Omnivore: {str(e)}", exc_info=True)
            return None

    def _process_omnivore_response(self, result: Dict[str, Any], url: str, label: str) -> Optional[str]:
        logger.debug(f"Processing Omnivore response: {json.dumps(result, indent=2)}")
        
        if "data" in result and "saveUrl" in result["data"]:
            save_url_result = result["data"]["saveUrl"]
            if isinstance(save_url_result, dict):
                if "url" in save_url_result:
                    logger.info(f"Successfully saved URL to Omnivore: {url} with label: {label}")
                    return save_url_result["url"]
                elif "errorCodes" in save_url_result:
                    error_codes = save_url_result["errorCodes"]
                    error_message = save_url_result.get("message", "No error message provided")
                    logger.error(f"Failed to save URL to Omnivore. Error codes: {error_codes}, Message: {error_message}")
                    logger.error(f"Attempted to save URL: {url}")
                else:
                    logger.error(f"Unexpected saveUrl response format: {save_url_result}")
            else:
                logger.error(f"Unexpected saveUrl data type: {type(save_url_result)}")
        else:
            logger.error(f"Unexpected response format from Omnivore API: {result}")
        return None