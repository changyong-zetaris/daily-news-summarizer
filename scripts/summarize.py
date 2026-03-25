"""Summarize fetched news articles using Llama 3.1 8B via Groq API."""

import json
import os
import re
import time
import yaml
import requests

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """You are a sales intelligence analyst for Zetaris, a data platform company.
Zetaris provides a semantic layer that enables:
- Integration of distributed/siloed data without moving it
- Easy data cleaning tailored to business models
- Federated queries across heterogeneous data sources

For each news article, analyze it from a sales perspective and respond in this exact JSON format:
{
  "summary": ["bullet 1", "bullet 2", "bullet 3"],
  "company": "Company name — Industry (or 'Not specified')",
  "pain_point": "The specific data problem described",
  "zetaris_relevance": "1-2 sentences on how Zetaris could solve this",
  "lead_score": "Hot" or "Warm" or "Cold"
}

Respond ONLY with valid JSON, no markdown or extra text."""

MAX_RETRIES = 3


def summarize_article(api_key: str, model: str, article: dict) -> dict:
    """Send a single article to Groq API with retry on rate limit."""
    user_prompt = f"Title: {article['title']}\n\n{article['text']}"

    for attempt in range(MAX_RETRIES):
        resp = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 600,
                "temperature": 0.3,
            },
            timeout=60,
        )

        if resp.status_code == 429:
            wait = 2 ** attempt * 5  # 5s, 10s, 20s
            print(f"    Rate limited, waiting {wait}s (attempt {attempt + 1}/{MAX_RETRIES})")
            time.sleep(wait)
            continue

        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", content)
            if match:
                return json.loads(match.group())
            return {
                "summary": [content[:200]],
                "company": "Not specified",
                "pain_point": "Unknown",
                "zetaris_relevance": "",
                "lead_score": "Cold",
            }

    raise RuntimeError(f"Rate limited after {MAX_RETRIES} retries")


def main():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable is not set")

    with open("config.yml") as f:
        config = yaml.safe_load(f)
    model = config["settings"]["summary_model"]

    with open("docs/news_raw.json") as f:
        raw = json.load(f)

    metadata = raw.get("_metadata", {})
    keywords_data = raw.get("keywords", raw)

    total = sum(len(articles) for articles in keywords_data.values())
    processed = 0

    for keyword, articles in keywords_data.items():
        print(f"\nSummarizing: {keyword}")
        for article in articles:
            processed += 1
            print(f"  [{processed}/{total}] {article['title'][:60]}...")
            try:
                article["analysis"] = summarize_article(api_key, model, article)
                time.sleep(2)
            except Exception as e:
                print(f"    Error: {e}")
                article["analysis"] = {
                    "summary": ["Analysis unavailable due to API error."],
                    "company": "Not specified",
                    "pain_point": "Unknown",
                    "zetaris_relevance": "",
                    "lead_score": "Cold",
                }

    output = {"_metadata": metadata, "keywords": keywords_data}

    with open("docs/news_data.json", "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nDone. {processed} articles analyzed.")


if __name__ == "__main__":
    main()
