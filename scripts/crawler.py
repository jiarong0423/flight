from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import random
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "sources.json"
RAW_DIR = ROOT / "data" / "raw"

TDX_TOKEN_URL = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
TDX_AIR_FIDS_URL = "https://tdx.transportdata.tw/api/basic/v2/Air/FIDS/Airport/{direction}/{airport}"


class CrawlError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing crawler config: {CONFIG_PATH}")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def request_text(url: str, timeout_seconds: int, headers: dict[str, str] | None = None) -> str:
    request = Request(url, headers=headers or {})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except (HTTPError, URLError, TimeoutError) as exc:
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
        with urlopen(request, timeout=timeout_seconds) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.read().decode(charset, errors="replace"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise CrawlError(f"Token request failed: {exc}") from exc


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
        payload = request_json(
            url,
            self.timeout_seconds,
            {
                "Authorization": f"Bearer {self.token()}",
                "User-Agent": self.user_agent,
                "Accept": "application/json",
            },
        )
        if not isinstance(payload, list):
            raise CrawlError(f"TDX FIDS response is not a list: {airport} {direction}")
        save_raw(f"tdx-{airport}-{direction}", payload)
        return payload


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
    departure_name = local_name(first_value(record, "DepartureAirportName", default={}))
    arrival_name = local_name(first_value(record, "ArrivalAirportName", default={}))
    identity = "|".join([flight_date, flight_number, airport, direction, compact_time(scheduled), compact_time(estimated)])
    return {
        "id": hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16],
        "flight_date": str(flight_date),
        "direction": "departure" if is_departure else "arrival",
        "airport": airport,
        "flight_number": flight_number,
        "airline_id": airline_id,
        "airline_name": airline_name,
        "departure_airport": departure_airport,
        "departure_airport_name": departure_name,
        "arrival_airport": arrival_airport,
        "arrival_airport_name": arrival_name,
        "scheduled_time": compact_time(scheduled),
        "estimated_time": compact_time(estimated),
        "actual_time": compact_time(actual),
        "terminal": str(terminal or ""),
        "gate": str(gate or ""),
        "remark": str(remark or ""),
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

    try:
        for airport in airports:
            for direction in directions:
                payload = client.fids_airport(airport, direction, top)
                items.extend(normalize_tdx_record(row, airport, direction) for row in payload)
                time.sleep(delay)
    except Exception as exc:
        if config.get("mock_fallback", True):
            print(f"WARN using mock fallback: {exc}")
            return mock_tdx_records(config)
        raise

    return items


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_csv_source(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))
