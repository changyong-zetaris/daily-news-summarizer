"""Summarize fetched news articles using Groq API."""

import json
import os
import re
import time
import yaml
import requests

API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Base instructions. The Zetaris knowledge base (zetaris_knowledge_base.md) is
# appended at runtime so the LLM has rich product/ICP/competitor context when
# scoring leads.
BASE_PROMPT = """You are a strict sales intelligence analyst for Zetaris.

You will be given:
1. A reference KNOWLEDGE BASE describing Zetaris's product, capabilities, ICP, and lead qualification signals.
2. A single news article (title + snippet).

Your job: decide how relevant the article is for Zetaris sales/marketing intelligence.

SCORING RULES (use the Hot / Warm / Cold definitions and signal lists in the KNOWLEDGE BASE):
- "Hot": A specific named company is described with a concrete pain point that maps directly to a Zetaris capability (federated query, semantic layer, data silo break-up, data integration for AI, governance across heterogeneous sources, lakehouse modernisation, regulatory lineage, M&A consolidation, data mesh / data product programme).
- "Warm": Industry trend, survey, or generic problem piece that matches Zetaris's domain but no specific target company is identified.
- "Cold": Article is about AI/data in general but the core problem is NOT in Zetaris's domain — see the "Cold signals" and "Out-of-Domain" sections of the knowledge base.

IMPORTANT:
- Be strict. Most articles should be "Cold" or "Warm". "Hot" should be rare.
- If Zetaris is unlikely to help, say so plainly in `zetaris_relevance` with a brief reason.
- Do NOT invent companies, products, or pain points that are not in the article.

Respond in this exact JSON format:
{
  "summary": ["bullet 1", "bullet 2", "bullet 3"],
  "company": "Company name — Industry (or 'Not specified')",
  "pain_point": "The specific data problem (or 'Not directly relevant to data integration')",
  "zetaris_relevance": "How Zetaris could help (or 'Low relevance — [brief reason]')",
  "lead_score": "Hot" or "Warm" or "Cold"
}

Respond ONLY with valid JSON, no markdown or extra text."""


def load_knowledge_base() -> str:
    """Load the Zetaris knowledge base from the ZETARIS_KB environment variable.

    The KB is provided as a GitHub Secret in CI and exported manually for local
    runs (e.g., ``export ZETARIS_KB="$(cat zetaris_knowledge_base.md)"``).
    """
    kb = os.environ.get("ZETARIS_KB", "").strip()
    if not kb:
        raise RuntimeError(
            "ZETARIS_KB environment variable is not set. "
            'For local runs use: export ZETARIS_KB="$(cat zetaris_knowledge_base.md)"'
        )
    return kb


def build_system_prompt() -> str:
    """Compose the system prompt by appending the knowledge base to the base instructions."""
    kb = load_knowledge_base()
    return (
        f"{BASE_PROMPT}\n\n"
        "===== ZETARIS KNOWLEDGE BASE (reference) =====\n"
        f"{kb}\n"
        "===== END KNOWLEDGE BASE =====\n"
    )


MAX_RETRIES = 5


def summarize_article(api_key: str, model: str, system_prompt: str, article: dict) -> dict:
    """Send a single article to Groq API."""
    user_prompt = f"Title: {article['title']}\n\n{article['text']}"

    for attempt in range(MAX_RETRIES):
        resp = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 600,
                "temperature": 0.3,
            },
            timeout=120,
        )

        if resp.status_code == 429 or resp.status_code == 503:
            wait = 2 ** attempt * 5
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

    raise RuntimeError(f"Failed after {MAX_RETRIES} retries")


def main():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable is not set")

    with open("config.yml") as f:
        config = yaml.safe_load(f)
    model = config["settings"]["summary_model"]

    system_prompt = build_system_prompt()
    print(f"System prompt size: {len(system_prompt):,} chars")

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
                article["analysis"] = summarize_article(
                    api_key, model, system_prompt, article
                )
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
