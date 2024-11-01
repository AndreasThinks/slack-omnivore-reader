import requests
import json
from datetime import datetime, timedelta
import os
import pytz 
import anthropic
import pandas as pd
from tqdm import tqdm
from dotenv import load_dotenv

import subprocess
from fasthtml.common import database

from config import settings

minimum_item_count = settings.MINIMUM_ITEM_COUNT
maximum_item_count = settings.MAXIMUM_ITEM_COUNT
days_to_check = settings.MIN_DAYS_TO_CHECK
maximum_days_to_check = settings.MAXIMUM_DAYS_TO_CHECK
EXAMPLE_SCORES_COUNT = 5  # Number of recent scores to include as examples

load_dotenv()
db = database('data/items.db')

items = db.t.items
comparisons = db.t.comparisons
last_update = db.t.last_update
newsletter_summaries = db.t.newsletter_summaries

if items not in db.t:
    items.create(id=int, title=str, url=str, content=str, long_summary=str, short_summary=str, interest_score=float, saved_at=str, pk='id')
    comparisons.create(id=int, winning_id=int, losing_id=int, pk='id')
    last_update.create(id=int, update_date=str, pk='id')
    newsletter_summaries.create(id=int, date=str, summary=str, pk='id')

def get_last_update_date():
    result = last_update(order_by='-id', limit=1)
    return datetime.strptime(result[0]['update_date'], '%Y-%m-%d').date() if result else None

def set_last_update_date(date):
    last_update.insert({'update_date': date.strftime('%Y-%m-%d')})

def get_existing_urls():
    """Get a set of all URLs currently in the database."""
    try:
        df = pd.DataFrame(items())
        return set(df['url'].values)
    except (KeyError, ValueError):
        return set()

def update_items_from_csv():
    df = pd.read_csv('summariser/item_summaries.csv')
    for _, row in df.iterrows():
        items.upsert({
            'id': row['id'],
            'title': row['title'],
            'url': row['url'],
            'long_summary': row['long_summary'],
            'short_summary': row['short_summary'],
            'interest_score': row['interest_score'],
            'saved_at': row.get('saved_at', datetime.now(pytz.utc).isoformat())  # Use provided saved_at or current time as fallback
        })
    set_last_update_date(datetime.now().date())

