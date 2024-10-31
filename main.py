from fasthtml import FastHTML
from fasthtml.common import fast_app, NotStr, Form, Head, Picture, Hidden, HTMLResponse, serve, database, Div, Card, MarkdownJS, A, Html, H3, Title, Body, Img, Titled, Article, Header, P, Footer, Main, H1, Style, picolink, H2, Ul, Li, Script, Button
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from limits import parse_many
import pandas as pd
from datetime import datetime, timedelta
import os
import pytz

from summariser.newsletter_creator import get_last_update_date, db, create_newsletter, process_articles, update_items_from_articles
from config import settings
from slack_handlers import app as slack_app
from utils import setup_rate_limiter, setup_logging

logger = setup_logging()

# Set up rate limiting
limiter = setup_rate_limiter()
rate_limits = parse_many(settings.RATE_LIMIT)
handler = AsyncSlackRequestHandler(slack_app)


items = db.t.items
comparisons = db.t.comparisons
last_update = db.t.last_update
newsletter_summaries = db.t.newsletter_summaries


pico_css = Style('''
    :root { 
        --pico-font-size: 100%; 
        --pico-font-family: Pacifico;
        --card-border-color: #d1d5db;
        --card-background: #f9fafb;
    }
    .item-card {
        margin-bottom: 1rem;
        border: 1px solid var(--card-border-color);
        border-radius: 0.5rem;
        padding: 1rem;
        background-color: var(--card-background);
        transition: all 0.3s ease;
    }
    .card-header {
        display: flex;
        align-items: center;  /* This was already correct */
        gap: 1rem;
    }
    .vote-buttons {
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
        margin-right: 1rem;
        /* Add height to match the typical height of the title */
        min-height: 2.5rem;
        justify-content: center;  /* Center the buttons vertically */
    }
    .vote-button {
        cursor: pointer;
        padding: 0.25rem;
        color: #9CA3AF;
        background: none;
        border: none;
        text-decoration: none;
        width: 24px;
        height: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 4px;
        transition: all 0.2s ease;
    }
    .vote-button:hover {
        color: #4F46E5;
        background: #EEF2FF;
    }
    .vote-button svg {
        width: 16px;
        height: 16px;
    }
    .card-title {
        margin: 0 !important;  /* Remove default margins */
        display: flex;
        align-items: center;
        min-height: 2.5rem;  /* Match height of vote buttons */
        flex: 1;  /* Take remaining space */
    }
    .card-title h3 {
        margin: 0;
    }
    .card-title a {
        display: inline-flex;
        align-items: center;
        min-width: 150px;
    }
    .item-list {
        list-style: none !important;
        padding-left: 0 !important;
        margin-left: 0 !important;
    }
    .item-list li {
        list-style-type: none !important;
    }
    #story-container {
        list-style: none !important;
        padding-left: 0 !important;
    }
    #story-container li {
        list-style: none !important;
    }
    .long-item {
        padding: 1.5rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .long-item h3 {
        font-size: 1.5rem;
        margin-bottom: 1rem;
    }
    .short-item {
        padding: 1rem;
    }
    .short-item h3 {
        font-size: 1.2rem;
        margin-bottom: 0.5rem;
    }
    .link-item {
        padding: 0.5rem;
        border: none;
        background: none;
    }
    .link-item h3 {
        font-size: 1rem;
        margin-bottom: 0;
    }
    .long-summary, .short-summary, .read-more {
        display: none;
    }
    .long-item .long-summary,
    .short-item .short-summary,
    .long-item .read-more,
    .short-item .read-more {
        display: block;
    }
    h2 {
        margin-top: 2rem;
        margin-bottom: 1rem;
        border-bottom: 2px solid var(--card-border-color);
        padding-bottom: 0.5rem;
    }
    .newsletter-summary {
        background-color: #f0f4f8;
        border: 1px solid #d1d5db;
        border-radius: 0.5rem;
        padding: 1rem;
        margin-bottom: 2rem;
    }
    ul, ol {
        list-style-type: none !important;
        padding-left: 0 !important;
    }
    #header-image {
        display: block;
        margin-left: auto;
        margin-right: auto;
        max-width: 30%;
        height: auto;
    }
    .header-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.5rem;
        padding: 0.75rem 0;
    }
    .last-updated {
        margin: 0;
    }
    .article-date {
        color: #6B7280;
        font-size: 0.875rem;
        margin-top: 0.5rem;
                 order: 2;
    }
    .action-btn {
        display: inline-block;
        padding: 0.5rem 1.2rem;
        color: white;
        text-decoration: none;
        border-radius: 0.5rem;
        font-size: 0.95rem;
        font-weight: 500;
        transition: all 0.2s ease;
        border: none;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
        cursor: pointer;
    }
    .action-btn:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .download-btn {
        background-color: #4F46E5;
        margin-right: 1rem;
    }
    .download-btn:hover {
        background-color: #4338CA;
    }
    .refresh-btn {
        background-color: #10B981;
        position: relative;
    }
    .refresh-btn:hover {
        background-color: #059669;
    }
    .refresh-btn.htmx-request {
        pointer-events: none;
        opacity: 0.7;
    }
    .refresh-btn.htmx-request::after {
        content: "";
        position: absolute;
        width: 1em;
        height: 1em;
        top: 50%;
        right: 0.5rem;
        transform: translateY(-50%);
        border: 2px solid transparent;
        border-top-color: #ffffff;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }
    @keyframes spin {
        to {
            transform: translateY(-50%) rotate(360deg);
        }
    }
''')


