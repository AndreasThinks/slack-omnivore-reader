import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from limits import parse_many

from config import settings
from slack_handlers import app as slack_app
from utils import setup_rate_limiter, setup_logging

# Set up logging
logger = setup_logging()

# Initialize FastAPI app
fastapi_app = FastAPI()
handler = AsyncSlackRequestHandler(slack_app)

# Add secure HTTP headers
fastapi_app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)
fastapi_app.add_middleware(HTTPSRedirectMiddleware)

# Set up rate limiting
limiter = setup_rate_limiter()
rate_limits = parse_many(settings.RATE_LIMIT)

@fastapi_app.post("/slack/events")
async def slack_events(req: Request):
    try:
        # Check rate limits
        for rate_limit in rate_limits:
            if not limiter.hit(rate_limit, "global", req.client.host):
                logger.warning("Rate limit exceeded")
                raise HTTPException(status_code=429, detail="Too many requests")
        
        body = await req.json()
        logger.info(f"Received Slack event: {body}")
        
        # Handle URL verification
        if body.get("type") == "url_verification":
            return {"challenge": body["challenge"]}
        
        return await handler.handle(req)
    except Exception as e:
        logger.error(f"Error handling Slack event: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An error occurred processing the Slack event")

@fastapi_app.get("/")
async def health_check():
    logger.info("Health check endpoint accessed")
    return {"status": "healthy"}

# Middleware for request logging
@fastapi_app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Request received: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response

# Error handling middleware
@fastapi_app.middleware("http")
async def errors_handling(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        logger.error(f"An error occurred: {str(exc)}", exc_info=True)
        return JSONResponse(status_code=500, content={"message": "An internal error occurred"})

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting FastAPI application")
    uvicorn.run("main:fastapi_app", host="0.0.0.0", port=settings.PORT)