def query_recent_omnivore_articles(initial_days=None, limit=None):
    api_token = os.getenv("OMNIVORE_API_KEY")
    url = "https://api-prod.omnivore.app/api/graphql"
    
    if initial_days is None:
        initial_days = days_to_check
    if limit is None:
        limit = maximum_item_count
    
    query = """
    query RecentArticles($after: String, $first: Int) {
        search(after: $after, first: $first, query: "", includeContent: true) {
            ... on SearchSuccess {
                edges {
                    node {
                        id
                        title
                        savedAt
                        url
                        content
                    }
                }
                pageInfo {
                    hasNextPage
                    endCursor
                }
            }
            ... on SearchError {
                errorCodes
            }
        }
    }
    """
    
    variables = {"after": None, "first": limit * 2}  # Request more than needed to ensure we have enough after filtering
    headers = {"Content-Type": "application/json", "Authorization": api_token}
    
    try:
        # Get existing URLs to avoid duplicates
        existing_urls = get_existing_urls()
        
        response = requests.post(url, json={"query": query, "variables": variables}, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        cutoff_date = datetime.now(pytz.utc) - timedelta(days=initial_days)
        
        # Get all articles with their saved dates, excluding ones we already have
        articles = [
            {
                "title": article['node']['title'],
                "url": article['node']['url'],
                "content": article['node']['content'],
                "saved_at": article['node']['savedAt']  # Keep the ISO format string from Omnivore
            }
            for article in data['data']['search']['edges']
            if article['node']['url'] not in existing_urls
        ]
        
        if not articles:
            print("No new articles found that aren't already in the database.")
            return []
        
        # Sort articles by date, newest first
        articles.sort(key=lambda x: x['saved_at'], reverse=True)
        
        # First try to get articles within the initial days period
        filtered_articles = [
            article for article in articles
            if datetime.fromisoformat(article['saved_at'].replace('Z', '+00:00')) > cutoff_date
        ]
        
        # If we don't have enough articles, gradually increase the date range
        current_days = initial_days
        while len(filtered_articles) < minimum_item_count and current_days < maximum_days_to_check:
            current_days += days_to_check
            cutoff_date = datetime.now(pytz.utc) - timedelta(days=current_days)
            filtered_articles = [
                article for article in articles
                if datetime.fromisoformat(article['saved_at'].replace('Z', '+00:00')) > cutoff_date
            ]
            
            # If we've gone through all available articles and still don't have enough,
            # make another API call with a larger limit
            if len(filtered_articles) < minimum_item_count and len(filtered_articles) == len(articles):
                variables["first"] = variables["first"] * 2  # Double the number of articles requested
                response = requests.post(url, json={"query": query, "variables": variables}, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                # Get new articles, still excluding ones we already have
                new_articles = [
                    {
                        "title": article['node']['title'],
                        "url": article['node']['url'],
                        "content": article['node']['content'],
                        "saved_at": article['node']['savedAt']  # Keep the ISO format string from Omnivore
                    }
                    for article in data['data']['search']['edges']
                    if article['node']['url'] not in existing_urls
                ]
                
                if not new_articles:
                    break
                
                articles.extend(new_articles)
                articles.sort(key=lambda x: x['saved_at'], reverse=True)
                
                filtered_articles = [
                    article for article in articles
                    if datetime.fromisoformat(article['saved_at'].replace('Z', '+00:00')) > cutoff_date
                ]
        
        # If we still don't have enough new articles after reaching maximum_days_to_check,
        # just take what we have
        if len(filtered_articles) < minimum_item_count:
            print(f"Warning: Only found {len(filtered_articles)} new articles")
            return filtered_articles
        
        # Limit to maximum_item_count while keeping the most recent articles
        return filtered_articles[:maximum_item_count]
        
    except requests.RequestException as e:
        print(f"Error querying Omnivore API: {e}")
        return []
    
def generate_article_summary(title, url, content, num_comparisons=4):
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    # Get recent article examples with their scores
    try:
        df = pd.DataFrame(items())
        df_sorted = df.sort_values('interest_score', ascending=False).reset_index(drop=True)
        recent_examples = df_sorted.head(EXAMPLE_SCORES_COUNT)
        example_text = "\n\nHere are some recent articles and their interest scores for reference:\n"
        for _, example in recent_examples.iterrows():
            example_text += f"\nTitle: {example['title']}\nScore: {example['interest_score']}\nSummary: {example['short_summary'][:100]}...\n"
    except (KeyError, ValueError):
        # If no examples are available, provide an empty string
        example_text = ""

    comparison_data = comparisons(order_by='-id', limit=num_comparisons)
    comparison_examples = ""
    if len(comparison_data) > 0:
        comparison_examples += "\n\nHere are some examples of article comparisons:\n"
        for comparison in comparison_data:
            winning_item = items[comparison['winning_id']]
            losing_item = items[comparison['losing_id']]
            comparison_examples += f"\nPreferred article:\nTitle: {winning_item['title']}\n{winning_item['short_summary'][:100]}...\n\nOver this article:\nTitle: {losing_item['title']}\n{losing_item['short_summary'][:100]}...\n"

    prompt = f"""
    Analyze the following article and provide a summary in JSON format:

    Title: {title}
    URL: {url}

    Content:
    {content[:1500]}  # Increased content limit for better context

    {example_text}
    {comparison_examples}

    Make sure your interest score is based on London based AI engineers, who are technically savvy, and want to focus on exciting AI developments. The score should be consistent with the example scores provided.

    For the summaries:
    - The short_summary should be 2-3 sentences that capture the main points and key insights
    - The long_summary should be 5-6 sentences that provide a comprehensive overview, including context, key findings, and implications

    Provide output in the following JSON format:
    {{
      "interest_score": [0-100],
      "short_summary": "[2-3 sentence summary]",
      "long_summary": "[5-6 sentence summary]"
    }}
    """
    
    try:
        print('Generating summary...')
        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        return json.loads(message.content[0].text)
    except Exception as e:
        print(f"Error generating summary for {title}: {e}")
        return None


def generate_newsletter_summary():
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    # Query the database for relevant articles
    df = pd.DataFrame(items())
    df_sorted = df.sort_values('interest_score', ascending=False).reset_index(drop=True)
    
    # Prepare the content for the summary
    articles_content = ""
    for _, article in df_sorted.iterrows():
        articles_content += f"Title: {article['title']}\n"
        articles_content += f"URL: {article['url']}\n"
        articles_content += f"Summary: {article['long_summary']}\n\n"

    prompt = f"""
    You are a skilled assistant tasked with creating an engaging summary for a newsletter. Your goal is to produce a concise, compelling summary that highlights the most noteworthy articles and exciting news from this week's newsletter content.
    Here are the articles for this week's newsletter:
    <articles>
    {articles_content[:3000]}  # Truncate to avoid token limits
    </articles>

    To create an effective summary, please follow these steps:

    1. Carefully read through the provided article information.
    2. Identify the 3-5 most important and interesting articles based on their summaries and titles.
    3. Focus on information that would be most relevant and appealing to the newsletter's audience.
    4. Condense the key points into a brief summary, keeping it between 7-10 lines long.
    5. Ensure your summary is factual while also sounding exciting and inspiring.
    6. Use language that engages the reader and encourages them to explore the full newsletter.
    7. Avoid using phrases like "In this newsletter" or "This edition covers" - instead, dive straight into the content.
    8. Make specific references to "this week" to emphasize the current nature of the information.

    Your summary should be written in a tone that is:
    - Professional yet approachable
    - Enthusiastic without being overly promotional
    - Informative and concise

    Please provide your summary within <summary> tags. Remember to keep it between 7-10 lines long, focusing on the most notable and exciting elements of this week's newsletter.
    """
    
    try:
        message = client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=1000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        summary = message.content[0].text
        summary = summary.replace('<summary>', '').replace('</summary>', '').strip()
        
        # Save the summary to the database
        current_date = datetime.now().date().strftime('%Y-%m-%d')
        newsletter_summaries.insert({
            'date': current_date,
            'summary': summary
        })
        
        print(f"Newsletter summary for {current_date} saved to the database.")
        return summary
    except Exception as e:
        print(f"Error generating or saving newsletter summary: {e}")
        return ""


def process_articles():
    articles = query_recent_omnivore_articles()
    if not articles:
        print("No new articles to process")
        return []
        
    processed_data = []
    
    for article in tqdm(articles, desc="Processing articles"):
        summary = generate_article_summary(article['title'], article['url'], article['content'])
        if summary:
            processed_data.append({
                'title': article['title'],
                'url': article['url'],
                'content': article['content'],
                'interest_score': summary['interest_score'],
                'short_summary': summary['short_summary'],
                'long_summary': summary['long_summary'],
                'saved_at': article['saved_at']  # Use the original savedAt from Omnivore
            })
    
    return processed_data

def update_items_from_articles(articles):
    if not articles:
        print("No new articles to update in database")
        return
        
    for article in articles:
        items.upsert({
            'id': hash(article['url']),  # Use a hash of the URL as a unique identifier
            'title': article['title'],
            'url': article['url'],
            'content': article['content'],
            'long_summary': article['long_summary'],
            'short_summary': article['short_summary'],
            'interest_score': article['interest_score'],
            'saved_at': article['saved_at']  # Use the original savedAt from Omnivore
        })
    set_last_update_date(datetime.now().date())
    generate_newsletter_summary()


def generate_markdown_newsletter(num_long_summaries=None, num_short_summaries=None):
    if num_long_summaries is None:
        num_long_summaries = settings.NUMBER_OF_LONG_ARTICLES
    if num_short_summaries is None:
        num_short_summaries = settings.NUMBER_OF_SHORT_ARTICLES

    df = pd.DataFrame(items())
    df_sorted = df.sort_values('interest_score', ascending=False).reset_index(drop=True)
    
    markdown_content = f"*This newsletter summarises articles that have been read and shared by i.AI in the past {days_to_check} days. Generated with help from Anthropic Haiku on {datetime.now().strftime('%Y-%m-%d')}*\n\n"
    
    markdown_content += "## Featured Articles\n\n"
    for i in range(min(num_long_summaries, len(df_sorted))):
        article = df_sorted.iloc[i]
        markdown_content += f"### [{article['title']}]({article['url']})\n\n"
        markdown_content += f"{article['long_summary']}\n\n"
    
    markdown_content += "## Quick Reads\n\n"
    for i in range(num_long_summaries, num_long_summaries + num_short_summaries):
        if i < len(df_sorted):
            article = df_sorted.iloc[i]
            markdown_content += f"- **[{article['title']}]({article['url']})**: {article['short_summary']}\n\n"
    
    markdown_content += "## Also Worth Checking\n\n"
    for i in range(num_long_summaries + num_short_summaries, len(df_sorted)):
        article = df_sorted.iloc[i]
        markdown_content += f"- [{article['title']}]({article['url']})\n"
    
    return markdown_content

def create_quarto_document(summary, content):
    with open('newsletter_template.qmd', 'r') as f:
        template = f.read()
    
    quarto_content = template.replace('{{date}}', datetime.now().strftime('%Y-%m-%d'))
    quarto_content = quarto_content.replace('{{summary}}', summary)
    quarto_content = quarto_content.replace('{{content}}', content)
    
    with open('newsletter.qmd', 'w') as f:
        f.write(quarto_content)

def render_quarto_to_html():
    try:
        subprocess.run([
            'quarto', 'render', 'newsletter.qmd',
            '--to', 'html',
            '--embed-resources',
            '--standalone'
        ], check=True)
        print("Self-contained HTML newsletter generated successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error rendering Quarto document: {e}")

def create_newsletter(num_long_summaries=None, num_short_summaries=None):
    if num_long_summaries is None:
        num_long_summaries = settings.NUMBER_OF_LONG_ARTICLES
    if num_short_summaries is None:
        num_short_summaries = settings.NUMBER_OF_SHORT_ARTICLES

    last_update = get_last_update_date()
    current_date = datetime.now().date()

    try:
        df = pd.DataFrame(items())
        df_sorted = df.sort_values('interest_score', ascending=False).reset_index(drop=True)
        
        # Check if we have enough articles
        if len(df_sorted) >= minimum_item_count:
            print("Using existing articles from database...")
        else:
            print("Not enough articles in database, fetching new ones...")
            articles = process_articles()
            if articles:
                update_items_from_articles(articles)
            
    except KeyError:
        print("No items found in the database")
        articles = process_articles()
        if articles:
            update_items_from_articles(articles)

    if not last_update or (current_date - last_update) >= timedelta(days=maximum_days_to_check):
        print("Fetching and processing new articles...")
        articles = process_articles()
        if articles:
            update_items_from_articles(articles)

    newsletter_content = generate_markdown_newsletter(num_long_summaries, num_short_summaries)
    
    summary = generate_newsletter_summary()
    summary = summary.replace('<summary>', '').replace('</summary>', '').strip()
    
    create_quarto_document(summary, newsletter_content)
    render_quarto_to_html()
    
    print("Self-contained newsletter generated and saved as newsletter.html")

if __name__ == "__main__":
    if items not in db.t:
        items.create(id=int, title=str, url=str, content=str, long_summary=str, short_summary=str, interest_score=float, added_date=str, saved_at=str, pk='id')
        comparisons.create(id=int, winning_id=int, losing_id=int, pk='id')
        last_update.create(id=int, update_date=str, pk='id')
        newsletter_summaries.create(id=int, date=str, summary=str, pk='id')
    create_newsletter()