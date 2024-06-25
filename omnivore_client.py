import httpx
import logging
import json
import secrets
from typing import Optional, Dict, Any
from datetime import datetime, timezone

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
        
        # Create a SaveUrlInput that matches the schema
        save_url_input = {
            "url": url,
            "source": "slack_bot",
            "clientRequestId": secrets.token_urlsafe(),
            "state": "SUCCEEDED",  # Assuming we want to save it as succeeded
            "labels": [{"name": label}],
            "locale": "en-US",  # You might want to make this configurable
            "timezone": str(datetime.now(timezone.utc).astimezone().tzinfo),
            "savedAt": datetime.now(timezone.utc).isoformat(),
            # "publishedAt" is optional, so we're not including it
            # "folder" is optional, so we're not including it
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
                "input": save_url_input
            }
        }
        
        logger.debug(f"Sending request to Omnivore API. URL: {url}, Label: {label}")
        logger.debug(f"Request payload: {json.dumps(payload, indent=2)}")
        logger.debug(f"Request headers: {json.dumps(headers, indent=2)}")

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

    async def test_connection(self) -> bool:
        """Test the connection to Omnivore API"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.api_key
        }
        
        payload = {
            "query": """
            query {
                me {
                    id
                    name
                }
            }
            """
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.api_url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            if "data" in result and "me" in result["data"]:
                logger.info(f"Successfully connected to Omnivore API. User: {result['data']['me']['name']}")
                return True
            else:
                logger.error(f"Unexpected response from Omnivore API: {result}")
                return False
        except Exception as e:
            logger.error(f"Failed to connect to Omnivore API: {str(e)}")
            return False