from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from airline_rules import enrich_offer_with_airline_rule, load_airline_rules, merged_rule
from crawler import build_change_overlays, crawl_static_schedule, crawl_tdx_fids, crawl_ticket_offers, load_config
from lookups import load_lookups


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
AIRLINE_ASSET_DIR = ROOT / "assets" / "airlines"
JSON_PATH = DATA_DIR / "flights.json"
CSV_PATH = DATA_DIR / "flights.csv"
OFFERS_JSON_PATH = DATA_DIR / "offers.json"
OFFERS_CSV_PATH = DATA_DIR / "offers.csv"
SCHEDULE_JSON_PATH = DATA_DIR / "schedule.json"
SCHEDULE_CSV_PATH = DATA_DIR / "schedule.csv"
CHANGES_JSON_PATH = DATA_DIR / "changes.json"
CHANGES_CSV_PATH = DATA_DIR / "changes.csv"
TABLES_JSON_PATH = DATA_DIR / "tables.json"
TABLES_CSV_PATH = DATA_DIR / "tables.csv"
AIRLINE_ICON_SOURCE = "https://images.kiwi.com/airlines/64/{code}.png"


FIELDNAMES = [
    "id",
    "flight_date",
    "direction",
    "airport",
    "flight_number",
    "airline_id",
    "departure_airport",
    "arrival_airport",
    "scheduled_time",
    "estimated_time",
    "actual_time",
    "terminal",
    "gate",
    "status_code",
    "source",
]

OFFER_FIELDNAMES = [
    "route",
    "origin",
    "destination",
    "departure_date",
    "flight_number",
    "airline_id",
    "departure_time",
    "arrival_time",
    "duration_minutes",
    "id",
    "price",
    "currency",
    "transfer_count",
    "transfer_airports",
    "baggage_checked_weight_kg",
    "baggage_checked_pieces",
    "baggage_carry_on_weight_kg",
    "booking_url",
    "source",
]

SCHEDULE_FIELDNAMES = [
    "schedule_id",
    "route",
    "origin",
    "destination",
    "flight_date",
    "weekday",
    "airline_id",
    "flight_number",
    "departure_time",
    "arrival_time",
    "duration_minutes",
    "transfer_count",
    "transfer_airports",
    "source",
]

CHANGE_FIELDNAMES = [
    "route",
    "origin",
    "destination",
    "flight_date",
    "flight_number",
    "airline_id",
    "change_id",
    "change_type",
    "price",
    "currency",
    "baggage_checked_weight_kg",
    "baggage_checked_pieces",
    "baggage_carry_on_weight_kg",
    "transfer_count",
    "transfer_airports",
    "booking_url",
    "changed_fields",
    "source",
]

