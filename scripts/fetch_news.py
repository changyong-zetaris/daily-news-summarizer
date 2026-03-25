"""Fetch news articles from Google News RSS and Reddit RSS feeds."""

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import yaml
import requests

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"


def parse_date(pub_date: str) -> str:
    """Parse various date formats to ISO date string."""
    if not pub_date:
        return ""
    try:
        dt = parsedate_to_datetime(pub_date)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return ""


def search_google_news(keyword: str, num_results: int, site: str = "") -> list[dict]:
    """Fetch articles from Google News RSS, optionally filtered by site."""
    query = f"{keyword} site:{site}" if site else keyword
    query += " when:1y"  # Restrict to past 1 year

    resp = requests.get(
        GOOGLE_NEWS_RSS,
        params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
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

        if "<" in description:
            description = re.sub(r"<[^>]+>", "", description).strip()

        # Skip articles older than 1 year
        iso_date = parse_date(pub_date)
        if iso_date:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")
            if iso_date < cutoff:
                continue

        articles.append({
            "title": title,
            "text": description,
            "url": link,
            "source": source,
            "date": pub_date,
            "iso_date": iso_date,
            "channel": "News",
        })

    return articles


def load_keywords() -> list[str]:
    """Load keywords from SEARCH_KEYWORDS environment variable (comma-separated)."""
    raw = os.environ.get("SEARCH_KEYWORDS", "")
    if not raw:
        raise RuntimeError("SEARCH_KEYWORDS environment variable is not set")
    return [kw.strip() for kw in raw.split(",") if kw.strip()]


CHANNELS = [
    {"name": "News",     "site": ""},
    {"name": "LinkedIn", "site": "linkedin.com"},
    {"name": "Facebook", "site": "facebook.com"},
    {"name": "Reddit",   "site": "reddit.com"},
    {"name": "Medium",   "site": "medium.com"},
    {"name": "X",        "site": "twitter.com"},
    {"name": "YouTube",  "site": "youtube.com"},
]


def fetch_all(keyword: str, num_results: int) -> list[dict]:
    """Fetch from all channels for a single keyword."""
    all_articles = []

    for ch in CHANNELS:
        print(f"  [{ch['name']}] ", end="")
        try:
            articles = search_google_news(keyword, num_results, site=ch["site"])
            # Override channel tag
            for art in articles:
                art["channel"] = ch["name"]
            print(f"{len(articles)} found")
            all_articles.extend(articles)
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(1)

    return all_articles


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
        print(f"\nSearching: {keyword}")
        try:
            articles = fetch_all(keyword, num_results)
            results["keywords"][keyword] = articles
            for art in articles:
                print(f"     [{art['channel']}] {art['title'][:70]}")
        except Exception as e:
            print(f"  Error: {e}")
            results["keywords"][keyword] = []

    with open("docs/news_raw.json", "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    total = sum(len(v) for v in results["keywords"].values())
    results["_metadata"]["article_count"] = total

    # Channel breakdown
    channels = {}
    for arts in results["keywords"].values():
        for a in arts:
            ch = a.get("channel", "News")
            channels[ch] = channels.get(ch, 0) + 1

    print(f"\nTotal articles fetched: {total}")
    for ch, count in sorted(channels.items()):
        print(f"  {ch}: {count}")


if __name__ == "__main__":
    main()
