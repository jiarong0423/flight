from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "sources.json"
RAW_DIR = ROOT / "data" / "raw"


class CrawlError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def date_range(start: date, days: int):
    for offset in range(days + 1):
        yield start + timedelta(days=offset)


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing crawler config: {CONFIG_PATH}")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def split_route(route: str) -> tuple[str, str]:
    if "-" not in route:
        return route, ""
    origin, destination = route.split("-", 1)
    return origin, destination


def fill_template(template: str, route: str, travel_date: date) -> str:
    origin, destination = split_route(route)
    return template.format(
        route=route,
        origin=origin,
        destination=destination,
        date=travel_date.isoformat(),
        yyyymmdd=travel_date.strftime("%Y%m%d"),
    )


def request_text(url: str, timeout_seconds: int, user_agent: str) -> str:
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "*/*"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise CrawlError(f"Fetch failed: {url}: {exc}") from exc


def nested_get(payload: Any, path: str) -> Any:
    current = payload
    if not path:
        return current
    for part in path.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(path)
    return current


def normalize_price(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^0-9]", "", str(value))
    if not digits:
        raise ValueError(f"Cannot parse price from {value!r}")
    return int(digits)


def parse_json_source(text: str, source: dict[str, Any], route: str, travel_date: date, currency: str) -> dict[str, Any]:
    payload = json.loads(text)
    items_path = source.get("items_path", "")
    items = nested_get(payload, items_path)
    if isinstance(items, dict):
        items = [items]
    fields = source.get("fields", {})
    if not items:
        raise CrawlError("JSON source returned no items")
    item = items[0]
    price_path = fields.get("price", "price")
    currency_path = fields.get("currency")
    return {
        "route": route,
        "travel_date": travel_date.isoformat(),
        "price": normalize_price(nested_get(item, price_path)),
        "currency": nested_get(item, currency_path) if currency_path else currency,
        "source": source.get("name", "json-source"),
        "fetched_at": utc_now(),
    }


def parse_csv_source(text: str, source: dict[str, Any], route: str, travel_date: date, currency: str) -> dict[str, Any]:
    rows = list(csv.DictReader(io.StringIO(text)))
    fields = source.get("fields", {})
    price_field = fields.get("price", "price")
    route_field = fields.get("route", "route")
    date_field = fields.get("travel_date", "travel_date")
    for row in rows:
        row_route = row.get(route_field, route)
        row_date = row.get(date_field, travel_date.isoformat())
        if row_route == route and row_date == travel_date.isoformat():
            return {
                "route": route,
                "travel_date": travel_date.isoformat(),
                "price": normalize_price(row[price_field]),
                "currency": row.get(fields.get("currency", "currency"), currency),
                "source": source.get("name", "csv-source"),
                "fetched_at": utc_now(),
            }
    raise CrawlError("CSV source had no matching row")


def parse_html_regex_source(text: str, source: dict[str, Any], route: str, travel_date: date, currency: str) -> dict[str, Any]:
    pattern = source.get("price_regex")
    if not pattern:
        raise CrawlError("html_regex source requires price_regex")
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
    if not match:
        raise CrawlError("html_regex did not match price")
    value = match.group("price") if "price" in match.groupdict() else match.group(1)
    return {
        "route": route,
        "travel_date": travel_date.isoformat(),
        "price": normalize_price(value),
        "currency": source.get("currency", currency),
        "source": source.get("name", "html-regex-source"),
        "fetched_at": utc_now(),
    }


def mock_price(route: str, travel_date: date, currency: str) -> dict[str, Any]:
    key = f"{route}:{travel_date.isoformat()}".encode("utf-8")
    digest = hashlib.sha256(key).hexdigest()
    randomizer = random.Random(int(digest[:12], 16))
    base = 5200 + randomizer.randint(0, 9000)
    weekend = 900 if travel_date.weekday() in (4, 5, 6) else 0
    season = 1400 if travel_date.month in (7, 8, 12) else 0
    route_adjustment = {
        "TPE-NRT": 1800,
        "TPE-ICN": 900,
        "TPE-BKK": 1200,
        "TPE-HKG": -300,
        "TPE-SIN": 1600,
    }.get(route, 0)
    return {
        "route": route,
        "travel_date": travel_date.isoformat(),
        "price": base + weekend + season + route_adjustment,
        "currency": currency,
        "source": "mock-fallback",
        "fetched_at": utc_now(),
    }


def fetch_one(route: str, travel_date: date, config: dict[str, Any]) -> dict[str, Any]:
    currency = config.get("currency", "TWD")
    timeout_seconds = int(config.get("timeout_seconds", 20))
    user_agent = config.get("user_agent", "flight-cache-crawler/1.0")
    last_error = None

    for source in config.get("sources", []):
        if not source.get("enabled", True):
            continue
        source_type = source.get("type")
        url_template = source.get("url")
        if not url_template:
            continue
        url = fill_template(url_template, route, travel_date)
        try:
            text = request_text(url, timeout_seconds, user_agent)
            save_raw(route, travel_date, source.get("name", source_type or "source"), text)
            if source_type == "json":
                return parse_json_source(text, source, route, travel_date, currency)
            if source_type == "csv":
                return parse_csv_source(text, source, route, travel_date, currency)
            if source_type == "html_regex":
                return parse_html_regex_source(text, source, route, travel_date, currency)
            raise CrawlError(f"Unsupported source type: {source_type}")
        except Exception as exc:  # keep next source/fallback alive
            last_error = exc
            print(f"WARN {route} {travel_date}: {exc}")
            time.sleep(float(config.get("request_delay_seconds", 0.2)))

    if config.get("mock_fallback", True):
        return mock_price(route, travel_date, currency)
    raise CrawlError(f"All sources failed for {route} {travel_date}: {last_error}")


def save_raw(route: str, travel_date: date, source_name: str, text: str) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    safe_source = re.sub(r"[^a-zA-Z0-9_.-]+", "-", source_name).strip("-") or "source"
    raw_path = RAW_DIR / f"{travel_date.isoformat()}_{route}_{safe_source}.txt"
    raw_path.write_text(text, encoding="utf-8")


def crawl_prices(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    config = config or load_config()
    routes = config.get("routes", [])
    lookahead_days = int(config.get("lookahead_days", 120))
    start = date.today()
    items = []
    for route in routes:
        for travel_date in date_range(start, lookahead_days):
            items.append(fetch_one(route, travel_date, config))
    return items