TABLE_FIELDNAMES = [
    "table",
    "id",
    "name_zh",
    "name_en",
    "country",
    "flag",
    "icon_url",
    "origin",
    "destination",
    "rule_status",
    "rule_source_url",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def pick(row: dict[str, Any], fieldnames: list[str]) -> dict[str, Any]:
    return {field: row.get(field, "") for field in fieldnames}


def compact_rows(rows: list[dict[str, Any]], fieldnames: list[str], key_fields: list[str]) -> list[dict[str, Any]]:
    compacted: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        item = pick(row, fieldnames)
        key = tuple(str(item.get(field, "")) for field in key_fields)
        compacted[key] = item
    return list(compacted.values())


def write_table(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows([pick(row, fieldnames) for row in rows])


def ensure_airline_icon(airline_id: str) -> str:
    code = str(airline_id or "").strip().upper()
    if not code:
        return ""
    AIRLINE_ASSET_DIR.mkdir(parents=True, exist_ok=True)
    icon_path = AIRLINE_ASSET_DIR / f"{code}.png"
    if icon_path.exists() and icon_path.stat().st_size > 0:
        return f"./assets/airlines/{code}.png"
    request = Request(AIRLINE_ICON_SOURCE.format(code=code), headers={"User-Agent": "flight-cache-crawler/1.0"})
    try:
        with urlopen(request, timeout=10) as response:
            content_type = response.headers.get("Content-Type", "")
            payload = response.read()
        if "image" not in content_type or not payload:
            return ""
        icon_path.write_bytes(payload)
        return f"./assets/airlines/{code}.png"
    except (HTTPError, URLError, TimeoutError, OSError):
        return ""


def build_tables(config: dict[str, Any], schedule: list[dict[str, Any]], offers: list[dict[str, Any]]) -> dict[str, Any]:
    lookups = load_lookups()
    airline_registry = load_airline_rules()
    route_codes = []
    seen_routes = set()
    for route in (
        list(config.get("offer_routes", []))
        + [row.get("route", "") for row in schedule]
        + [row.get("route", "") for row in offers]
    ):
        if route and route not in seen_routes:
            route_codes.append(route)
            seen_routes.add(route)
    airport_codes = sorted({
        code
        for route in route_codes
        for code in route.split("-", 1)
        if code
    })
    airline_codes = sorted({
        code
        for code in (
            [row.get("airline_id", "") for row in schedule]
            + [row.get("airline_id", "") for row in offers]
        )
        if code
    })
    airports = []
    for code in airport_codes:
        airport = lookups.get("airports", {}).get(code, {})
        airports.append({
            "airport_id": code,
            "airport_name_zh": airport.get("zh_tw", ""),
            "airport_name_en": airport.get("en", ""),
            "country": airport.get("country", ""),
            "flag": airport.get("flag", ""),
        })
    airlines = []
    for code in airline_codes:
        rule = merged_rule(code, airline_registry)
        airlines.append({
            "airline_id": rule.get("airline_id", code),
            "airline_name_zh": rule.get("airline_name", ""),
            "airline_name_en": rule.get("airline_name_en", ""),
            "icon_url": ensure_airline_icon(rule.get("airline_id", code)),
            "rule_status": rule.get("rule_status", "unknown"),
            "rule_source_url": rule.get("rule_source_url", ""),
        })
    routes = []
    for route in route_codes:
        if "-" not in route:
            continue
        origin, destination = route.split("-", 1)
        routes.append({
            "route": route,
            "origin": origin,
            "destination": destination,
        })
    return {
        "generated_at": utc_now(),
        "schema_version": 2,
        "tables": {
            "airports": airports,
            "airlines": airlines,
            "routes": routes,
        },
    }


def table_csv_rows(tables_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in tables_payload["tables"]["airports"]:
        rows.append({
            "table": "airports",
            "id": item.get("airport_id", ""),
            "name_zh": item.get("airport_name_zh", ""),
            "name_en": item.get("airport_name_en", ""),
            "country": item.get("country", ""),
            "flag": item.get("flag", ""),
        })
    for item in tables_payload["tables"]["airlines"]:
        rows.append({
            "table": "airlines",
            "id": item.get("airline_id", ""),
            "name_zh": item.get("airline_name_zh", ""),
            "name_en": item.get("airline_name_en", ""),
            "icon_url": item.get("icon_url", ""),
            "rule_status": item.get("rule_status", ""),
            "rule_source_url": item.get("rule_source_url", ""),
        })
    for item in tables_payload["tables"]["routes"]:
        rows.append({
            "table": "routes",
            "id": item.get("route", ""),
            "origin": item.get("origin", ""),
            "destination": item.get("destination", ""),
        })
    return rows


def write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_outputs(items: list[dict[str, Any]], schedule: list[dict[str, Any]], offers: list[dict[str, Any]], config: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = utc_now()
    airline_registry = load_airline_rules()

    items = compact_rows(items, FIELDNAMES, ["id"])
    items = sorted(items, key=lambda item: (
        item.get("flight_date", ""),
        item.get("airport", ""),
        item.get("direction", ""),
        item.get("scheduled_time", ""),
        item.get("flight_number", ""),
    ))

    schedule = compact_rows(schedule, SCHEDULE_FIELDNAMES, ["schedule_id"])
    schedule = sorted(schedule, key=lambda row: (
        row.get("flight_date", ""),
        row.get("route", ""),
        row.get("departure_time", ""),
        row.get("flight_number", ""),
    ))

    enriched_offers = [enrich_offer_with_airline_rule(offer, airline_registry) for offer in offers]
    offers_public = compact_rows(enriched_offers, OFFER_FIELDNAMES, ["id"])
    offers_public = sorted(offers_public, key=lambda offer: (
        offer.get("departure_date", ""),
        offer.get("route", ""),
        int(offer.get("price") or 0),
        offer.get("flight_number", ""),
    ))

    changes = build_change_overlays(schedule, enriched_offers)
    changes = compact_rows(changes, CHANGE_FIELDNAMES, ["change_id"])
    changes = sorted(changes, key=lambda row: (
        row.get("flight_date", ""),
        row.get("route", ""),
        row.get("flight_number", ""),
        row.get("changed_fields", ""),
    ))

    tables_payload = build_tables(config, schedule, offers_public)

    write_payload(JSON_PATH, {
        "generated_at": generated_at,
        "schema_version": 2,
        "dataset": "TDX Air FIDS Airport Departure/Arrival",
        "standard_fields": FIELDNAMES,
        "items": items,
    })
    write_table(CSV_PATH, items, FIELDNAMES)

    write_payload(SCHEDULE_JSON_PATH, {
        "generated_at": generated_at,
        "schema_version": 2,
        "dataset": "Fixed Flight Schedule",
        "standard_fields": SCHEDULE_FIELDNAMES,
        "items": schedule,
    })
    write_table(SCHEDULE_CSV_PATH, schedule, SCHEDULE_FIELDNAMES)

    write_payload(CHANGES_JSON_PATH, {
        "generated_at": generated_at,
        "schema_version": 2,
        "dataset": "Schedule Change Overlay",
        "standard_fields": CHANGE_FIELDNAMES,
        "items": changes,
    })
    write_table(CHANGES_CSV_PATH, changes, CHANGE_FIELDNAMES)

    write_payload(OFFERS_JSON_PATH, {
        "generated_at": generated_at,
        "schema_version": 2,
        "dataset": "Ticket Offers",
        "standard_fields": OFFER_FIELDNAMES,
        "items": offers_public,
    })
    write_table(OFFERS_CSV_PATH, offers_public, OFFER_FIELDNAMES)

    write_payload(TABLES_JSON_PATH, tables_payload)
    write_table(TABLES_CSV_PATH, table_csv_rows(tables_payload), TABLE_FIELDNAMES)


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
    print(f"Wrote {TABLES_JSON_PATH}")
    print(f"Wrote {TABLES_CSV_PATH}")


if __name__ == "__main__":
    main()