class StoryCard:
    def __init__(self, title, url, long_summary, short_summary, item_id, saved_at):
        self.title = title
        self.url = url
        self.long_summary = long_summary
        self.short_summary = short_summary
        self.item_id = item_id
        # Parse ISO format date and format it nicely, with fallback to current time
        try:
            dt = datetime.fromisoformat(saved_at.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            dt = datetime.now(pytz.UTC)
            print(f"Warning: Invalid saved_at date for article {title}, using current time")
        self.saved_at = dt.strftime('%B %d, %Y at %I:%M %p')

    def render(self, format_type):
        base_class = "item-card"
        if format_type == "long":
            base_class += " long-item"
        elif format_type == "short":
            base_class += " short-item"
        else:  # link format
            base_class += " link-item"

        # SVG icons for vote buttons
        up_arrow = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M14.77 12.79a.75.75 0 01-1.06-.02L10 8.832 6.29 12.77a.75.75 0 11-1.08-1.04l4.25-4.5a.75.75 0 011.08 0l4.25 4.5a.75.75 0 01-.02 1.06z" clip-rule="evenodd" />
        </svg>'''
        
        down_arrow = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd" />
        </svg>'''

        return Li(
            Article(
                Div(
                    Div(
                        A(NotStr(up_arrow), href="#", cls="vote-button", hx_post=f"/vote/{self.item_id}/up", hx_target="#story-container", hx_swap="innerHTML"),
                        A(NotStr(down_arrow), href="#", cls="vote-button", hx_post=f"/vote/{self.item_id}/down", hx_target="#story-container", hx_swap="innerHTML"),
                        cls="vote-buttons"
                    ),
                    H3(A(self.title, href=self.url), cls="card-title"),
                    P(f"Saved on {self.saved_at}", cls="article-date"),
                    cls="card-header"
                ),
                P(self.long_summary, cls="long-summary"),
                P(self.short_summary, cls="short-summary"),
                Footer(A("Read more", href=self.url, cls="secondary read-more")),
                Hidden(id="id", value=self.item_id),
                cls=base_class,
            )
        )


app, rt = fast_app(hdrs=(picolink, pico_css), htmlkw={'data-theme': 'light'})

@app.get("/")
def home():
    last_update = get_last_update_date()
    current_date = datetime.now().date()

    if not last_update or (current_date - last_update) >= timedelta(days=7):
        if current_date.weekday() == 4:  # 4 represents Friday (0 is Monday, 6 is Sunday)
            print("Updating items from Omnivore...")
            create_newsletter()
            last_update = current_date

    try:
        df = pd.DataFrame(items())
        
        # Convert saved_at to datetime
        df['saved_at'] = pd.to_datetime(df['saved_at'])
        
        # Calculate minimum required items
        min_required = (
            settings.NUMBER_OF_LONG_ARTICLES + 
            settings.NUMBER_OF_SHORT_ARTICLES
        )
        
        if len(df) < min_required:
            # If we don't have enough items, sort purely by interest score
            df_sorted = df.sort_values('interest_score', ascending=False)
        else:
            # Calculate a time decay factor (e.g., last 7 days get priority)
            current_time = pd.Timestamp.now(tz='UTC')
            df['days_old'] = (current_time - df['saved_at']).dt.total_seconds() / (24 * 3600)
            
            # Create a combined score that weighs both recency and interest
            # Articles less than 7 days old get a boost
            df['recency_boost'] = (df['days_old'] <= 7).astype(float) * 1000
            
            # Combined score considers both interest_score and recency
            df['combined_score'] = df['interest_score'] + df['recency_boost']
            
            # Sort by combined score, then by saved_at for ties
            df_sorted = df.sort_values(
                ['combined_score', 'saved_at'], 
                ascending=[False, False]
            )
        
        df_sorted = df_sorted.reset_index(drop=True)
        
    except KeyError:
        logger.error("No items found in the database")
        create_newsletter()
        df = pd.DataFrame(items())
        df_sorted = df.sort_values('interest_score', ascending=False).reset_index(drop=True)

    item_cards = []
    for i, row in df_sorted.iterrows():
        card = StoryCard(
            row['title'], 
            row['url'], 
            row['long_summary'], 
            row['short_summary'], 
            row['id'], 
            row['saved_at'].isoformat() if isinstance(row['saved_at'], pd.Timestamp) else row['saved_at']
        )
        format_type = "long" if i < settings.NUMBER_OF_LONG_ARTICLES else \
                     "short" if i < settings.NUMBER_OF_LONG_ARTICLES + settings.NUMBER_OF_SHORT_ARTICLES else \
                     "link"
        item_cards.append(card.render(format_type))

    card_container = Ul(*item_cards, id='story-container')

    # Get the latest newsletter summary
    latest_summary = newsletter_summaries(order_by='-date', limit=1)
    summary_content = latest_summary[0]['summary'] if latest_summary else "No newsletter summary available."

    # Add download button for newsletter and refresh button
    buttons = Div(
        A("Download Newsletter", href="/download-newsletter", cls="action-btn download-btn"),
        Button("Refresh Articles", 
               cls="action-btn refresh-btn",
               hx_post="/refresh",
               hx_target="#story-container",
               hx_swap="innerHTML",
               hx_indicator=".refresh-btn"),
        style="display: flex; align-items: center;"
    )

    page = (Title('Bedtime Reading'),
            Img(src=f"/header.png", id=f'header-image'),
        Main(
            Div(
                    Div(
                        P(f"Last updated on: {last_update.strftime('%Y-%m-%d') if last_update else 'Never'}", cls="last-updated"),
                        buttons,
                        cls="header-row"
                    ),
                    Div(summary_content, cls="newsletter-summary"),
                    card_container, 
                cls="container"
            )
        )
    )

    return page

@app.post("/refresh")
async def refresh_articles():
    """Force a refresh of articles and their scores."""
    try:
        logger.info("Starting manual refresh of articles...")
        articles = process_articles()
        update_items_from_articles(articles)
        logger.info("Manual refresh completed successfully")
        
        # Return just the updated story container content
        df = pd.DataFrame(items())
        df_sorted = df.sort_values('interest_score', ascending=False).reset_index(drop=True)
        
        item_cards = []
        for i, row in df_sorted.iterrows():
            card = StoryCard(row['title'], row['url'], row['long_summary'], row['short_summary'], row['id'], row['saved_at'])
            format_type = "long" if i < settings.NUMBER_OF_LONG_ARTICLES else "short" if i < settings.NUMBER_OF_LONG_ARTICLES + settings.NUMBER_OF_SHORT_ARTICLES else "link"
            item_cards.append(card.render(format_type))
        
        return Ul(*item_cards, id='story-container')
    except Exception as e:
        logger.error(f"Error during manual refresh: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error refreshing articles")

@app.get("/download-newsletter")
async def download_newsletter():
    """Serve the newsletter HTML file for download."""
    newsletter_path = "newsletter.html"
    if not os.path.exists(newsletter_path):
        # Generate a new newsletter if it doesn't exist
        create_newsletter()
    
    if os.path.exists(newsletter_path):
        return FileResponse(
            path=newsletter_path,
            filename=f"newsletter_{datetime.now().strftime('%Y-%m-%d')}.html",
            media_type="text/html"
        )
    raise HTTPException(status_code=404, detail="Newsletter not found")

@app.post("/update")
async def update():
    current_date = datetime.now().date()
    last_update.update({'date': current_date})

@app.post("/vote/{id}/{direction}")
async def vote(id: int, direction: str):
    try:
        # Get current item's score
        current_item = items[id]
        current_score = current_item.get('interest_score', 0)
        
        # Get fresh list of sorted items
        df = pd.DataFrame(items())
        df_sorted = df.sort_values('interest_score', ascending=False).reset_index(drop=True)
        
        # Find current index
        current_idx = df_sorted[df_sorted['id'] == id].index[0]
        
        # Calculate new index based on vote direction
        new_idx = current_idx - 1 if direction == "up" else current_idx + 1
        
        # Ensure new index is within bounds
        if 0 <= new_idx < len(df_sorted):
            # Get the item we're comparing with
            target_item = df_sorted.iloc[new_idx]
            target_score = target_item['interest_score']
            
            if direction == "up":
                # Set score just slightly higher than the item above
                new_score = target_score + 0.1
                
                # Record the comparison
                comparisons.insert({
                    'winning_id': int(id),
                    'losing_id': int(target_item['id'])
                })
            else:
                # Set score just slightly lower than the item below
                new_score = target_score - 0.1
                
                # Record the comparison
                comparisons.insert({
                    'winning_id': int(target_item['id']),
                    'losing_id': int(id)
                })
            
            # Update the score
            items.update({'interest_score': new_score}, id)
        
        # Re-fetch and sort items
        df = pd.DataFrame(items())
        df_sorted = df.sort_values('interest_score', ascending=False).reset_index(drop=True)
        
        # Render updated list
        item_cards = []
        for i, row in df_sorted.iterrows():
            card = StoryCard(row['title'], row['url'], row['long_summary'], row['short_summary'], row['id'], row['saved_at'])
            format_type = "long" if i < settings.NUMBER_OF_LONG_ARTICLES else "short" if i < settings.NUMBER_OF_LONG_ARTICLES + settings.NUMBER_OF_SHORT_ARTICLES else "link"
            item_cards.append(card.render(format_type))
        
        return Ul(*item_cards, id='story-container')
    
    except Exception as e:
        logger.error(f"Error in vote endpoint: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error processing vote")

@app.post("/slack/events")
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
    
serve()
