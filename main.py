from fasthtml import FastHTML
from fasthtml.common import fast_app, Form, Head, Picture, SortableJS, Hidden, HTMLResponse, serve, database, Div, Card, MarkdownJS, A, Html, H3, Title, Body, Img, Titled, Article, Header, P, Footer, Main, H1, Style, picolink, H2, Ul, Li, Script
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from limits import parse_many
import pandas as pd
from datetime import datetime, timedelta
import os

from summariser.newsletter_creator import get_last_update_date, db, create_newsletter
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
        cursor: move;
        transition: all 0.3s ease;
    }
    .item-list {
        list-style: none !important;
        padding-left: 0 !important;
        margin-left: 0 !important;
                 
    }
    .item-list li {
        list-style-type: none !important;
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
        list-style-type: none;
    }
    .sortable {
        list-style-type: none;
    }
    #header-image {
        display: block;
        margin-left: auto;
        margin-right: auto;
        max-width: 30%;
        height: auto;
    }
    .download-btn {
        display: inline-block;
        padding: 0.5rem 1.2rem;
        background-color: #4F46E5;
        color: white;
        text-decoration: none;
        border-radius: 0.5rem;
        font-size: 0.95rem;
        transition: all 0.2s ease;
        border: none;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
    }
    .download-btn:hover {
        background-color: #4338CA;
        transform: translateY(-1px);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    }
    .header-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1.5rem;
        padding: 0.5rem 0;
    }
    .last-updated {
        margin: 0;
    }
''')


class StoryCard:
    def __init__(self, title, url, long_summary, short_summary, item_id):
        self.title = title
        self.url = url
        self.long_summary = long_summary
        self.short_summary = short_summary
        self.item_id = item_id

    def render(self, format_type):
        base_class = "item-card"
        if format_type == "long":
            base_class += " long-item"
        elif format_type == "short":
            base_class += " short-item"
        else:  # link format
            base_class += " link-item"

        return Li(
            Article(
                H3(A(self.title, href=self.url)),
                P(self.long_summary, cls="long-summary"),
                P(self.short_summary, cls="short-summary"),
                Footer(A("Read more", href=self.url, cls="secondary read-more")),
                Hidden(id="id", value=self.item_id),
                cls=base_class,
            )
        )


app, rt = fast_app(hdrs=(picolink, pico_css, SortableJS('.sortable'),), htmlkw={'data-theme': 'light'})

LONG_ITEM_COUNT = 3
SHORT_ITEM_COUNT = 4

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
        df_sorted = df.sort_values('interest_score', ascending=False).reset_index(drop=True)
    except KeyError:
        logger.error("No items found in the database")
        create_newsletter()
        df_sorted = pd.DataFrame()
        df = pd.DataFrame(items())
        df_sorted = df.sort_values('interest_score', ascending=False).reset_index(drop=True)

    item_cards = []
    for i, row in df_sorted.iterrows():
        card = StoryCard(row['title'], row['url'], row['long_summary'], row['short_summary'], row['id'])
        format_type = "long" if i < LONG_ITEM_COUNT else "short" if i < LONG_ITEM_COUNT + SHORT_ITEM_COUNT else "link"
        item_cards.append(card.render(format_type))

    card_container = Form(*item_cards,
               id='story-container', cls='sortable', hx_trigger="end", hx_post="/reorder", hx_swap="innerHTML", hx_target="#story-container")

    # Get the latest newsletter summary
    latest_summary = newsletter_summaries(order_by='-date', limit=1)
    summary_content = latest_summary[0]['summary'] if latest_summary else "No newsletter summary available."

    # Add download button for newsletter
    download_btn = A("Download Newsletter", href="/download-newsletter", cls="download-btn")

    page = (Title('Bedtime Reading'),
            Img(src=f"/header.png", id=f'header-image'),
        Main(
            Div(
                    Div(
                        P(f"Last updated on: {last_update.strftime('%Y-%m-%d') if last_update else 'Never'}", cls="last-updated"),
                        download_btn,
                        cls="header-row"
                    ),
                    Div(summary_content, cls="newsletter-summary"),
                    card_container, 
                cls="container"
            )
        )
    )

    return page

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

@app.post("/reorder")
async def reorder(request: Request):
    form_data = await request.form()
    ids = form_data.getlist("id")

    new_order = ids

    df = pd.DataFrame(items())
    df_sorted = df.sort_values('interest_score', ascending=False).reset_index(drop=True)

    # Get the original order of items
    original_order = df_sorted['id'].tolist()
    
    # Record comparisons
    for new_index, item_id in enumerate(new_order):
        item_id = int(item_id)
        old_index = original_order.index(item_id)
        
        if new_index < old_index:
            # This item has moved up in the ranking
            for losing_id in original_order[new_index:old_index]:
                if losing_id != item_id:
                    comparisons.insert({
                        'winning_id': item_id,
                        'losing_id': losing_id
                    })

    # Reorder items based on new order
    reordered_items = []
    for item_id in new_order:
        item = df_sorted[df_sorted['id'] == int(item_id)].iloc[0]
        reordered_items.append(item)

    # Render the reordered items
    item_cards = []
    for i, row in enumerate(reordered_items):
        card = StoryCard(row['title'], row['url'], row['long_summary'], row['short_summary'], row['id'])
        format_type = "long" if i < LONG_ITEM_COUNT else "short" if i < LONG_ITEM_COUNT + SHORT_ITEM_COUNT else "link"
        item_cards.append(card.render(format_type))

    return Li(*item_cards)

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
