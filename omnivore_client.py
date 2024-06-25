import httpx
import logging
import json
import uuid
from typing import Optional, Dict, Any
import os

logger = logging.getLogger(__name__)

class OmnivoreClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_url = "https://api-prod.omnivore.app/api/graphql"
        self.label = os.environ.get("OMNIVORE_LABEL", "SlackSaved")

    async def save_url(self, url: str) -> Optional[Dict[str, Any]]:
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
                    "clientRequestId": str(uuid.uuid4()),
                    "source": "api",
                    "url": url,
                    "labels": [{"name": self.label}]
                }
            }
        }
        
        logger.debug(f"Sending request to Omnivore API. URL: {url}, Label: {self.label}")
        logger.debug(f"Request payload: {json.dumps(payload, indent=2)}")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.api_url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            logger.info(f"Successfully saved URL to Omnivore: {url} with label: {self.label}")
            logger.debug(f"Omnivore API response: {json.dumps(result, indent=2)}")
            
            if "data" in result and isinstance(result["data"], dict):
                return result
            else:
                logger.error("Unexpected response format from Omnivore API")
                return None
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error occurred while saving to Omnivore: {e}")
            logger.error(f"Response content: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"An error occurred while saving to Omnivore: {str(e)}", exc_info=True)
            raise

    def _process_omnivore_response(self, result: Dict[str, Any], url: str) -> Optional[str]:
        logger.debug(f"Processing Omnivore response: {json.dumps(result, indent=2)}")
        
        if "data" in result and "saveUrl" in result["data"]:
            save_url_result = result["data"]["saveUrl"]
            if isinstance(save_url_result, dict):
                if "url" in save_url_result:
                    logger.info(f"Successfully saved URL to Omnivore: {url} with label: {self.label}")
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