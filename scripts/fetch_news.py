"""Fetch news articles from Google News RSS and Reddit RSS feeds."""

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import yaml
import requests

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
REDDIT_RSS = "https://www.reddit.com/search.json"

# Channel types for tagging articles
CHANNEL_NEWS = "News"
CHANNEL_LINKEDIN = "LinkedIn"
CHANNEL_FACEBOOK = "Facebook"
CHANNEL_REDDIT = "Reddit"


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

        # Determine channel
        if site == "linkedin.com":
            channel = CHANNEL_LINKEDIN
        elif site == "facebook.com":
            channel = CHANNEL_FACEBOOK
        else:
            channel = CHANNEL_NEWS

        articles.append({
            "title": title,
            "text": description,
            "url": link,
            "source": source,
            "date": pub_date,
            "iso_date": parse_date(pub_date),
            "channel": channel,
        })

    return articles


def search_reddit(keyword: str, num_results: int) -> list[dict]:
    """Fetch posts from Reddit search."""
    resp = requests.get(
        REDDIT_RSS,
        params={"q": keyword, "sort": "relevance", "t": "week", "limit": num_results},
        headers={"User-Agent": "ZetarisSalesBot/1.0"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    articles = []
    for post in data.get("data", {}).get("children", []):
        d = post.get("data", {})
        created = d.get("created_utc", 0)
        iso_date = datetime.fromtimestamp(created, tz=timezone.utc).strftime("%Y-%m-%d") if created else ""
        pub_date = datetime.fromtimestamp(created, tz=timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z") if created else ""

        articles.append({
            "title": d.get("title", ""),
            "text": d.get("selftext", "")[:3000] or d.get("title", ""),
            "url": "https://www.reddit.com" + d.get("permalink", ""),
            "source": "r/" + d.get("subreddit", ""),
            "date": pub_date,
            "iso_date": iso_date,
            "channel": CHANNEL_REDDIT,
        })

    return articles


def load_keywords() -> list[str]:
    """Load keywords from SEARCH_KEYWORDS environment variable (comma-separated)."""
    raw = os.environ.get("SEARCH_KEYWORDS", "")
    if not raw:
        raise RuntimeError("SEARCH_KEYWORDS environment variable is not set")
    return [kw.strip() for kw in raw.split(",") if kw.strip()]


def fetch_all(keyword: str, num_results: int) -> list[dict]:
    """Fetch from all channels for a single keyword."""
    all_articles = []

    # Google News (general)
    print(f"  [News] ", end="")
    articles = search_google_news(keyword, num_results)
    print(f"{len(articles)} found")
    all_articles.extend(articles)
    time.sleep(1)

    # LinkedIn via Google
    print(f"  [LinkedIn] ", end="")
    articles = search_google_news(keyword, num_results, site="linkedin.com")
    print(f"{len(articles)} found")
    all_articles.extend(articles)
    time.sleep(1)

    # Facebook via Google
    print(f"  [Facebook] ", end="")
    articles = search_google_news(keyword, num_results, site="facebook.com")
    print(f"{len(articles)} found")
    all_articles.extend(articles)
    time.sleep(1)

    # Reddit
    print(f"  [Reddit] ", end="")
    articles = search_reddit(keyword, num_results)
    print(f"{len(articles)} found")
    all_articles.extend(articles)
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
