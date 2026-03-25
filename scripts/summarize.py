"""Summarize fetched news articles using HuggingFace Inference API."""

import json
import os
import re
import time
import yaml
import requests

HF_API_URL = "https://api-inference.huggingface.co/v1/chat/completions"

SYSTEM_PROMPT = """You are a strict sales intelligence analyst for Zetaris, a data platform company.

Zetaris provides a SEMANTIC LAYER that solves these SPECIFIC problems:
- Data silos: organizations that cannot query across multiple distributed databases/systems
- Data integration: companies struggling to unify data from heterogeneous sources (SQL, NoSQL, APIs, files)
- Data quality/cleaning: businesses wasting time preparing and cleaning data before analysis or AI training
- Federated queries: need to query data across systems WITHOUT moving or copying it

SCORING RULES — be strict:
- "Hot": Article describes a SPECIFIC company experiencing data silos, data integration failures, or data quality issues that directly block their AI/analytics projects. The company could be a Zetaris customer.
- "Warm": Article discusses data integration/quality challenges in general terms, mentions an industry trend. No specific company identified but the problem domain matches.
- "Cold": Article mentions data/AI but the core problem is NOT about data silos, integration, or quality. Examples of Cold: AI ethics, AI job displacement, VC funding opinions, AI model comparisons, general AI hype, cybersecurity, privacy regulations.

IMPORTANT: Most articles should be "Cold" or "Warm". "Hot" should be rare — only when a real company is described with a real data integration/silo/quality problem.

Respond in this exact JSON format:
{
  "summary": ["bullet 1", "bullet 2", "bullet 3"],
  "company": "Company name — Industry (or 'Not specified')",
  "pain_point": "The specific data problem (or 'Not directly relevant to data integration')",
  "zetaris_relevance": "How Zetaris could help (or 'Low relevance — [brief reason]')",
  "lead_score": "Hot" or "Warm" or "Cold"
}

Respond ONLY with valid JSON, no markdown or extra text."""

MAX_RETRIES = 3


def summarize_article(api_key: str, model: str, article: dict) -> dict:
    """Send a single article to HuggingFace Inference API."""
    user_prompt = f"Title: {article['title']}\n\n{article['text']}"

    for attempt in range(MAX_RETRIES):
        resp = requests.post(
            HF_API_URL,
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
            timeout=120,
        )

        if resp.status_code == 429 or resp.status_code == 503:
            wait = 2 ** attempt * 10
            print(f"    Rate limited/loading, waiting {wait}s (attempt {attempt + 1}/{MAX_RETRIES})")
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

    raise RuntimeError(f"Failed after {MAX_RETRIES} retries")


def main():
    api_key = os.environ.get("HF_TOKEN")
    if not api_key:
        raise RuntimeError("HF_TOKEN environment variable is not set")

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
