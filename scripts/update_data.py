from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from crawler import crawl_tdx_fids, load_config


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
JSON_PATH = DATA_DIR / "flights.json"
CSV_PATH = DATA_DIR / "flights.csv"


FIELDNAMES = [
    "id",
    "flight_date",
    "direction",
    "airport",
    "flight_number",
    "airline_id",
    "airline_name",
    "departure_airport",
    "departure_airport_name",
    "arrival_airport",
    "arrival_airport_name",
    "scheduled_time",
    "estimated_time",
    "actual_time",
    "terminal",
    "gate",
    "remark",
    "source",
    "fetched_at",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_outputs(items: list[dict], config: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    items = sorted(
        items,
        key=lambda item: (
            item.get("flight_date", ""),
            item.get("airport", ""),
            item.get("direction", ""),
            item.get("scheduled_time", ""),
            item.get("flight_number", ""),
        ),
    )
    active_sources = sorted({item.get("source", "unknown") for item in items})
    payload = {
        "generated_at": utc_now(),
        "source": ", ".join(active_sources),
        "dataset": "TDX Air FIDS Airport Departure/Arrival",
        "airports": config.get("airports", []),
        "directions": ["departure", "arrival"],
        "items": [{field: item.get(field, "") for field in FIELDNAMES} for item in items],
    }
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(payload["items"])


def main() -> None:
    config = load_config()
    items = crawl_tdx_fids(config)
    write_outputs(items, config)
    print(f"Wrote {len(items)} flight records")
    print(f"Wrote {JSON_PATH}")
    print(f"Wrote {CSV_PATH}")


if __name__ == "__main__":
    main()
