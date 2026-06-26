from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from airline_rules import enrich_offer_with_airline_rule, load_airline_rules, public_registry
from crawler import build_change_overlays, crawl_static_schedule, crawl_tdx_fids, crawl_ticket_offers, load_config
from lookups import load_lookups, public_lookups


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
JSON_PATH = DATA_DIR / "flights.json"
CSV_PATH = DATA_DIR / "flights.csv"
OFFERS_JSON_PATH = DATA_DIR / "offers.json"
OFFERS_CSV_PATH = DATA_DIR / "offers.csv"
SCHEDULE_JSON_PATH = DATA_DIR / "schedule.json"
SCHEDULE_CSV_PATH = DATA_DIR / "schedule.csv"
CHANGES_JSON_PATH = DATA_DIR / "changes.json"
CHANGES_CSV_PATH = DATA_DIR / "changes.csv"


FIELDNAMES = [
    "id",
    "flight_date",
    "direction",
    "airport",
    "airport_name",
    "flight_number",
    "airline_id",
    "airline_name",
    "airline_name_zh",
    "airline_name_en",
    "departure_airport",
    "departure_airport_name",
    "departure_airport_name_zh",
    "arrival_airport",
    "arrival_airport_name",
    "arrival_airport_name_zh",
    "scheduled_time",
    "estimated_time",
    "actual_time",
    "terminal",
    "gate",
    "remark",
    "status_code",
    "source",
    "fetched_at",
]

OFFER_FIELDNAMES = [
    "id",
    "route",
    "origin",
    "origin_name",
    "origin_name_zh",
    "destination",
    "destination_name",
    "destination_name_zh",
    "departure_date",
    "price",
    "currency",
    "flight_number",
    "airline_id",
    "airline_name",
    "airline_name_zh",
    "airline_name_en",
    "departure_time",
    "arrival_time",
    "duration_minutes",
    "transfer_count",
    "baggage_checked_weight_kg",
    "baggage_checked_pieces",
    "baggage_carry_on_weight_kg",
    "baggage_text",
    "fare_brand",
    "booking_url",
    "airline_rule_status",
    "airline_rule_source_url",
    "change_rule",
    "refund_rule",
    "no_show_rule",
    "source",
    "fetched_at",
]

SCHEDULE_FIELDNAMES = [
    "schedule_id",
    "route",
    "origin",
    "origin_name",
    "origin_name_zh",
    "destination",
    "destination_name",
    "destination_name_zh",
    "flight_date",
    "weekday",
    "airline_id",
    "airline_name",
    "airline_name_zh",
    "airline_name_en",
    "flight_number",
    "departure_time",
    "arrival_time",
    "duration_minutes",
    "transfer_count",
    "baseline_price",
    "baseline_currency",
    "baseline_checked_baggage_kg",
    "baseline_checked_baggage_pieces",
    "baseline_carry_on_kg",
    "source",
    "fetched_at",
]

CHANGE_FIELDNAMES = [
    "change_id",
    "change_type",
    "route",
    "flight_date",
    "flight_number",
    "airline_id",
    "airline_name",
    "airline_name_zh",
    "airline_name_en",
    "price",
    "currency",
    "baggage_checked_weight_kg",
    "baggage_checked_pieces",
    "baggage_carry_on_weight_kg",
    "transfer_count",
    "booking_url",
    "changed_fields",
    "source",
    "fetched_at",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_table(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in fieldnames} for row in rows])


def write_outputs(items: list[dict], schedule: list[dict], offers: list[dict], config: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    airline_registry = load_airline_rules()
    lookup_registry = load_lookups()
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
    enriched_offers = [enrich_offer_with_airline_rule(offer, airline_registry) for offer in offers]
    changes = build_change_overlays(schedule, enriched_offers)
    enriched_offers = sorted(
        enriched_offers,
        key=lambda offer: (
            offer.get("departure_date", ""),
            offer.get("route", ""),
            int(offer.get("price") or 0),
            offer.get("flight_number", ""),
        ),
    )
    offer_sources = sorted({offer.get("source", "unknown") for offer in enriched_offers})
    payload = {
        "generated_at": utc_now(),
        "source": ", ".join(active_sources),
        "dataset": "TDX Air FIDS Airport Departure/Arrival",
        "airports": config.get("airports", []),
        "directions": ["departure", "arrival"],
        "lookups": public_lookups(lookup_registry),
        "airline_rules": public_registry(airline_registry),
        "items": [{field: item.get(field, "") for field in FIELDNAMES} for item in items],
    }
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(payload["items"])

    schedule_payload = {
        "generated_at": utc_now(),
        "source": ", ".join(sorted({row.get("source", "unknown") for row in schedule})),
        "dataset": "Fixed Flight Schedule",
        "routes": config.get("offer_routes", []),
        "lookups": public_lookups(lookup_registry),
        "airline_rules": public_registry(airline_registry),
        "standard_fields": SCHEDULE_FIELDNAMES,
        "items": [{field: row.get(field, "") for field in SCHEDULE_FIELDNAMES} for row in schedule],
    }
    SCHEDULE_JSON_PATH.write_text(json.dumps(schedule_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_table(SCHEDULE_CSV_PATH, schedule, SCHEDULE_FIELDNAMES)

    changes_payload = {
        "generated_at": utc_now(),
        "source": ", ".join(sorted({row.get("source", "unknown") for row in changes})),
        "dataset": "Schedule Change Overlay",
        "routes": config.get("offer_routes", []),
        "standard_fields": CHANGE_FIELDNAMES,
        "items": [{field: row.get(field, "") for field in CHANGE_FIELDNAMES} for row in changes],
    }
    CHANGES_JSON_PATH.write_text(json.dumps(changes_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_table(CHANGES_CSV_PATH, changes, CHANGE_FIELDNAMES)

    offer_payload = {
        "generated_at": utc_now(),
        "source": ", ".join(offer_sources),
        "dataset": "Ticket Offers",
        "routes": config.get("offer_routes", []),
        "lookups": public_lookups(lookup_registry),
        "airline_rules": public_registry(airline_registry),
        "standard_fields": OFFER_FIELDNAMES,
        "items": [{field: offer.get(field, "") for field in OFFER_FIELDNAMES} for offer in enriched_offers],
    }
    OFFERS_JSON_PATH.write_text(json.dumps(offer_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with OFFERS_CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OFFER_FIELDNAMES)
        writer.writeheader()
        writer.writerows(offer_payload["items"])


def main() -> None:
    config = load_config()
    items = crawl_tdx_fids(config) if config.get("enable_live_fids", False) else []
    schedule = crawl_static_schedule(config)
    offers = crawl_ticket_offers(config)
    write_outputs(items, schedule, offers, config)
    print(f"Wrote {len(items)} flight records")
    print(f"Wrote {len(schedule)} fixed schedule records")
    print(f"Wrote {len(offers)} ticket offers")
    print(f"Wrote {JSON_PATH}")
    print(f"Wrote {CSV_PATH}")
    print(f"Wrote {OFFERS_JSON_PATH}")
    print(f"Wrote {OFFERS_CSV_PATH}")
    print(f"Wrote {SCHEDULE_JSON_PATH}")
    print(f"Wrote {SCHEDULE_CSV_PATH}")
    print(f"Wrote {CHANGES_JSON_PATH}")
    print(f"Wrote {CHANGES_CSV_PATH}")


if __name__ == "__main__":
    main()
