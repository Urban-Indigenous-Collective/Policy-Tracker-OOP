"""Tests for sponsor_utils indigenous annotation."""

from __future__ import annotations

from sponsor_utils import process_sponsors


class _FakeIndigenousDb:
    def __init__(self, entries: dict[str, dict]):
        self._entries = entries

    def get_indigenous_sponsor_entry(self, name: str):
        for key, entry in self._entries.items():
            if key.lower() in name.lower():
                return entry
        return None


def test_keeps_legiscan_district_over_wikipedia_career():
    db = _FakeIndigenousDb(
        {
            "Bryce Edgmon": {
                "name": "Bryce Edgmon",
                "ethnicity": "Yup'ik",
                "offices_held": "State representative 2007–present,speaker of the state house2017–2021",
            },
            "Lyman Hoffman": {
                "name": "Lyman Hoffman",
                "ethnicity": "Yup’ik",
                "offices_held": "State representative 1987–1991 and 1993–1995, state senator 1991–1993 and 1995–present",
            },
        }
    )
    _, indigenous = process_sponsors(
        "Rep Bryce Edgmon (I) - District HD-37, Sen Lyman Hoffman (D) - District SD-Y",
        db,
    )
    assert "District HD-37" in indigenous
    assert "District SD-Y" in indigenous
    assert "speaker of the state house" not in indigenous
    assert "1995–present" not in indigenous


def test_uses_mmip_coordinator_title_when_no_legiscan_role():
    db = _FakeIndigenousDb(
        {
            "Cedar Wilkie Gillette": {
                "name": "Cedar Wilkie Gillette",
                "ethnicity": "Mandan, Hidatsa, Arikara Nation",
                "offices_held": "MMIP Coordinator (District of Oregon)",
            },
        }
    )
    _, indigenous = process_sponsors("Cedar Wilkie Gillette", db)
    assert "MMIP Coordinator (District of Oregon)" in indigenous
