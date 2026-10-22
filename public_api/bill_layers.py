"""Classify Live bills for map filter layers (state / national / DOJ)."""

from __future__ import annotations

from discovery.federal_schema import FEDERAL_STATE
from public_api.doj_detection import is_doj_initiative_bill
from public_api.states import is_map_state_code


def is_state_legislation_bill(bill: dict) -> bool:
    if not is_map_state_code(str(bill.get("state") or "")):
        return False
    if is_doj_initiative_bill(bill):
        return False
    return True


def is_national_legislation_bill(bill: dict) -> bool:
    state = str(bill.get("state") or "")
    if state != FEDERAL_STATE:
        return False
    if is_doj_initiative_bill(bill):
        return False
    return True


def bill_matches_map_layers(
    bill: dict,
    *,
    state_legislation: bool,
    national_legislation: bool,
    doj_initiative: bool,
) -> bool:
    if state_legislation and is_state_legislation_bill(bill):
        return True
    if national_legislation and is_national_legislation_bill(bill):
        return True
    if doj_initiative and is_doj_initiative_bill(bill):
        return True
    return False
