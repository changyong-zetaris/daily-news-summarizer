"""Generate a static HTML report and archive daily data."""

import json
import os
from datetime import datetime, timezone, timedelta
from jinja2 import Environment, FileSystemLoader


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
    generated_at = datetime.now(aest).strftime("%Y-%m-%d %H:%M AEDT")
    today = datetime.now(aest).strftime("%Y-%m-%d")

    metadata["generated_at"] = generated_at

    # Archive daily data
    os.makedirs("docs/data", exist_ok=True)
    archive = {"_metadata": metadata, "keywords": keywords_data}
    with open(f"docs/data/{today}.json", "w") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)

    # Build date index from archived files
    dates = sorted(
        [f.replace(".json", "") for f in os.listdir("docs/data")
         if f.endswith(".json") and f != "index.json"],
        reverse=True,
    )
    with open("docs/data/index.json", "w") as f:
        json.dump(dates, f)

    # Count stats for logging
    total = sum(len(arts) for arts in keywords_data.values())

    # Render HTML with embedded JSON data
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("index.html.j2")

    html = template.render(
        news_json=json.dumps(archive, ensure_ascii=False),
        dates_json=json.dumps(dates),
        current_date=today,
    )

    with open("docs/index.html", "w") as f:
        f.write(html)

    print(f"Generated docs/index.html — {total} articles")
    print(f"Archived to docs/data/{today}.json")
    print(f"Historical dates available: {len(dates)}")


if __name__ == "__main__":
    main()
