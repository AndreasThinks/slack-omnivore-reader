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


load_dotenv()

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

def generate_article_summary(title, url, content):
    client = anthropic.Anthropic()
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
                'interest_score': summary['interest_score'],
                'short_summary': summary['short_summary'],
                'long_summary': summary['long_summary']
            })
    
    df = pd.DataFrame(processed_data)
    df.to_csv('article_summaries.csv', index=False)
    return df

def generate_markdown_newsletter(df, num_long_summaries, num_short_summaries):
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

def generate_newsletter_summary(newsletter_content):
    client = anthropic.Anthropic()
    prompt = f"""
    You are a skilled assistant tasked with creating an engaging summary for a newsletter. Your goal is to produce a concise, compelling summary that highlights the most noteworthy articles and exciting news from this week's newsletter content.
    Here is the content of this week's newsletter:
    <newsletter>
    {newsletter_content}  # Truncate to avoid token limits
    </newsletter>

    To create an effective summary, please follow these steps:\n\n1. Carefully read through the entire newsletter content.\n2. Identify the 3-5 most important and interesting articles, news items, or announcements.\n3. Focus on information that would be most relevant and appealing to the newsletter's audience.\n4. Condense the key points into a brief summary, keeping it between 4-7 lines long.\n5. Ensure your summary is factual while also sounding exciting and inspiring.\n6. Use language that engages the reader and encourages them to explore the full newsletter.\n7. Avoid using phrases like \"In this newsletter\" or \"This edition covers\" - instead, dive straight into the content.\n8. Make specific references to \"this week\" to emphasize the current nature of the information.\n\nYour summary should be written in a tone that is:\n- Professional yet approachable\n- Enthusiastic without being overly promotional\n- Informative and concise\n\nPlease provide your summary within <summary> tags. Remember to keep it between 3-5 lines long, focusing on the most notable and exciting elements of this week's newsletter."
    """
    
    try:
        message = client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=1000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except Exception as e:
        print(f"Error generating newsletter summary: {e}")
        return ""


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
    df = process_articles()
    newsletter_content = generate_markdown_newsletter(df, num_long_summaries, num_short_summaries)
    
    summary = generate_newsletter_summary(newsletter_content)
    summary = summary.replace('<summary>', '').replace('</summary>', '').strip()
    
    create_quarto_document(summary, newsletter_content)
    render_quarto_to_html()
    
    print("Self-contained newsletter generated and saved as newsletter.html")

if __name__ == "__main__":
    create_newsletter()