from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from crawler import crawl_prices, load_config


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
JSON_PATH = DATA_DIR / "flights.json"
CSV_PATH = DATA_DIR / "flights.csv"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_outputs(items: list[dict], config: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    items = sorted(items, key=lambda item: (item["route"], item["travel_date"]))
    active_sources = sorted({item.get("source", "unknown") for item in items})
    payload = {
        "generated_at": utc_now(),
        "source": ", ".join(active_sources),
        "currency": config.get("currency", "TWD"),
        "routes": config.get("routes", []),
        "items": [
            {
                "route": item["route"],
                "travel_date": item["travel_date"],
                "price": int(item["price"]),
                "currency": item.get("currency", config.get("currency", "TWD")),
                "source": item.get("source", "unknown"),
                "fetched_at": item.get("fetched_at"),
            }
            for item in items
        ],
    }
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["route", "travel_date", "price", "currency", "source", "fetched_at"],
        )
        writer.writeheader()
        writer.writerows(payload["items"])


def main() -> None:
    config = load_config()
    items = crawl_prices(config)
    write_outputs(items, config)
    print(f"Wrote {len(items)} records")
    print(f"Wrote {JSON_PATH}")
    print(f"Wrote {CSV_PATH}")


if __name__ == "__main__":
    main()
