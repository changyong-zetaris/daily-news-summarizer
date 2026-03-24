"""Fetch news articles from Google News RSS feeds."""

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import yaml
import requests

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"


def search_news(keyword: str, num_results: int) -> list[dict]:
    """Fetch news articles from Google News RSS for a keyword."""
    resp = requests.get(
        GOOGLE_NEWS_RSS,
        params={
            "q": keyword,
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
        },
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    articles = []

    for item in root.findall(".//item"):
        if len(articles) >= num_results:
            break

        title = item.findtext("title", "")
        link = item.findtext("link", "")
        pub_date = item.findtext("pubDate", "")
        source = item.findtext("source", "")
        description = item.findtext("description", "")

        # Strip HTML tags from description
        if "<" in description:
            description = re.sub(r"<[^>]+>", "", description).strip()

        # Parse pub_date to ISO format for filtering
        iso_date = ""
        if pub_date:
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(pub_date)
                iso_date = dt.strftime("%Y-%m-%d")
            except Exception:
                iso_date = ""

        articles.append({
            "title": title,
            "text": description,
            "url": link,
            "source": source,
            "date": pub_date,
            "iso_date": iso_date,
        })

    return articles


def load_keywords() -> list[str]:
    """Load keywords from SEARCH_KEYWORDS environment variable (comma-separated)."""
    raw = os.environ.get("SEARCH_KEYWORDS", "")
    if not raw:
        raise RuntimeError("SEARCH_KEYWORDS environment variable is not set")
    return [kw.strip() for kw in raw.split(",") if kw.strip()]


def main():
    keywords = load_keywords()
    print(f"Loaded {len(keywords)} keywords")

    with open("config.yml") as f:
        config = yaml.safe_load(f)

    num_results = config["settings"]["results_per_keyword"]
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    results = {
        "_metadata": {
            "fetched_at": fetched_at,
            "keyword_count": len(keywords),
        },
        "keywords": {},
    }

    for keyword in keywords:
        print(f"Searching: {keyword}")
        try:
            articles = search_news(keyword, num_results)
            results["keywords"][keyword] = articles
            print(f"  => {len(articles)} articles found")
            for art in articles:
                print(f"     - {art['title'][:80]}")
            time.sleep(1)
        except Exception as e:
            print(f"  Error: {e}")
            results["keywords"][keyword] = []

    with open("docs/news_raw.json", "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    total = sum(len(v) for v in results["keywords"].values())
    results["_metadata"]["article_count"] = total
    print(f"\nTotal articles fetched: {total}")


if __name__ == "__main__":
    main()
