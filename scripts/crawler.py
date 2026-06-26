from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import random
import re
import ssl
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from airline_rules import merged_rule
from lookups import airport_info, airport_name, mapped_baggage, standard_direction, standard_status


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "sources.json"
RAW_DIR = ROOT / "data" / "raw"

TDX_TOKEN_URL = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
TDX_AIR_FIDS_URL = "https://tdx.transportdata.tw/api/basic/v2/Air/FIDS/Airport/{direction}/{airport}"
AMADEUS_TEST_BASE_URL = "https://test.api.amadeus.com"
AMADEUS_PROD_BASE_URL = "https://api.amadeus.com"


class CrawlError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing crawler config: {CONFIG_PATH}")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context


def request_text(url: str, timeout_seconds: int, headers: dict[str, str] | None = None) -> str:
    request = Request(url, headers=headers or {})
    try:
        with urlopen(request, timeout=timeout_seconds, context=tls_context()) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except HTTPError as exc:
        raise CrawlError(f"Fetch failed: {url}: HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise CrawlError(f"Fetch failed: {url}: {exc}") from exc


def request_json(url: str, timeout_seconds: int, headers: dict[str, str] | None = None) -> Any:
    return json.loads(request_text(url, timeout_seconds, headers))


def request_form_json(url: str, form: dict[str, str], timeout_seconds: int) -> Any:
    body = urlencode(form).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds, context=tls_context()) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.read().decode(charset, errors="replace"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise CrawlError(f"Token request failed: {exc}") from exc


def request_form_json_headers(url: str, form: dict[str, str], timeout_seconds: int, headers: dict[str, str] | None = None) -> Any:
    body = urlencode(form).encode("utf-8")
    request_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    request_headers.update(headers or {})
    request = Request(url, data=body, headers=request_headers, method="POST")
    try:
        with urlopen(request, timeout=timeout_seconds, context=tls_context()) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.read().decode(charset, errors="replace"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise CrawlError(f"Form request failed: {url}: HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise CrawlError(f"Form request failed: {url}: {exc}") from exc


def first_value(record: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return default


def local_name(value: Any) -> str:
    if isinstance(value, dict):
        return value.get("Zh_tw") or value.get("En") or value.get("zh_tw") or value.get("en") or ""
    return str(value or "")


def compact_time(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) == 4 and text.isdigit():
        return f"{text[:2]}:{text[2:]}"
    return text


def split_route(route: str) -> tuple[str, str]:
    if "-" not in route:
        return route, ""
    origin, destination = route.split("-", 1)
    return origin, destination


def date_range(start: date, days: int):
    for offset in range(days + 1):
        yield start + timedelta(days=offset)


def fill_template(template: str, route: str, travel_date: date) -> str:
    origin, destination = split_route(route)
    return template.format(
        route=route,
        origin=origin,
        destination=destination,
        date=travel_date.isoformat(),
        yyyymmdd=travel_date.strftime("%Y%m%d"),
    )


def nested_get(payload: Any, path: str, default: Any = "") -> Any:
    current = payload
    if not path:
        return current
    try:
        for part in path.split("."):
            if isinstance(current, list):
                current = current[int(part)]
            elif isinstance(current, dict):
                current = current[part]
            else:
                return default
    except (KeyError, IndexError, ValueError, TypeError):
        return default
    return default if current is None else current


def normalize_int(value: Any, default: int | None = None) -> int | None:
    if value in (None, ""):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^0-9-]", "", str(value))
    if digits in ("", "-"):
        return default
    return int(digits)


def save_raw(name: str, payload: Any) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "-", name).strip("-") or "source"
    raw_path = RAW_DIR / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{safe_name}.json"
    raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class TdxClient:
    def __init__(self, config: dict[str, Any]):
        self.timeout_seconds = int(config.get("timeout_seconds", 20))
        self.user_agent = config.get("user_agent", "flight-cache-crawler/1.0")
        self.client_id = os.getenv(config.get("client_id_env", "TDX_CLIENT_ID"), "")
        self.client_secret = os.getenv(config.get("client_secret_env", "TDX_CLIENT_SECRET"), "")
        self.max_retries = int(config.get("max_retries", 2))
        self.retry_delay_seconds = float(config.get("retry_delay_seconds", 60.0))
        self._token: str | None = None

    def token(self) -> str:
        if self._token:
            return self._token
        if not self.client_id or not self.client_secret:
            raise CrawlError("Missing TDX credentials. Set TDX_CLIENT_ID and TDX_CLIENT_SECRET.")
        payload = request_form_json(
            TDX_TOKEN_URL,
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            self.timeout_seconds,
        )
        self._token = payload["access_token"]
        return self._token

    def fids_airport(self, airport: str, direction: str, top: int) -> list[dict[str, Any]]:
        url = TDX_AIR_FIDS_URL.format(direction=direction, airport=airport)
        url = f"{url}?{urlencode({'$top': top, '$format': 'JSON'})}"
        headers = {
            "Authorization": f"Bearer {self.token()}",
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        payload = None
        for attempt in range(self.max_retries + 1):
            try:
                payload = request_json(url, self.timeout_seconds, headers)
                break
            except CrawlError as exc:
                if "HTTP 429" not in str(exc) or attempt == self.max_retries:
                    raise
                sleep_seconds = self.retry_delay_seconds * (attempt + 1)
                print(f"WARN rate limited for {airport} {direction}; retrying in {sleep_seconds:.0f}s")
                time.sleep(sleep_seconds)
        if not isinstance(payload, list):
            raise CrawlError(f"TDX FIDS response is not a list: {airport} {direction}")
        save_raw(f"tdx-{airport}-{direction}", payload)
        return payload


class AmadeusClient:
    def __init__(self, config: dict[str, Any], source: dict[str, Any]):
        self.timeout_seconds = int(config.get("timeout_seconds", 20))
        self.client_id = os.getenv(source.get("client_id_env", "AMADEUS_CLIENT_ID"), "")
        self.client_secret = os.getenv(source.get("client_secret_env", "AMADEUS_CLIENT_SECRET"), "")
        self.base_url = AMADEUS_PROD_BASE_URL if source.get("environment") == "production" else AMADEUS_TEST_BASE_URL
        self.currency = source.get("currency", "TWD")
        self.adults = int(source.get("adults", 1))
        self.max_results = int(source.get("max_results", 10))
        self._token: str | None = None

    def token(self) -> str:
        if self._token:
            return self._token
        if not self.client_id or not self.client_secret:
            raise CrawlError("Missing Amadeus credentials. Set AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET.")
        payload = request_form_json_headers(
            f"{self.base_url}/v1/security/oauth2/token",
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            self.timeout_seconds,
        )
        self._token = payload["access_token"]
        return self._token

    def flight_offers(self, route: str, departure_date: date) -> dict[str, Any]:
        origin, destination = split_route(route)
        query = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": departure_date.isoformat(),
            "adults": self.adults,
            "currencyCode": self.currency,
            "max": self.max_results,
        }
        url = f"{self.base_url}/v2/shopping/flight-offers?{urlencode(query)}"
        payload = request_json(
            url,
            self.timeout_seconds,
            {
                "Authorization": f"Bearer {self.token()}",
                "Accept": "application/json",
            },
        )
        save_raw(f"amadeus-{route}-{departure_date.isoformat()}", payload)
        return payload


def iso_time(value: Any) -> str:
    text = str(value or "")
    if "T" in text:
        return text.split("T", 1)[1][:5]
    return compact_time(text)


def parse_duration_minutes(value: Any) -> int | str:
    text = str(value or "")
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", text)
    if not match:
        return ""
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    return hours * 60 + minutes


def amadeus_baggage(offer: dict[str, Any]) -> dict[str, Any]:
    checked_weight = ""
    checked_pieces = ""
    fare_details = (
        offer.get("travelerPricings", [{}])[0]
        .get("fareDetailsBySegment", [])
    )
    for detail in fare_details:
        bags = detail.get("includedCheckedBags") or {}
        if not checked_weight and bags.get("weight"):
            checked_weight = bags.get("weight")
        if not checked_pieces and bags.get("quantity") is not None:
            checked_pieces = bags.get("quantity")
    return {
        "baggage_checked_weight_kg": checked_weight,
        "baggage_checked_pieces": checked_pieces,
        "baggage_carry_on_weight_kg": "",
        "baggage_text": "Amadeus includedCheckedBags",
    }


def parse_amadeus_offers(payload: dict[str, Any], route: str, departure_date: date) -> list[dict[str, Any]]:
    parsed = []
    for offer in payload.get("data", []):
        itinerary = (offer.get("itineraries") or [{}])[0]
        segments = itinerary.get("segments") or []
        if not segments:
            continue
        first_segment = segments[0]
        last_segment = segments[-1]
        airline_id = (offer.get("validatingAirlineCodes") or [first_segment.get("carrierCode", "")])[0]
        flight_numbers = [
            f"{segment.get('carrierCode', '')}{segment.get('number', '')}".strip()
            for segment in segments
        ]
        transfer_airports = [
            segment.get("arrival", {}).get("iataCode", "")
            for segment in segments[:-1]
            if segment.get("arrival", {}).get("iataCode")
        ]
        transfer_airports_zh = " / ".join(airport_name(code) for code in transfer_airports)
        transfer_count = max(len(segments) - 1, 0)
        baggage = amadeus_baggage(offer)
        row = {
            "price": offer.get("price", {}).get("grandTotal") or offer.get("price", {}).get("total", ""),
            "currency": offer.get("price", {}).get("currency", "TWD"),
            "flight_number": " + ".join(flight_numbers),
            "airline_id": airline_id,
            "departure_time": iso_time(first_segment.get("departure", {}).get("at")),
            "arrival_time": iso_time(last_segment.get("arrival", {}).get("at")),
            "duration_minutes": parse_duration_minutes(itinerary.get("duration")),
            "transfer_count": transfer_count,
            "transfer_airports": ",".join(transfer_airports),
            "transfer_airports_zh": transfer_airports_zh,
            "transfer_summary": "直飛" if transfer_count == 0 else f"{transfer_count} stop(s): {transfer_airports_zh or ','.join(transfer_airports)}",
            "fare_brand": offer.get("pricingOptions", {}).get("fareType", [""])[0],
            "booking_url": "",
            **baggage,
        }
        parsed.append(normalize_offer(row, route, departure_date, "amadeus-flight-offers", {}))
    return parsed


def normalize_tdx_record(record: dict[str, Any], airport: str, direction: str) -> dict[str, Any]:
    is_departure = direction == "Departure"
    flight_date = first_value(record, "FlightDate", "Date", default=date.today().isoformat())
    flight_number = str(first_value(record, "FlightNumber", "FlightNo", default="")).strip()
    airline_id = first_value(record, "AirlineID", "AirLineID", "AirlineCode", default="")
    departure_airport = first_value(record, "DepartureAirportID", "DepartureAirport", default=airport if is_departure else "")
    arrival_airport = first_value(record, "ArrivalAirportID", "ArrivalAirport", default=airport if not is_departure else "")
    scheduled = first_value(
        record,
        "ScheduleDepartureTime" if is_departure else "ScheduleArrivalTime",
        "ScheduledDepartureTime" if is_departure else "ScheduledArrivalTime",
        "ScheduleTime",
        default="",
    )
    estimated = first_value(
        record,
        "EstimatedDepartureTime" if is_departure else "EstimatedArrivalTime",
        "EstimateDepartureTime" if is_departure else "EstimateArrivalTime",
        "EstimatedTime",
        default="",
    )
    actual = first_value(
        record,
        "ActualDepartureTime" if is_departure else "ActualArrivalTime",
        "ActualTime",
        default="",
    )
    remark = first_value(
        record,
        "DepartureRemark" if is_departure else "ArrivalRemark",
        "Remark",
        default="",
    )
    terminal = first_value(record, "Terminal", "TerminalID", default="")
    gate = first_value(record, "Gate", "GateID", default="")
    airline_name = local_name(first_value(record, "AirlineName", "AirLineName", default={}))
    airline_rule = merged_rule(airline_id)
    airline_name = airline_name or airline_rule.get("airline_name", "")
    departure_name = local_name(first_value(record, "DepartureAirportName", default={}))
    arrival_name = local_name(first_value(record, "ArrivalAirportName", default={}))
    departure_name = departure_name or airport_name(departure_airport)
    arrival_name = arrival_name or airport_name(arrival_airport)
    departure_info = airport_info(departure_airport)
    arrival_info = airport_info(arrival_airport)
    identity = "|".join([flight_date, flight_number, airport, direction, compact_time(scheduled), compact_time(estimated)])
    return {
        "id": hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16],
        "flight_date": str(flight_date),
        "direction": standard_direction(direction),
        "airport": airport,
        "airport_name": airport_name(airport),
        "flight_number": flight_number,
        "airline_id": airline_id,
        "airline_name": airline_name,
        "airline_name_zh": airline_rule.get("airline_name", airline_name),
        "airline_name_en": airline_rule.get("airline_name_en", ""),
        "departure_airport": departure_airport,
        "departure_airport_name": departure_name,
        "departure_airport_name_zh": airport_name(departure_airport),
        "departure_country": departure_info.get("country", ""),
        "departure_flag": departure_info.get("flag", ""),
        "arrival_airport": arrival_airport,
        "arrival_airport_name": arrival_name,
        "arrival_airport_name_zh": airport_name(arrival_airport),
        "arrival_country": arrival_info.get("country", ""),
        "arrival_flag": arrival_info.get("flag", ""),
        "scheduled_time": compact_time(scheduled),
        "estimated_time": compact_time(estimated),
        "actual_time": compact_time(actual),
        "terminal": str(terminal or ""),
        "gate": str(gate or ""),
        "remark": str(remark or ""),
        "status_code": standard_status(remark),
        "source": "TDX Air FIDS",
        "fetched_at": utc_now(),
    }


def mock_tdx_records(config: dict[str, Any]) -> list[dict[str, Any]]:
    airports = config.get("airports", ["TPE", "TSA", "KHH"])
    directions = config.get("directions", ["Departure", "Arrival"])
    airlines = ["CI", "BR", "JX", "IT", "AE", "B7"]
    destinations = ["NRT", "ICN", "HKG", "BKK", "SIN", "KHH", "TSA", "MZG", "KNH"]
    today = date.today().isoformat()
    items = []
    for airport in airports:
        for direction in directions:
            for index in range(12):
                rng = random.Random(f"{airport}:{direction}:{today}:{index}")
                airline = rng.choice(airlines)
                hour = 6 + index
                minute = rng.choice([0, 5, 10, 20, 30, 45, 55])
                scheduled = f"{hour:02d}:{minute:02d}"
                estimated_minute = (minute + rng.choice([0, 0, 5, 10, 20])) % 60
                estimated = f"{hour:02d}:{estimated_minute:02d}"
                other_airport = rng.choice([item for item in destinations if item != airport])
                record = {
                    "FlightDate": today,
                    "FlightNumber": f"{airline}{rng.randint(100, 999)}",
                    "AirlineID": airline,
                    "DepartureAirportID": airport if direction == "Departure" else other_airport,
                    "ArrivalAirportID": other_airport if direction == "Departure" else airport,
                    "ScheduleDepartureTime" if direction == "Departure" else "ScheduleArrivalTime": scheduled,
                    "EstimatedDepartureTime" if direction == "Departure" else "EstimatedArrivalTime": estimated,
                    "DepartureRemark" if direction == "Departure" else "ArrivalRemark": rng.choice(["準時", "報到", "已飛", "延誤", "抵達"]),
                    "Terminal": str(rng.randint(1, 2)),
                    "Gate": f"{rng.choice(['A', 'B', 'C', 'D'])}{rng.randint(1, 9)}",
                }
                item = normalize_tdx_record(record, airport, direction)
                item["source"] = "mock-tdx-fallback"
                items.append(item)
    return items


def crawl_tdx_fids(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    config = config or load_config()
    airports = config.get("airports", [])
    directions = config.get("directions", ["Departure", "Arrival"])
    top = int(config.get("top", 200))
    delay = float(config.get("request_delay_seconds", 0.2))
    client = TdxClient(config)
    items: list[dict[str, Any]] = []

    if (not client.client_id or not client.client_secret) and config.get("mock_fallback", True):
        print("WARN using mock fallback: missing TDX credentials")
        return mock_tdx_records(config)

    for airport in airports:
        for direction in directions:
            try:
                payload = client.fids_airport(airport, direction, top)
                items.extend(normalize_tdx_record(row, airport, direction) for row in payload)
            except Exception as exc:
                print(f"WARN skipped {airport} {direction}: {exc}")
                time.sleep(delay)

    if not items and config.get("mock_fallback", True):
        print("WARN using mock fallback: no TDX records fetched")
        return mock_tdx_records(config)

    return items


def mock_static_schedule(config: dict[str, Any]) -> list[dict[str, Any]]:
    routes = config.get("offer_routes", ["TPE-NRT"])
    lookahead_days = int(config.get("schedule_lookahead_days", config.get("offer_lookahead_days", 90)))
    airlines = ["CI", "BR", "JX", "IT", "AE", "B7"]
    today = date.today()
    rows = []
    for route in routes:
        origin, destination = split_route(route)
        route_seed = int(hashlib.sha1(route.encode("utf-8")).hexdigest()[:6], 16)
        for travel_day in date_range(today, lookahead_days):
            weekday = travel_day.weekday()
            for slot in range(2):
                rng = random.Random(f"schedule:{route}:{weekday}:{slot}:{route_seed}")
                airline = airlines[(route_seed + weekday + slot) % len(airlines)]
                airline_rule = merged_rule(airline)
                origin_info = airport_info(origin)
                destination_info = airport_info(destination)
                flight_number = f"{airline}{100 + ((route_seed + weekday * 13 + slot * 71) % 800)}"
                dep_hour = 7 + slot * 8 + rng.randint(0, 2)
                dep_minute = rng.choice([0, 10, 20, 30, 45, 55])
                duration = rng.randint(90, 260)
                arr_hour = (dep_hour + duration // 60) % 24
                arr_minute = (dep_minute + duration % 60) % 60
                schedule_id = hashlib.sha1(f"{route}:{travel_day}:{flight_number}".encode("utf-8")).hexdigest()[:16]
                rows.append(
                    {
                        "schedule_id": schedule_id,
                        "route": route,
                        "origin": origin,
                        "origin_name": airport_name(origin),
                        "origin_name_zh": airport_name(origin),
                        "origin_country": origin_info.get("country", ""),
                        "origin_flag": origin_info.get("flag", ""),
                        "destination": destination,
                        "destination_name": airport_name(destination),
                        "destination_name_zh": airport_name(destination),
                        "destination_country": destination_info.get("country", ""),
                        "destination_flag": destination_info.get("flag", ""),
                        "flight_date": travel_day.isoformat(),
                        "weekday": weekday,
                        "airline_id": airline,
                        "airline_name": airline_rule.get("airline_name", ""),
                        "airline_name_zh": airline_rule.get("airline_name", ""),
                        "airline_name_en": airline_rule.get("airline_name_en", ""),
                        "flight_number": flight_number,
                        "departure_time": f"{dep_hour:02d}:{dep_minute:02d}",
                        "arrival_time": f"{arr_hour:02d}:{arr_minute:02d}",
                        "duration_minutes": duration,
                        "transfer_count": 0,
                        "baseline_price": "",
                        "baseline_currency": "TWD",
                        "baseline_checked_baggage_kg": "",
                        "baseline_checked_baggage_pieces": "",
                        "baseline_carry_on_kg": "",
                        "source": "fixed-schedule-fallback",
                        "fetched_at": utc_now(),
                    }
                )
    return rows


def crawl_static_schedule(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    config = config or load_config()
    # Keep the static baseline intentionally low-frequency and deterministic.
    # A real TDX schedule endpoint can be wired here without changing frontend fields.
    return mock_static_schedule(config)


def build_change_overlays(schedule: list[dict[str, Any]], offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    schedule_by_key = {
        (row.get("route"), row.get("flight_date"), row.get("flight_number")): row
        for row in schedule
    }
    changes = []
    for offer in offers:
        key = (offer.get("route"), offer.get("departure_date"), offer.get("flight_number"))
        baseline = schedule_by_key.get(key)
        change_fields: dict[str, Any] = {}
        if baseline is None:
            change_type = "new_offer"
            change_fields = {
                "price": offer.get("price", ""),
                "baggage_checked_weight_kg": offer.get("baggage_checked_weight_kg", ""),
                "baggage_checked_pieces": offer.get("baggage_checked_pieces", ""),
                "baggage_carry_on_weight_kg": offer.get("baggage_carry_on_weight_kg", ""),
                "transfer_count": offer.get("transfer_count", ""),
            }
        else:
            change_type = "updated_offer"
            comparisons = {
                "price": ("baseline_price", offer.get("price", "")),
                "baggage_checked_weight_kg": ("baseline_checked_baggage_kg", offer.get("baggage_checked_weight_kg", "")),
                "baggage_checked_pieces": ("baseline_checked_baggage_pieces", offer.get("baggage_checked_pieces", "")),
                "baggage_carry_on_weight_kg": ("baseline_carry_on_kg", offer.get("baggage_carry_on_weight_kg", "")),
                "transfer_count": ("transfer_count", offer.get("transfer_count", "")),
            }
            for field, (base_field, current) in comparisons.items():
                if current not in (None, "") and str(current) != str(baseline.get(base_field, "")):
                    change_fields[field] = current
        if not change_fields:
            continue
        change_id = hashlib.sha1(f"{key}:{json.dumps(change_fields, sort_keys=True)}".encode("utf-8")).hexdigest()[:16]
        changes.append(
            {
                "change_id": change_id,
                "change_type": change_type,
                "route": offer.get("route", ""),
                "origin": offer.get("origin", ""),
                "origin_name": offer.get("origin_name", ""),
                "origin_name_zh": offer.get("origin_name_zh", ""),
                "origin_country": offer.get("origin_country", ""),
                "origin_flag": offer.get("origin_flag", ""),
                "destination": offer.get("destination", ""),
                "destination_name": offer.get("destination_name", ""),
                "destination_name_zh": offer.get("destination_name_zh", ""),
                "destination_country": offer.get("destination_country", ""),
                "destination_flag": offer.get("destination_flag", ""),
                "flight_date": offer.get("departure_date", ""),
                "flight_number": offer.get("flight_number", ""),
                "airline_id": offer.get("airline_id", ""),
                "airline_name": offer.get("airline_name", ""),
                "airline_name_zh": offer.get("airline_name_zh", offer.get("airline_name", "")),
                "airline_name_en": offer.get("airline_name_en", ""),
                "price": offer.get("price", ""),
                "currency": offer.get("currency", "TWD"),
                "baggage_checked_weight_kg": offer.get("baggage_checked_weight_kg", ""),
                "baggage_checked_pieces": offer.get("baggage_checked_pieces", ""),
                "baggage_carry_on_weight_kg": offer.get("baggage_carry_on_weight_kg", ""),
                "transfer_count": offer.get("transfer_count", ""),
                "transfer_airports": offer.get("transfer_airports", ""),
                "transfer_airports_zh": offer.get("transfer_airports_zh", ""),
                "transfer_summary": offer.get("transfer_summary", ""),
                "booking_url": offer.get("booking_url", ""),
                "changed_fields": ",".join(sorted(change_fields.keys())),
                "source": offer.get("source", ""),
                "fetched_at": utc_now(),
            }
        )
    return changes


def normalize_offer(
    record: dict[str, Any],
    route: str,
    departure_date: date,
    source_name: str,
    fields: dict[str, str],
) -> dict[str, Any]:
    origin, destination = split_route(route)
    origin_info = airport_info(origin)
    destination_info = airport_info(destination)
    price = normalize_int(nested_get(record, fields.get("price", "price")), 0) or 0
    flight_number = str(nested_get(record, fields.get("flight_number", "flight_number"), "")).strip()
    airline_id = str(nested_get(record, fields.get("airline_id", "airline_id"), "")).strip()
    airline_rule = merged_rule(airline_id or flight_number)
    departure_time = compact_time(nested_get(record, fields.get("departure_time", "departure_time"), ""))
    arrival_time = compact_time(nested_get(record, fields.get("arrival_time", "arrival_time"), ""))
    transfer_count = normalize_int(nested_get(record, fields.get("transfer_count", "transfer_count"), 0), 0) or 0
    transfer_airports = str(nested_get(record, fields.get("transfer_airports", "transfer_airports"), "")).strip()
    transfer_airports_zh = " / ".join(
        airport_name(code.strip()) for code in transfer_airports.split(",") if code.strip()
    )
    transfer_summary = "直飛" if transfer_count == 0 else f"{transfer_count} stop(s) {transfer_airports_zh or transfer_airports}".strip()
    checked_kg = normalize_int(nested_get(record, fields.get("baggage_checked_weight_kg", "baggage_checked_weight_kg"), ""), None)
    checked_pieces = normalize_int(nested_get(record, fields.get("baggage_checked_pieces", "baggage_checked_pieces"), ""), None)
    carry_on_kg = normalize_int(nested_get(record, fields.get("baggage_carry_on_weight_kg", "baggage_carry_on_weight_kg"), ""), None)
    alias_baggage = mapped_baggage(record)
    checked_kg = checked_kg if checked_kg is not None else alias_baggage.get("baggage_checked_weight_kg") or None
    checked_pieces = checked_pieces if checked_pieces is not None else alias_baggage.get("baggage_checked_pieces") or None
    carry_on_kg = carry_on_kg if carry_on_kg is not None else alias_baggage.get("baggage_carry_on_weight_kg") or None
    baggage_text = str(nested_get(record, fields.get("baggage_text", "baggage_text"), "")).strip()
    fare_brand = str(nested_get(record, fields.get("fare_brand", "fare_brand"), "")).strip()
    booking_url = str(nested_get(record, fields.get("booking_url", "booking_url"), "")).strip()
    identity = "|".join(
        [
            route,
            departure_date.isoformat(),
            flight_number,
            airline_id,
            str(price),
            departure_time,
            source_name,
        ]
    )
    return {
        "id": hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16],
        "route": route,
        "origin": origin,
        "origin_name": airport_name(origin),
        "origin_name_zh": airport_name(origin),
        "origin_country": origin_info.get("country", ""),
        "origin_flag": origin_info.get("flag", ""),
        "destination": destination,
        "destination_name": airport_name(destination),
        "destination_name_zh": airport_name(destination),
        "destination_country": destination_info.get("country", ""),
        "destination_flag": destination_info.get("flag", ""),
        "departure_date": departure_date.isoformat(),
        "price": price,
        "currency": str(nested_get(record, fields.get("currency", "currency"), "TWD") or "TWD"),
        "flight_number": flight_number,
        "airline_id": airline_id,
        "airline_name": str(nested_get(record, fields.get("airline_name", "airline_name"), "") or airline_rule.get("airline_name", "")),
        "airline_name_zh": airline_rule.get("airline_name", ""),
        "airline_name_en": airline_rule.get("airline_name_en", ""),
        "departure_time": departure_time,
        "arrival_time": arrival_time,
        "duration_minutes": normalize_int(nested_get(record, fields.get("duration_minutes", "duration_minutes"), ""), None),
        "transfer_count": transfer_count,
        "transfer_airports": transfer_airports,
        "transfer_airports_zh": transfer_airports_zh,
        "transfer_summary": transfer_summary,
        "baggage_checked_weight_kg": checked_kg if checked_kg is not None else "",
        "baggage_checked_pieces": checked_pieces if checked_pieces is not None else "",
        "baggage_carry_on_weight_kg": carry_on_kg if carry_on_kg is not None else "",
        "baggage_text": baggage_text,
        "fare_brand": fare_brand,
        "booking_url": booking_url,
        "source": source_name,
        "fetched_at": utc_now(),
    }


def parse_json_offer_source(text: str, source: dict[str, Any], route: str, departure_date: date) -> list[dict[str, Any]]:
    payload = json.loads(text)
    items = nested_get(payload, source.get("items_path", ""), [])
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        raise CrawlError("JSON ticket source did not return a list")
    fields = source.get("fields", {})
    return [normalize_offer(item, route, departure_date, source.get("name", "json-ticket-source"), fields) for item in items]


def parse_csv_offer_source(text: str, source: dict[str, Any], route: str, departure_date: date) -> list[dict[str, Any]]:
    origin, destination = split_route(route)
    rows = list(csv.DictReader(io.StringIO(text)))
    fields = source.get("fields", {})
    matched = []
    for row in rows:
        row_origin = row.get(fields.get("origin", "origin"), origin)
        row_destination = row.get(fields.get("destination", "destination"), destination)
        row_date = row.get(fields.get("departure_date", "departure_date"), departure_date.isoformat())
        if row_origin == origin and row_destination == destination and row_date == departure_date.isoformat():
            matched.append(normalize_offer(row, route, departure_date, source.get("name", "csv-ticket-source"), fields))
    if not matched:
        raise CrawlError("CSV ticket source had no matching offer rows")
    return matched


def parse_html_offer_source(text: str, source: dict[str, Any], route: str, departure_date: date) -> list[dict[str, Any]]:
    price_match = re.search(source.get("price_regex", ""), text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
    if not price_match:
        raise CrawlError("HTML ticket source did not match price")
    flight_match = re.search(source.get("flight_number_regex", ""), text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
    baggage_match = re.search(source.get("baggage_regex", ""), text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
    row = {
        "price": price_match.group("price") if "price" in price_match.groupdict() else price_match.group(1),
        "currency": source.get("currency", "TWD"),
        "flight_number": flight_match.group("flight") if flight_match and "flight" in flight_match.groupdict() else "",
        "baggage_checked_weight_kg": baggage_match.group("weight") if baggage_match and "weight" in baggage_match.groupdict() else "",
        "baggage_text": baggage_match.group(0) if baggage_match else "",
    }
    return [normalize_offer(row, route, departure_date, source.get("name", "html-ticket-source"), {})]


def mock_ticket_offers(config: dict[str, Any]) -> list[dict[str, Any]]:
    routes = config.get("offer_routes", ["TPE-NRT"])
    lookahead_days = int(config.get("offer_lookahead_days", 30))
    airlines = ["CI", "BR", "JX", "IT", "AE", "B7"]
    fare_brands = ["Basic", "Standard", "Flex"]
    today = date.today()
    offers = []
    for route in routes:
        origin, destination = split_route(route)
        possible_transfers = [code for code in ["HKG", "ICN", "NRT", "KIX", "SIN", "BKK"] if code not in (origin, destination)]
        for travel_day in date_range(today, lookahead_days):
            for rank in range(2):
                rng = random.Random(f"{route}:{travel_day.isoformat()}:{rank}")
                airline = rng.choice(airlines)
                checked_kg = rng.choice([0, 15, 20, 23, 30])
                checked_pieces = 0 if checked_kg == 0 else rng.choice([1, 2])
                transfer_count = rng.choice([0, 0, 1, 1, 2])
                transfer_airports = rng.sample(possible_transfers, k=min(transfer_count, len(possible_transfers)))
                row = {
                    "price": 4200 + rng.randint(0, 12000),
                    "currency": "TWD",
                    "flight_number": f"{airline}{rng.randint(100, 999)}",
                    "airline_id": airline,
                    "departure_time": f"{rng.randint(6, 22):02d}:{rng.choice([0, 10, 20, 30, 45, 55]):02d}",
                    "arrival_time": f"{rng.randint(8, 23):02d}:{rng.choice([0, 10, 20, 30, 45, 55]):02d}",
                    "duration_minutes": rng.randint(85, 420),
                    "transfer_count": transfer_count,
                    "transfer_airports": ",".join(transfer_airports),
                    "baggage_checked_weight_kg": checked_kg,
                    "baggage_checked_pieces": checked_pieces,
                    "baggage_carry_on_weight_kg": rng.choice([7, 10]),
                    "baggage_text": "No checked baggage" if checked_kg == 0 else f"Checked baggage {checked_kg}kg / {checked_pieces} piece(s)",
                    "fare_brand": rng.choice(fare_brands),
                    "booking_url": "",
                }
                offer = normalize_offer(row, route, travel_day, "mock-offer-fallback", {})
                offers.append(offer)
    return offers


def crawl_ticket_offers(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    config = config or load_config()
    routes = config.get("offer_routes", [])
    lookahead_days = int(config.get("offer_lookahead_days", 30))
    timeout_seconds = int(config.get("timeout_seconds", 20))
    delay = float(config.get("request_delay_seconds", 30.0))
    headers = {
        "User-Agent": config.get("user_agent", "flight-cache-crawler/1.0"),
        "Accept": "text/html,application/json,text/csv,*/*",
    }
    offers: list[dict[str, Any]] = []
    today = date.today()

    for source in config.get("ticket_offer_sources", []):
        if not source.get("enabled", False):
            continue
        if source.get("type") == "amadeus":
            client = AmadeusClient(config, source)
            for route in routes:
                for travel_day in date_range(today, lookahead_days):
                    try:
                        payload = client.flight_offers(route, travel_day)
                        offers.extend(parse_amadeus_offers(payload, route, travel_day))
                        time.sleep(delay)
                    except Exception as exc:
                        print(f"WARN skipped Amadeus offer {route} {travel_day}: {exc}")
            continue
        for route in routes:
            for travel_day in date_range(today, lookahead_days):
                try:
                    url = fill_template(source["url"], route, travel_day)
                    text = request_text(url, timeout_seconds, headers)
                    save_raw(f"ticket-{source.get('name', 'source')}-{route}-{travel_day}", {"url": url, "body": text[:200000]})
                    if source.get("type") == "json":
                        offers.extend(parse_json_offer_source(text, source, route, travel_day))
                    elif source.get("type") == "csv":
                        offers.extend(parse_csv_offer_source(text, source, route, travel_day))
                    elif source.get("type") == "html_regex":
                        offers.extend(parse_html_offer_source(text, source, route, travel_day))
                    else:
                        raise CrawlError(f"Unsupported ticket source type: {source.get('type')}")
                    time.sleep(delay)
                except Exception as exc:
                    print(f"WARN skipped ticket offer {source.get('name')} {route} {travel_day}: {exc}")

    if not offers and config.get("offer_mock_fallback", True):
        print("WARN using mock ticket offer fallback: no ticket provider enabled or no offers fetched")
        return mock_ticket_offers(config)
    return offers


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_csv_source(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))
