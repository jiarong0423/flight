from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "config" / "airline_rules.json"


def load_airline_rules() -> dict[str, Any]:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def standard_airline_id(value: Any) -> str:
    text = str(value or "").strip().upper()
    match = re.match(r"([A-Z0-9]{2})", text)
    return match.group(1) if match else text


def merged_rule(airline_id: str, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = registry or load_airline_rules()
    code = standard_airline_id(airline_id)
    rule = dict(registry.get("default_rule", {}))
    rule.update(registry.get("airlines", {}).get(code, {}))
    rule["airline_id"] = code
    return rule


def value_present(value: Any) -> bool:
    return value not in (None, "", "unknown")


def enrich_offer_with_airline_rule(offer: dict[str, Any], registry: dict[str, Any] | None = None) -> dict[str, Any]:
    enriched = dict(offer)
    rule = merged_rule(enriched.get("airline_id") or enriched.get("flight_number"), registry)
    enriched["airline_id"] = rule["airline_id"] or enriched.get("airline_id", "")
    if not value_present(enriched.get("airline_name")):
        enriched["airline_name"] = rule.get("airline_name", "")
    enriched["airline_name_zh"] = rule.get("airline_name", enriched.get("airline_name", ""))
    enriched["airline_name_en"] = rule.get("airline_name_en", "")
    enriched["airline_rule_status"] = rule.get("rule_status", "unknown")
    enriched["airline_rule_source_url"] = rule.get("rule_source_url", "")

    if not value_present(enriched.get("baggage_checked_weight_kg")):
        enriched["baggage_checked_weight_kg"] = rule.get("checked_baggage_weight_kg", "")
    if not value_present(enriched.get("baggage_checked_pieces")):
        enriched["baggage_checked_pieces"] = rule.get("checked_baggage_pieces", "")
    if not value_present(enriched.get("baggage_carry_on_weight_kg")):
        enriched["baggage_carry_on_weight_kg"] = rule.get("carry_on_weight_kg", "")
    if not value_present(enriched.get("baggage_text")):
        checked = rule.get("checked_baggage_included", "unknown")
        carry = rule.get("carry_on_included", "unknown")
        enriched["baggage_text"] = f"checked={checked}; carry_on={carry}"

    enriched["change_rule"] = enriched.get("change_rule") or rule.get("change_rule", "unknown")
    enriched["refund_rule"] = enriched.get("refund_rule") or rule.get("refund_rule", "unknown")
    enriched["no_show_rule"] = enriched.get("no_show_rule") or rule.get("no_show_rule", "unknown")
    return enriched


def public_registry(registry: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = registry or load_airline_rules()
    return {
        "schema_version": registry.get("schema_version"),
        "updated_at": registry.get("updated_at"),
        "standard_fields": registry.get("standard_fields", []),
        "airlines": registry.get("airlines", {}),
    }
