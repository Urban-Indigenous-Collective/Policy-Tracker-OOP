from __future__ import annotations

import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fuzzywuzzy import fuzz

from wikipedia_api_client import WikipediaAPIClient

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/indigenous_politicians.json")
DEFAULT_BACKUP_DIR = Path("data/backups")
DEFAULT_OVERRIDES_PATH = Path("data/indigenous_ethnicity_overrides.json")
DEFAULT_MIN_COUNT = 500


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_na(value: str | None) -> bool:
    return not value or value.strip() in ("", "N/A")


class IndigenousDatabase:
    def __init__(
        self,
        db_path: Path | str | None = None,
        backup_dir: Path | str | None = None,
        overrides_path: Path | str | None = None,
        wikipedia_client: WikipediaAPIClient | None = None,
    ):
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.backup_dir = Path(backup_dir or DEFAULT_BACKUP_DIR)
        self.overrides_path = Path(overrides_path or DEFAULT_OVERRIDES_PATH)
        self.wikipedia_client = wikipedia_client or WikipediaAPIClient()
        self.database: list[dict] = []
        self.built_at: str | None = None
        self._disk_mtime: float | None = None
        self._ethnicity_overrides: dict[str, str] = {}
        self._name_aliases: dict[str, str] = {}
        self._load_ethnicity_overrides()

    def build_category_dict(self, database, url, ethnicity):
        politicians_category = self.wikipedia_client.parse_category_and_subcategories(url)
        for politician in politicians_category:
            politician_dict = {
                "name": politician,
                "party": "N/A",
                "state": "N/A",
                "ethnicity": ethnicity,
                "offices_held": "N/A",
            }
            database.append(politician_dict)

    def build_database(self):
        list_url = "https://en.wikipedia.org/wiki/List_of_Native_American_politicians"
        self.database = self.wikipedia_client.parse_list_page(list_url)

        self.build_category_dict(self.database, "Native_American_state_legislators", "N/A")
        self.build_category_dict(self.database, "21st-century Native American politicians", "N/A")
        self.build_category_dict(self.database, "Native_Hawaiian_politicians", "Native Hawaiian")
        self.manual_adjustments()
        self.database = self._finalize_roster(self.database)
        self.built_at = _utc_now_iso()
        logger.info("Built indigenous database with %d entries", len(self.database))

    def manual_adjustments(self):
        for i, entry in enumerate(self.database):
            if entry["name"].lower() in ["donny olson", "donald olson"]:
                self.database[i] = {
                    "name": "Donald Olson",
                    "party": "Democratic",
                    "state": "Alaska",
                    "ethnicity": "Iñupiat",
                    "offices_held": "N/A",
                }
                break
        else:
            self.database.append(
                {
                    "name": "Donald Olson",
                    "party": "Democratic",
                    "state": "Alaska",
                    "ethnicity": "Iñupiat",
                    "offices_held": "N/A",
                }
            )

        for manual in (
            {
                "name": "Ingrid Cumberlidge",
                "party": "N/A",
                "state": "Alaska",
                "ethnicity": "Aleut, Tlingit",
                "offices_held": "MMIP Coordinator (District of Alaska)",
            },
            {
                "name": "Ingrid Goodyear",
                "party": "N/A",
                "state": "Alaska",
                "ethnicity": "Aleut, Tlingit",
                "offices_held": "MMIP Coordinator (Districts of Alaska & Great Plains)",
            },
            {
                "name": "Cedar Wilkie Gillette",
                "party": "N/A",
                "state": "Oregon",
                "ethnicity": "Mandan, Hidatsa, Arikara Nation, Turtle Mountain Band of Chippewa",
                "offices_held": "MMIP Coordinator (Northwest Region), MMIP Coordinator (District of Oregon)",
            },
            {
                "name": "Shaniya Decker",
                "party": "N/A",
                "state": "New Mexico",
                "ethnicity": "Salish, Nakoda, Turtle Mountain Band of Chippewa",
                "offices_held": "MMIP Coordinator (District of New Mexico)",
            },
            {
                "name": "Patti Buhl",
                "party": "N/A",
                "state": "Oklahoma",
                "ethnicity": "Citizen of the Cherokee Nation",
                "offices_held": "MMIP Coordinator (District of Northern Oklahoma)",
            },
            {
                "name": "Bree Black Horse",
                "party": "N/A",
                "state": "Washington",
                "ethnicity": "Seminole Nation of Oklahoma",
                "offices_held": "MMIP Coordinator (District of Eastern Washington)",
            },
            {
                "name": "Allison Morrisette",
                "party": "N/A",
                "state": "South Dakota",
                "ethnicity": "Oglala Lakota",
                "offices_held": "MMIP Coordinator (South Dakota)",
            },
        ):
            self.database.append(manual)

    @staticmethod
    def _normalize_roster_name(name: str) -> str:
        cleaned = IndigenousDatabase.parse_name_from_input(name)
        cleaned = re.sub(r"\(.*?\)", "", cleaned).strip()
        cleaned = cleaned.split("-", 1)[0].strip()
        cleaned = cleaned.replace("–", "-")
        cleaned = re.sub(r"\s+", " ", cleaned).lower()
        # Collapse spaced compound surnames: "running wolf" -> "runningwolf"
        return cleaned.replace(" ", "")

    @staticmethod
    def _pick_richer(existing: str | None, candidate: str | None) -> str:
        if _is_na(existing):
            return candidate or "N/A"
        if _is_na(candidate):
            return existing or "N/A"
        if len(candidate) > len(existing):
            return candidate
        return existing

    @classmethod
    def _merge_entries(cls, entries: list[dict]) -> dict:
        merged = dict(entries[0])
        for entry in entries[1:]:
            merged["party"] = cls._pick_richer(merged.get("party"), entry.get("party"))
            merged["state"] = cls._pick_richer(merged.get("state"), entry.get("state"))
            merged["ethnicity"] = cls._pick_richer(merged.get("ethnicity"), entry.get("ethnicity"))
            merged["offices_held"] = cls._pick_richer(
                merged.get("offices_held"), entry.get("offices_held")
            )
        return merged

    @classmethod
    def _dedupe_roster(cls, records: list[dict]) -> list[dict]:
        groups: dict[str, list[dict]] = {}
        for record in records:
            key = cls._normalize_roster_name(record.get("name") or "")
            if not key:
                continue
            groups.setdefault(key, []).append(record)

        deduped: list[dict] = []
        for entries in groups.values():
            deduped.append(cls._merge_entries(entries))
        deduped.sort(key=lambda r: (r.get("name") or "").lower())
        return deduped

    def _load_ethnicity_overrides(self) -> None:
        self._ethnicity_overrides = {}
        self._name_aliases = {}
        if not self.overrides_path.is_file():
            return
        payload = json.loads(self.overrides_path.read_text(encoding="utf-8"))
        self._ethnicity_overrides = dict(payload.get("ethnicity") or {})
        self._name_aliases = dict(payload.get("aliases") or {})

    @staticmethod
    def _strip_middle_initial(name: str) -> str:
        parts = name.split()
        if len(parts) >= 3 and re.fullmatch(r"[A-Za-z]\.?", parts[1]):
            return f"{parts[0]} {' '.join(parts[2:])}"
        return name

    def _lookup_name(self, name: str) -> str:
        cleaned = self._clean_name(self.parse_name_from_input(name))
        return self.normalize_hyphens_and_en_dashes(cleaned).lower().strip()

    def _compact_name_key(self, name: str) -> str:
        cleaned = self._clean_name(self.parse_name_from_input(name))
        cleaned = self._strip_middle_initial(cleaned)
        return self._normalize_roster_name(cleaned)

    def _resolve_alias(self, name: str) -> str:
        lookup = self._lookup_name(name)
        for alias, canonical in self._name_aliases.items():
            if self._lookup_name(alias) == lookup:
                return canonical
        return self._clean_name(self.parse_name_from_input(name))

    def _resolve_input_name(self, input_name: str) -> str:
        parsed = self.parse_name_from_input(input_name)
        cleaned = self._clean_name(parsed)
        cleaned = self._resolve_alias(cleaned)
        stripped = self._strip_middle_initial(cleaned)
        if stripped != cleaned:
            cleaned = self._resolve_alias(stripped)
        return cleaned

    def _apply_ethnicity_overrides(self, records: list[dict]) -> list[dict]:
        if not self._ethnicity_overrides:
            return records
        override_keys = {
            self._compact_name_key(name): ethnicity
            for name, ethnicity in self._ethnicity_overrides.items()
        }
        for record in records:
            key = self._compact_name_key(record.get("name") or "")
            if key in override_keys:
                record["ethnicity"] = override_keys[key]
        return records

    def _finalize_roster(self, records: list[dict]) -> list[dict]:
        records = self._dedupe_roster(records)
        return self._apply_ethnicity_overrides(records)

    def save_to_disk(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "built_at": self.built_at or _utc_now_iso(),
            "source": "wikipedia",
            "count": len(self.database),
            "politicians": self.database,
        }
        self.db_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        self._disk_mtime = self.db_path.stat().st_mtime
        self.built_at = payload["built_at"]

    def load_from_disk(self) -> bool:
        if not self.db_path.is_file():
            return False
        payload = json.loads(self.db_path.read_text(encoding="utf-8"))
        records = payload.get("politicians") or payload.get("records") or []
        self.database = self._finalize_roster(records)
        self.built_at = payload.get("built_at")
        self._disk_mtime = self.db_path.stat().st_mtime
        return True

    def ensure_loaded(self) -> str:
        if self.load_from_disk():
            logger.info(
                "Loaded indigenous DB from %s (count=%d built_at=%s)",
                self.db_path,
                len(self.database),
                self.built_at,
            )
            return "disk"
        logger.warning("No indigenous cache at %s; scraping Wikipedia", self.db_path)
        self.build_database()
        self.save_to_disk()
        return "wikipedia_scrape"

    def reload_if_stale(self) -> bool:
        if not self.db_path.is_file():
            return False
        mtime = self.db_path.stat().st_mtime
        if self._disk_mtime is not None and mtime <= self._disk_mtime:
            return False
        return self.load_from_disk()

    def _backup_current_cache(self) -> str | None:
        if not self.db_path.is_file():
            return None
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup_path = self.backup_dir / f"indigenous_politicians-{stamp}.json"
        shutil.copy2(self.db_path, backup_path)
        return str(backup_path)

    def refresh(self, min_count: int | None = None) -> dict:
        threshold = min_count
        if threshold is None:
            threshold = int(os.getenv("INDIGENOUS_DB_MIN_COUNT", str(DEFAULT_MIN_COUNT)))

        backup_path = self._backup_current_cache()
        previous = list(self.database)
        previous_count = len(previous)

        self.build_database()
        new_count = len(self.database)
        if new_count < threshold:
            self.database = previous
            if self.db_path.is_file():
                self.load_from_disk()
            raise RuntimeError(
                f"Indigenous roster refresh rejected: only {new_count} entries "
                f"(minimum {threshold}); kept previous cache ({previous_count} entries)"
            )

        self.save_to_disk()
        return {
            "count": new_count,
            "built_at": self.built_at,
            "path": str(self.db_path),
            "backup_path": backup_path,
        }

    def dedupe_disk_cache(self) -> dict:
        if not self.load_from_disk():
            raise FileNotFoundError(f"No roster cache at {self.db_path}")
        before = len(json.loads(self.db_path.read_text(encoding="utf-8")).get("politicians") or [])
        backup_path = self._backup_current_cache()
        self.built_at = _utc_now_iso()
        self.save_to_disk()
        return {
            "before": before,
            "after": len(self.database),
            "backup_path": backup_path,
            "path": str(self.db_path),
            "built_at": self.built_at,
        }

    def print_database(self):
        for politician in self.database:
            print(politician["name"] + " " + politician["ethnicity"])

    def get_all_records(self):
        self.ensure_loaded()
        return self.database

    @staticmethod
    def parse_name_from_input(user_input):
        name_part = re.sub(
            r"^(Rep\.?\s|Representative\s|Sen\.?\s|Senator\s|Gov\.?\s|Governor\s|Secretary\s|Attorney General\s)"
            r"|\s*\[[D|R].*?\]|\s*\([D|R].*?\).*$",
            "",
            user_input,
            flags=re.I,
        )
        name_part = name_part.strip()
        return name_part.replace("–", "-")

    def normalize_hyphens_and_en_dashes(self, name):
        return name.replace("–", "-")

    def _clean_name(self, name: str) -> str:
        name = re.sub(r"\(.*?\)", "", name).strip()
        name = name.split("-", 1)[0].strip()
        return name

    def _last_name(self, name: str) -> str:
        parts = name.split()
        return parts[-1] if parts else name

    def _is_confident_match(self, normalized_input: str, db_entry: dict, match_score: int) -> bool:
        if match_score <= 90:
            return False

        db_name = self._clean_name(self.parse_name_from_input(db_entry.get("name") or ""))
        normalized_db_name = self.normalize_hyphens_and_en_dashes(db_name).lower()

        if self._normalize_roster_name(normalized_input) == self._normalize_roster_name(
            normalized_db_name
        ):
            return True

        if self._compact_name_key(normalized_input) == self._compact_name_key(normalized_db_name):
            return True

        token_score = fuzz.token_sort_ratio(normalized_input, normalized_db_name)
        if token_score >= 88:
            return True

        input_parts = normalized_input.split()
        db_parts = normalized_db_name.split()
        if len(input_parts) >= 2 and len(db_parts) >= 2:
            input_last = self._last_name(normalized_input)
            db_last = self._last_name(normalized_db_name)
            if fuzz.ratio(input_last, db_last) >= 92:
                input_first = input_parts[0]
                db_first = db_parts[0]
                if fuzz.ratio(input_first, db_first) >= 85:
                    return True

            input_stripped = self._strip_middle_initial(normalized_input)
            db_stripped = self._strip_middle_initial(normalized_db_name)
            if input_stripped != normalized_input or db_stripped != normalized_db_name:
                if self._compact_name_key(input_stripped) == self._compact_name_key(db_stripped):
                    return True

        return False

    def _match_score(self, normalized_input: str, db_entry: dict) -> int:
        db_name = db_entry.get("name") or ""
        cleaned_db_name = self._clean_name(self.parse_name_from_input(db_name))
        normalized_db_name = self.normalize_hyphens_and_en_dashes(cleaned_db_name).lower()
        normalized_db_compact = normalized_db_name.replace(" ", "")

        score = fuzz.partial_ratio(normalized_input, normalized_db_name)
        compact_score = fuzz.partial_ratio(normalized_input.replace(" ", ""), normalized_db_compact)
        return max(score, compact_score)

    def _entry_quality(self, entry: dict) -> tuple[int, int, int, int]:
        ethnicity_known = 0 if _is_na(entry.get("ethnicity")) else 1
        offices_known = 0 if _is_na(entry.get("offices_held")) else 1
        party_known = 0 if _is_na(entry.get("party")) else 1
        state_known = 0 if _is_na(entry.get("state")) else 1
        return (ethnicity_known, offices_known, party_known, state_known)

    def is_indigenous_sponsor(self, input_name):
        parsed_input_name = self.parse_name_from_input(self._resolve_input_name(input_name))
        normalized_input_name = self.normalize_hyphens_and_en_dashes(parsed_input_name).lower()

        for db_entry in self.database:
            match_score = self._match_score(normalized_input_name, db_entry)
            if match_score > 90 and self._is_confident_match(
                normalized_input_name, db_entry, match_score
            ):
                return True
        return False

    def get_indigenous_sponsor_entry(self, input_name):
        resolved_name = self._resolve_input_name(input_name)
        parsed_input_name = self.parse_name_from_input(resolved_name)
        cleaned_input_name = self._clean_name(parsed_input_name)
        normalized_input_name = self.normalize_hyphens_and_en_dashes(cleaned_input_name).lower()

        threshold = 90
        scored: list[tuple[int, dict]] = []

        for db_entry in self.database:
            match_score = self._match_score(normalized_input_name, db_entry)
            if match_score > threshold and self._is_confident_match(
                normalized_input_name, db_entry, match_score
            ):
                scored.append((match_score, db_entry))

        if not scored:
            return None

        matched_keys = {
            self._normalize_roster_name(entry.get("name") or "") for _, entry in scored
        }

        best_group: dict | None = None
        best_rank: tuple[int, tuple[int, int, int, int]] | None = None

        for key in matched_keys:
            twins = [
                entry
                for entry in self.database
                if self._normalize_roster_name(entry.get("name") or "") == key
            ]
            merged = self._merge_entries(twins)
            group_score = max(
                score
                for score, entry in scored
                if self._normalize_roster_name(entry.get("name") or "") == key
            )
            rank = (group_score, self._entry_quality(merged))
            if best_rank is None or rank > best_rank:
                best_rank = rank
                best_group = merged

        logger.debug("Indigenous match for %r: %s", input_name, best_group.get("name") if best_group else None)
        return best_group
