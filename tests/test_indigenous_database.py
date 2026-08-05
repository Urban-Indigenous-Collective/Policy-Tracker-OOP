import json
from pathlib import Path

import pytest

from indigenous_database import IndigenousDatabase


class FakeWiki:
    def __init__(self, names=None):
        self.names = names or [
            {
                "name": f"Politician {i}",
                "party": "N/A",
                "state": "N/A",
                "ethnicity": "N/A",
                "offices_held": "N/A",
            }
            for i in range(25)
        ]
        self.list_calls = 0
        self.category_calls = 0

    def parse_list_page(self, url):
        self.list_calls += 1
        return list(self.names)

    def parse_category_and_subcategories(self, url):
        self.category_calls += 1
        return []


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "roster.json"
    db = IndigenousDatabase(db_path=path, backup_dir=tmp_path / "backups", wikipedia_client=FakeWiki())
    db.build_database()
    db.save_to_disk()

    other = IndigenousDatabase(db_path=path, backup_dir=tmp_path / "backups", wikipedia_client=FakeWiki())
    assert other.load_from_disk()
    assert len(other.database) == len(db.database)
    assert other.built_at == db.built_at


def test_ensure_loaded_uses_disk_without_scrape(tmp_path):
    path = tmp_path / "roster.json"
    payload = {
        "built_at": "2026-08-01T00:00:00Z",
        "source": "wikipedia",
        "count": 2,
        "politicians": [
            {"name": "Ada Deer", "party": "N/A", "state": "WI", "ethnicity": "Menominee", "offices_held": "N/A"},
            {"name": "Deb Haaland", "party": "D", "state": "NM", "ethnicity": "Laguna Pueblo", "offices_held": "N/A"},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    wiki = FakeWiki()
    db = IndigenousDatabase(db_path=path, backup_dir=tmp_path / "backups", wikipedia_client=wiki)
    assert db.ensure_loaded() == "disk"
    assert wiki.list_calls == 0
    assert len(db.database) == 2


def test_refresh_backs_up_and_rejects_thin_scrape(tmp_path):
    path = tmp_path / "roster.json"
    backups = tmp_path / "backups"
    good = FakeWiki()
    db = IndigenousDatabase(db_path=path, backup_dir=backups, wikipedia_client=good)
    db.build_database()
    db.save_to_disk()
    original_count = len(db.database)

    thin = FakeWiki(
        names=[
            {
                "name": "Only One",
                "party": "N/A",
                "state": "N/A",
                "ethnicity": "N/A",
                "offices_held": "N/A",
            }
        ]
    )
    db.wikipedia_client = thin
    with pytest.raises(RuntimeError, match="only 9 entries"):
        # 1 from list + 8 manual MMIP/Olson adjustments
        db.refresh(min_count=20)

    assert path.is_file()
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded["count"] == original_count
    assert len(db.database) == original_count


def test_refresh_writes_backup(tmp_path):
    path = tmp_path / "roster.json"
    backups = tmp_path / "backups"
    db = IndigenousDatabase(db_path=path, backup_dir=backups, wikipedia_client=FakeWiki())
    db.build_database()
    db.save_to_disk()

    db.wikipedia_client = FakeWiki(
        names=[
            {
                "name": f"New Politician {i}",
                "party": "N/A",
                "state": "N/A",
                "ethnicity": "N/A",
                "offices_held": "N/A",
            }
            for i in range(30)
        ]
    )
    stats = db.refresh(min_count=20)
    assert stats["count"] >= 30
    assert stats["backup_path"]
    assert Path(stats["backup_path"]).is_file()
    assert "New Politician 0" in {p["name"] for p in db.database}


def test_reload_if_stale(tmp_path):
    path = tmp_path / "roster.json"
    db = IndigenousDatabase(db_path=path, backup_dir=tmp_path / "backups", wikipedia_client=FakeWiki())
    db.build_database()
    db.save_to_disk()

    # Simulate another process writing a newer cache
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["politicians"].append(
        {
            "name": "Fresh Entry",
            "party": "N/A",
            "state": "N/A",
            "ethnicity": "N/A",
            "offices_held": "N/A",
        }
    )
    payload["count"] = len(payload["politicians"])
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert db.reload_if_stale()
    assert any(p["name"] == "Fresh Entry" for p in db.database)


def test_is_indigenous_sponsor_match(tmp_path):
    db = IndigenousDatabase(
        db_path=tmp_path / "roster.json",
        backup_dir=tmp_path / "backups",
        wikipedia_client=FakeWiki(),
    )
    db.database = [
        {
            "name": "Donald Olson",
            "party": "Democratic",
            "state": "Alaska",
            "ethnicity": "Iñupiat",
            "offices_held": "N/A",
        }
    ]
    assert db.is_indigenous_sponsor("Sen. Donald Olson (D)")
    assert not db.is_indigenous_sponsor("Sen. Totally Unknown (R)")


def test_running_wolf_enriches_from_list_page_twin(tmp_path):
    """Spaced bill spelling must pick up Blackfeet ethnicity from Runningwolf twin."""
    db = IndigenousDatabase(
        db_path=tmp_path / "roster.json",
        backup_dir=tmp_path / "backups",
        wikipedia_client=FakeWiki(),
    )
    db.database = [
        {
            "name": "Tyson Runningwolf",
            "party": "Democratic",
            "state": "Montana",
            "ethnicity": "Blackfeet Nation",
            "offices_held": "Representative for Montana house district 16 (2019–present)",
        },
        {
            "name": "Tyson Running Wolf",
            "party": "N/A",
            "state": "N/A",
            "ethnicity": "N/A",
            "offices_held": "N/A",
        },
    ]
    entry = db.get_indigenous_sponsor_entry("Rep Tyson Running Wolf (D)")
    assert entry is not None
    assert entry["ethnicity"] == "Blackfeet Nation"
    assert "Representative" in entry["offices_held"]


def test_process_sponsors_keeps_match_without_ethnicity(tmp_path):
    from sponsor_utils import process_sponsors

    db = IndigenousDatabase(
        db_path=tmp_path / "roster.json",
        backup_dir=tmp_path / "backups",
        wikipedia_client=FakeWiki(),
    )
    db.database = [
        {
            "name": "Only Category Entry",
            "party": "N/A",
            "state": "N/A",
            "ethnicity": "N/A",
            "offices_held": "N/A",
        }
    ]
    processed, indigenous = process_sponsors(
        "Rep Only Category Entry (D) - District HD-1", db
    )
    assert "Only Category Entry" in processed
    assert indigenous
    assert "Only Category Entry" in indigenous
    # Matched as indigenous, but no fabricated tribe label from N/A ethnicity
    assert "(N/A)" not in indigenous


def test_process_sponsors_running_wolf_annotated(tmp_path):
    from sponsor_utils import process_sponsors

    db = IndigenousDatabase(
        db_path=tmp_path / "roster.json",
        backup_dir=tmp_path / "backups",
        wikipedia_client=FakeWiki(),
    )
    db.database = [
        {
            "name": "Tyson Runningwolf",
            "party": "Democratic",
            "state": "Montana",
            "ethnicity": "Blackfeet Nation",
            "offices_held": "Representative for Montana house district 16",
        },
        {
            "name": "Tyson Running Wolf",
            "party": "N/A",
            "state": "N/A",
            "ethnicity": "N/A",
            "offices_held": "N/A",
        },
    ]
    processed, indigenous = process_sponsors(
        "Rep Tyson Running Wolf (D) - District HD-016", db
    )
    assert "Blackfeet Nation" in processed
    assert "Blackfeet Nation" in indigenous


def test_rejects_near_miss_surnames(tmp_path):
    db = IndigenousDatabase(
        db_path=tmp_path / "roster.json",
        backup_dir=tmp_path / "backups",
        wikipedia_client=FakeWiki(),
    )
    db.database = [
        {
            "name": "Kevin Killer",
            "party": "Democratic",
            "state": "South Dakota",
            "ethnicity": "Oglala Sioux",
            "offices_held": "N/A",
        },
        {
            "name": "Robert William Wilcox",
            "party": "N/A",
            "state": "N/A",
            "ethnicity": "Native Hawaiian",
            "offices_held": "N/A",
        },
    ]
    assert db.get_indigenous_sponsor_entry("Rep Kevin Kiley (R)") is None
    assert db.get_indigenous_sponsor_entry("Rep Robert Williams (D)") is None


def test_hyphenated_surname_still_matches(tmp_path):
    db = IndigenousDatabase(
        db_path=tmp_path / "roster.json",
        backup_dir=tmp_path / "backups",
        wikipedia_client=FakeWiki(),
    )
    db.database = [
        {
            "name": "Mary Kunesh",
            "party": "DFL",
            "state": "Minnesota",
            "ethnicity": "Standing Rock Dakota / Native Hawaiian",
            "offices_held": "N/A",
        }
    ]
    entry = db.get_indigenous_sponsor_entry("Rep Mary Kunesh-Podein (D)")
    assert entry is not None
    assert "Standing Rock" in entry["ethnicity"]


def test_secretary_haaland_matches(tmp_path):
    db = IndigenousDatabase(
        db_path=tmp_path / "roster.json",
        backup_dir=tmp_path / "backups",
        wikipedia_client=FakeWiki(),
    )
    db.database = [
        {
            "name": "Deb Haaland",
            "party": "Democratic",
            "state": "New Mexico",
            "ethnicity": "Laguna Pueblo",
            "offices_held": "N/A",
        }
    ]
    entry = db.get_indigenous_sponsor_entry("Secretary Deb Haaland (D)")
    assert entry is not None
    assert entry["ethnicity"] == "Laguna Pueblo"


def test_derrick_lente_middle_initial(tmp_path):
    overrides = tmp_path / "overrides.json"
    overrides.write_text(
        json.dumps(
            {
                "ethnicity": {"Derrick Lente": "Sandia & Isleta Pueblo"},
                "aliases": {"Derrick J. Lente": "Derrick Lente"},
            }
        ),
        encoding="utf-8",
    )
    db = IndigenousDatabase(
        db_path=tmp_path / "roster.json",
        backup_dir=tmp_path / "backups",
        overrides_path=overrides,
        wikipedia_client=FakeWiki(),
    )
    db.database = [
        {
            "name": "Derrick Lente",
            "party": "Democratic",
            "state": "New Mexico",
            "ethnicity": "Sandia & Isleta Pueblo",
            "offices_held": "N/A",
        }
    ]
    entry = db.get_indigenous_sponsor_entry("Representative Derrick J. Lente [D]")
    assert entry is not None
    assert "Sandia" in entry["ethnicity"]


def test_ethnicity_overrides_merge_after_dedupe(tmp_path):
    overrides = tmp_path / "overrides.json"
    overrides.write_text(
        json.dumps(
            {
                "ethnicity": {
                    "James Ramos": "Serrano/Cahuilla",
                    "Sharice Davids": "Ho-Chunk",
                }
            }
        ),
        encoding="utf-8",
    )
    db = IndigenousDatabase(
        db_path=tmp_path / "roster.json",
        backup_dir=tmp_path / "backups",
        overrides_path=overrides,
        wikipedia_client=FakeWiki(),
    )
    db.database = db._finalize_roster(
        [
            {
                "name": "James Ramos",
                "party": "Democratic",
                "state": "California",
                "ethnicity": "N/A",
                "offices_held": "N/A",
            },
            {
                "name": "Sharice Davids",
                "party": "Democratic",
                "state": "Kansas",
                "ethnicity": "N/A",
                "offices_held": "N/A",
            },
        ]
    )
    ramos = next(p for p in db.database if p["name"] == "James Ramos")
    davids = next(p for p in db.database if p["name"] == "Sharice Davids")
    assert ramos["ethnicity"] == "Serrano/Cahuilla"
    assert davids["ethnicity"] == "Ho-Chunk"

    from sponsor_utils import process_sponsors

    _, indigenous = process_sponsors("Rep James Ramos (D) - District HD-040", db)
    assert "Serrano/Cahuilla" in indigenous
    _, indigenous = process_sponsors("Rep Sharice Davids (D) - District HD-KS-3", db)
    assert "Ho-Chunk" in indigenous


def test_load_from_disk_applies_enrichment_sidecar(tmp_path):
    enrichment = tmp_path / "enrichment.json"
    enrichment.write_text(
        json.dumps(
            {
                "entries": {
                    "janedoe": {
                        "roster_name": "Jane Doe",
                        "ethnicity": "Cherokee Nation",
                        "status": "accepted",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    roster = tmp_path / "roster.json"
    roster.write_text(
        json.dumps(
            {
                "built_at": "2026-08-01T00:00:00Z",
                "source": "wikipedia",
                "count": 1,
                "politicians": [
                    {
                        "name": "Jane Doe",
                        "party": "N/A",
                        "state": "N/A",
                        "ethnicity": "N/A",
                        "offices_held": "N/A",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    db = IndigenousDatabase(
        db_path=roster,
        backup_dir=tmp_path / "backups",
        enrichment_path=enrichment,
        wikipedia_client=FakeWiki(),
    )
    assert db.load_from_disk()
    assert db.database[0]["ethnicity"] == "Cherokee Nation"


def test_known_ethnicity_not_overwritten_by_enrichment(tmp_path):
    enrichment = tmp_path / "enrichment.json"
    enrichment.write_text(
        json.dumps(
            {
                "entries": {
                    "debhaaland": {
                        "roster_name": "Deb Haaland",
                        "ethnicity": "Wrong Tribe",
                        "status": "accepted",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    roster = tmp_path / "roster.json"
    roster.write_text(
        json.dumps(
            {
                "built_at": "2026-08-01T00:00:00Z",
                "source": "wikipedia",
                "count": 1,
                "politicians": [
                    {
                        "name": "Deb Haaland",
                        "party": "Democratic",
                        "state": "New Mexico",
                        "ethnicity": "Laguna Pueblo",
                        "offices_held": "N/A",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    db = IndigenousDatabase(
        db_path=roster,
        backup_dir=tmp_path / "backups",
        enrichment_path=enrichment,
        wikipedia_client=FakeWiki(),
    )
    db.load_from_disk()
    assert db.database[0]["ethnicity"] == "Laguna Pueblo"


def test_wonda_johnson_alias(tmp_path):
    overrides = tmp_path / "overrides.json"
    overrides.write_text(
        json.dumps(
            {
                "ethnicity": {"Doreen Wonda Johnson": "Navajo"},
                "aliases": {"Wonda Johnson": "Doreen Wonda Johnson"},
            }
        ),
        encoding="utf-8",
    )
    db = IndigenousDatabase(
        db_path=tmp_path / "roster.json",
        backup_dir=tmp_path / "backups",
        overrides_path=overrides,
        wikipedia_client=FakeWiki(),
    )
    db.database = [
        {
            "name": "Doreen Wonda Johnson",
            "party": "Democratic",
            "state": "New Mexico",
            "ethnicity": "Navajo",
            "offices_held": "N/A",
        }
    ]
    entry = db.get_indigenous_sponsor_entry("Wonda Johnson")
    assert entry is not None
    assert entry["ethnicity"] == "Navajo"
