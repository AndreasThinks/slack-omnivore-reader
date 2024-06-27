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

    async def search_url(self, url: str) -> bool:
        querystring = {
            "after": "null",
            "first": "10",
            "query": f'url:"{url}"'
        }

        payload = {
            "query": """
            query Search($after: String, $first: Int, $query: String) {
              search(after: $after, first: $first, query: $query) {
                ... on SearchSuccess {
                  edges {
                    node {
                      id
                      title
                      url
                    }
                  }
                  pageInfo {
                    hasNextPage
                    endCursor
                    totalCount
                  }
                }
                ... on SearchError {
                  errorCodes
                }
              }
            }
            """,
            "operationName": "Search"
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "OmnivoreClient/1.0",
            "Authorization": self.api_key
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.api_url, data=json.dumps(payload), headers=headers, params=querystring)
            response.raise_for_status()
            result = response.json()
            
            logger.debug(f"Search URL response: {json.dumps(result, indent=2)}")
            
            if "data" in result and "search" in result["data"]:
                search_result = result["data"]["search"]
                if "edges" in search_result:
                    for edge in search_result["edges"]:
                        if edge["node"]["url"] == url:
                            logger.info(f"Exact URL match found in Omnivore: {url}")
                            return True
                    logger.info(f"Exact URL not found in Omnivore: {url}")
                    return False
                else:
                    logger.info(f"No search results for URL: {url}")
                    return False
            logger.warning(f"Unexpected search result format for URL: {url}")
            return False
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error occurred while searching Omnivore: {e}")
            raise
        except Exception as e:
            logger.error(f"An error occurred while searching Omnivore: {str(e)}")
            raise

    async def save_url(self, url: str) -> Optional[Dict[str, Any]]:
        url = url.rstrip('>') if url else url
        
        # Check if the URL already exists
        if await self.search_url(url):
            logger.info(f"URL already exists, skipping save: {url}")
            return None

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

        headers = {
            "Content-Type": "application/json",
            "Authorization": self.api_key
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.api_url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            
            if "data" in result and isinstance(result["data"], dict):
                logger.info(f"Successfully saved URL to Omnivore: {url}")
                return result
            else:
                logger.error("Unexpected response format from Omnivore API")
                return None
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error occurred while saving to Omnivore: {e}")
            raise
        except Exception as e:
            logger.error(f"An error occurred while saving to Omnivore: {str(e)}")
            raise