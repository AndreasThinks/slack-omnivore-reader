import requests
import json
from datetime import datetime, timedelta
import os
import pytz 
import anthropic
import pandas as pd
from tqdm import tqdm
from dotenv import load_dotenv
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

load_dotenv()
db = database('data/items.db')

items = db.t.items
comparisons = db.t.comparisons
last_update = db.t.last_update
newsletter_summaries = db.t.newsletter_summaries

def get_last_update_date():
    result = last_update(order_by='-id', limit=1)
    return datetime.strptime(result[0]['update_date'], '%Y-%m-%d').date() if result else None

def set_last_update_date(date):
    last_update.insert({'update_date': date.strftime('%Y-%m-%d')})


def update_items_from_csv():
    df = pd.read_csv('summariser/item_summaries.csv')
    current_date = datetime.now().date()
    for _, row in df.iterrows():
        items.upsert({
            'id': row['id'],
            'title': row['title'],
            'url': row['url'],
            'long_summary': row['long_summary'],
            'short_summary': row['short_summary'],
            'interest_score': row['interest_score'],
            'added_date': current_date.strftime('%Y-%m-%d')
        })
    set_last_update_date(current_date)

def query_recent_omnivore_articles(days=14, limit=25):
    api_token = os.getenv("OMNIVORE_API_KEY")
    url = "https://api-prod.omnivore.app/api/graphql"
    
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
    
    variables = {"after": None, "first": limit}
    headers = {"Content-Type": "application/json", "Authorization": api_token}
    
    try:
        response = requests.post(url, json={"query": query, "variables": variables}, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        cutoff_date = datetime.now(pytz.utc) - timedelta(days=days)
        recent_articles = [
            {
                "title": article['node']['title'],
                "url": article['node']['url'],
                "content": article['node']['content']
            }
            for article in data['data']['search']['edges']
            if datetime.fromisoformat(article['node']['savedAt'].replace('Z', '+00:00')) > cutoff_date
        ]
        
        return recent_articles
    except requests.RequestException as e:
        print(f"Error querying Omnivore API: {e}")
        return []

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
    4. Condense the key points into a brief summary, keeping it between 4-7 lines long.
    5. Ensure your summary is factual while also sounding exciting and inspiring.
    6. Use language that engages the reader and encourages them to explore the full newsletter.
    7. Avoid using phrases like "In this newsletter" or "This edition covers" - instead, dive straight into the content.
    8. Make specific references to "this week" to emphasize the current nature of the information.

    Your summary should be written in a tone that is:
    - Professional yet approachable
    - Enthusiastic without being overly promotional
    - Informative and concise

    Please provide your summary within <summary> tags. Remember to keep it between 3-5 lines long, focusing on the most notable and exciting elements of this week's newsletter.
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
    
def generate_article_summary(title, url, content):
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    prompt = f"""
    Analyze the following article and provide a summary in JSON format:

    Title: {title}
    URL: {url}

    Content:
    {content[:1000]}  # Truncate content to avoid token limits

    Make sure your interest score is based on London based AI engineers, who are technically savy, and want to focus on exciting AI developments.

    Provide output in the following JSON format:
    {{
      "interest_score": [0-100],
      "short_summary": "[One-sentence summary]",
      "long_summary": "[2-3 sentence summary]"
    }}
    """
    
    try:
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

def process_articles():
    articles = query_recent_omnivore_articles()
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
                'added_date': datetime.now().strftime('%Y-%m-%d')
            })
    
    return processed_data

def update_items_from_articles(articles):
    current_date = datetime.now().date()
    for article in articles:
        items.upsert({
            'id': hash(article['url']),  # Use a hash of the URL as a unique identifier
            'title': article['title'],
            'url': article['url'],
            'content': article['content'],
            'long_summary': article['long_summary'],
            'short_summary': article['short_summary'],
            'interest_score': article['interest_score'],
            'added_date': current_date.strftime('%Y-%m-%d')
        })
    set_last_update_date(current_date)
    generate_newsletter_summary()

def generate_markdown_newsletter(num_long_summaries, num_short_summaries):
    df = pd.DataFrame(items())
    df_sorted = df.sort_values('interest_score', ascending=False).reset_index(drop=True)
    
    markdown_content = f"*This newsletter summarises articles that have been read and shared by i.AI in the past 14 days. Generated with help from Anthropic Haiku on {datetime.now().strftime('%Y-%m-%d')}*\n\n"
    
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

def create_newsletter(num_long_summaries=4, num_short_summaries=6):
    last_update = get_last_update_date()
    current_date = datetime.now().date()

    if not last_update or (current_date - last_update) >= timedelta(days=14):
        print("Fetching and processing new articles...")
        articles = process_articles()
        update_items_from_articles(articles)
    else:
        print("Using existing articles from database...")

    newsletter_content = generate_markdown_newsletter(num_long_summaries, num_short_summaries)
    
    summary = generate_newsletter_summary()
    summary = summary.replace('<summary>', '').replace('</summary>', '').strip()
    
    create_quarto_document(summary, newsletter_content)
    render_quarto_to_html()
    
    print("Self-contained newsletter generated and saved as newsletter.html")

if __name__ == "__main__":
    create_newsletter()

if items not in db.t:
    items.create(id=int, title=str, url=str, content=str, long_summary=str, short_summary=str, interest_score=float, added_date=str, pk='id')
    comparisons.create(id=int, item1_id=int, item2_id=int, pk='id')
    last_update.create(id=int, update_date=str, pk='id')
    newsletter_summaries.create(id=int, date=str, summary=str, pk='id')
    create_newsletter()