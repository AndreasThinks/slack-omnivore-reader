from fasthtml import FastHTML
from fasthtml.common import Form, HTMLResponse, serve, database, Div, Card, MarkdownJS, A, Html, H3, Title, Body, Img, Titled, Article, Header, P, Footer, Main, H1, Style, picolink, H2, Ul, Li, Script
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from limits import parse_many
import pandas as pd
from datetime import datetime, timedelta

from summariser.newsletter_creator import update_items_from_articles, get_last_update_date
from config import settings
from slack_handlers import app as slack_app
from utils import setup_rate_limiter, setup_logging

logger = setup_logging()

# Set up rate limiting
limiter = setup_rate_limiter()
rate_limits = parse_many(settings.RATE_LIMIT)
handler = AsyncSlackRequestHandler(slack_app)

# Set up SQLite database
db = database('data/items.db')
items = db.t.items
comparisons = db.t.comparisons
last_update = db.t.last_update
newsletter_summaries = db.t.newsletter_summaries

# if there are no items in the database, create the table
if not items.exists():
    update_items_from_articles()


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
''')


sortable_js = Script('''
    import Sortable from 'https://cdn.jsdelivr.net/npm/sortablejs@1.14.0/modular/sortable.esm.js';

    const LONG_ITEM_COUNT = 4;
    const SHORT_ITEM_COUNT = 6;

    new Sortable(document.querySelector('.item-list'), {
        animation: 150,
        onEnd: function (evt) {
            updateItemFormat();
            
            const itemIds = Array.from(document.querySelectorAll('.item-card'))
                .map(card => card.getAttribute('data-id'));
            
            htmx.ajax('POST', '/reorder', {
                target: '#reorder-result',
                swap: 'innerHTML',
                values: {ids: itemIds.join(',')}  // Join the array into a comma-separated string
            });
        }
    });

    function updateItemFormat() {
        const allItems = document.querySelectorAll('.item-card');
        allItems.forEach((item, index) => {
            item.classList.remove('long-item', 'short-item', 'link-item');
            if (index < LONG_ITEM_COUNT) {
                item.classList.add('long-item');
            } else if (index < LONG_ITEM_COUNT + SHORT_ITEM_COUNT) {
                item.classList.add('short-item');
            } else {
                item.classList.add('link-item');
            }
        });
    }

    // Initial format update
    updateItemFormat();
''', type='module')

app = FastHTML(hdrs=(picolink, pico_css, sortable_js))


@app.get("/")
def home():
    last_update = get_last_update_date()
    current_date = datetime.now().date()

    if not last_update or (current_date - last_update) >= timedelta(days=7):
        if current_date.weekday() == 4:  # 4 represents Friday (0 is Monday, 6 is Sunday)
            print("Updating items from Omnivore...")
            update_items_from_articles()
            last_update = current_date

    df = pd.DataFrame(items())
    df_sorted = df.sort_values('interest_score', ascending=False).reset_index(drop=True)

    LONG_ITEM_COUNT = 3
    SHORT_ITEM_COUNT = 4

    def create_item_card(title, url, long_summary, short_summary, index, item_id):
        class_name = "item-card"
        if index < LONG_ITEM_COUNT:
            class_name += " long-item"
        elif index < LONG_ITEM_COUNT + SHORT_ITEM_COUNT:
            class_name += " short-item"
        else:
            class_name += " link-item"

        return Li(
            Article(
                H3(A(title, href=url)),
                P(long_summary, cls="long-summary"),
                P(short_summary, cls="short-summary"),
                Footer(A("Read more", href=url, cls="secondary read-more")),
                cls=class_name,
                **{"data-id": item_id}
            )
        )

    item_cards = [
        create_item_card(
            row['title'],
            row['url'],
            row['long_summary'],
            row['short_summary'],
            i,
            row['id']
        ) for i, row in df_sorted.iterrows()
    ]

    # Get the latest newsletter summary
    latest_summary = newsletter_summaries(order_by='-date', limit=1)
    summary_content = latest_summary[0]['summary'] if latest_summary else "No newsletter summary available."

    page = Titled('Bedtime Reading',
        Main(
            Div(
                Div(
                    P(f"Last updated on: {last_update.strftime('%Y-%m-%d') if last_update else 'Never'}", cls="last-updated"),
                    Div(summary_content, cls="newsletter-summary"),
                    Ul(*item_cards, cls="item-list"),
                    Div(id="reorder-result"),  # Add this line to handle HTMX updates
                    cls="items-container"
                ),
                cls="container"
            )
        )
    )

    return page

@app.post("/update")
async def update():
    current_date = datetime.now().date()
    update_items_from_articles()
    last_update.update({'date': current_date})
    return JSONResponse(content={"message": "Update completed successfully", "last_update": str(current_date)})

@app.post("/reorder")
async def reorder(request: Request, ids: str = Form(...)):
    new_order = ids.split(',')
    
    # Create comparison pairs
    for i, item_id in enumerate(new_order):
        for j in range(i+1, len(new_order)):
            comparisons.insert({
                'item1_id': int(item_id),
                'item2_id': int(new_order[j])
            })
    
    # Update interest scores
    for i, item_id in enumerate(new_order):
        items.update({'interest_score': len(new_order) - i}, int(item_id))
    
    return JSONResponse(content={"status": "success"})


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
    
    6
serve()
