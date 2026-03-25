"""Archive daily news data as JSON. HTML is static and loads data via fetch."""

import json
import os
from datetime import datetime, timezone, timedelta


def main():
    data_path = "docs/news_data.json"
    if os.path.exists(data_path):
        with open(data_path) as f:
            data = json.load(f)
    else:
        data = {"_metadata": {}, "keywords": {}}

    metadata = data.get("_metadata", {})
    keywords_data = data.get("keywords", data)

    aest = timezone(timedelta(hours=11))
    now = datetime.now(aest)
    metadata["generated_at"] = now.strftime("%Y-%m-%d %H:%M AEDT")
    today = now.strftime("%Y-%m-%d")

    # Archive by date (overwrites same day)
    os.makedirs("docs/data", exist_ok=True)
    archive = {"_metadata": metadata, "keywords": keywords_data}
    archive_path = f"docs/data/{today}.json"
    with open(archive_path, "w") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)

    # Update date index
    dates = sorted(
        [f.replace(".json", "") for f in os.listdir("docs/data")
         if f.endswith(".json") and f != "index.json"],
        reverse=True,
    )
    with open("docs/data/index.json", "w") as f:
        json.dump(dates, f)

    total = sum(len(arts) for arts in keywords_data.values())
    print(f"Archived to {archive_path} — {total} articles")
    print(f"Historical dates available: {len(dates)}")


if __name__ == "__main__":
    main()
