from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LOOKUPS_PATH = ROOT / "config" / "lookups.json"


def load_lookups() -> dict[str, Any]:
    return json.loads(LOOKUPS_PATH.read_text(encoding="utf-8"))


def airport_name(code: Any, lookups: dict[str, Any] | None = None, locale: str = "zh_tw") -> str:
    lookups = lookups or load_lookups()
    code = str(code or "").strip().upper()
    airport = lookups.get("airports", {}).get(code, {})
    return airport.get(locale) or airport.get("en") or ""


def airport_info(code: Any, lookups: dict[str, Any] | None = None) -> dict[str, Any]:
    lookups = lookups or load_lookups()
    code = str(code or "").strip().upper()
    airport = lookups.get("airports", {}).get(code, {})
    return {
        "airport_id": code,
        "airport_name_zh": airport.get("zh_tw", ""),
        "airport_name_en": airport.get("en", ""),
        "country": airport.get("country", ""),
        "flag": airport.get("flag", ""),
    }


def standard_direction(value: Any, lookups: dict[str, Any] | None = None) -> str:
    lookups = lookups or load_lookups()
    text = str(value or "").strip()
    return lookups.get("directions", {}).get(text, text.lower())


def standard_status(value: Any, lookups: dict[str, Any] | None = None) -> str:
    lookups = lookups or load_lookups()
    text = str(value or "").strip()
    for label, status in lookups.get("status_aliases", {}).items():
        if label.lower() in text.lower():
            return status
    return "unknown" if not text else "other"


def find_alias_value(record: dict[str, Any], aliases: list[str]) -> Any:
    for alias in aliases:
        current: Any = record
        found = True
        for part in alias.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                found = False
                break
        if found and current not in (None, ""):
            return current
        if alias in record and record[alias] not in (None, ""):
            return record[alias]
    return ""


def number_from_text(value: Any) -> int | str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"-?\d+", str(value))
    return int(match.group(0)) if match else ""


def mapped_baggage(record: dict[str, Any], lookups: dict[str, Any] | None = None) -> dict[str, Any]:
    lookups = lookups or load_lookups()
    aliases = lookups.get("baggage_aliases", {})
    return {
        "baggage_checked_weight_kg": number_from_text(find_alias_value(record, aliases.get("checked_baggage_weight_kg", []))),
        "baggage_checked_pieces": number_from_text(find_alias_value(record, aliases.get("checked_baggage_pieces", []))),
        "baggage_carry_on_weight_kg": number_from_text(find_alias_value(record, aliases.get("carry_on_weight_kg", []))),
    }


def public_lookups(lookups: dict[str, Any] | None = None) -> dict[str, Any]:
    lookups = lookups or load_lookups()
    return {
        "schema_version": lookups.get("schema_version"),
        "updated_at": lookups.get("updated_at"),
        "airports": lookups.get("airports", {}),
        "directions": lookups.get("directions", {}),
        "status_aliases": lookups.get("status_aliases", {}),
    }
