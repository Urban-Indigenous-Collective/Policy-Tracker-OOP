"""Tests for Airtable field coercion (Main v3 alignment)."""

from datetime import date

from airtable_coercion import coerce_bill_fields, coerce_categories


def test_somewhat_maps_to_tbd_for_mechanisms():
    data = coerce_bill_fields({"Mechanisms for Evaluation?": "Somewhat"})
    assert data["Mechanisms for Evaluation?"] == "TBD or TCRP Specific"


def test_somewhat_kept_for_survivor_input():
    data = coerce_bill_fields({"Level of Survivor / Relative Input?": "Somewhat"})
    assert data["Level of Survivor / Relative Input?"] == "Somewhat"


def test_active_status_maps_to_pending():
    data = coerce_bill_fields({"Status": "Active", "Name": "Test Bill"})
    assert data["Status"] == "Pending"


def test_legacy_field_rename():
    data = coerce_bill_fields(
        {
            "Title": "MMIP Act",
            "Bill Overview": "https://example.com/bill/1",
            "Sponsors": "Sen. Example",
            "Gender Inclusive Explanation": "Uses inclusive terms",
        }
    )
    assert data["Name"] == "MMIP Act"
    assert data["Bill Overview (Link)"] == "https://example.com/bill/1"
    assert data["Sponsors of the Legislation"] == "Sen. Example"
    assert data["Gender Inclusive Language"] == "Uses inclusive terms"


def test_categories_from_comma_string():
    assert coerce_categories("Taskforce, Data Collection") == ["Taskforce", "Data Collection"]


def test_categories_from_python_list_repr():
    raw = "['Day of Recognition', 'US Law Enforcement']"
    assert coerce_categories(raw) == ["Day of Recognition", "US Law Enforcement"]


def test_categories_from_json_array_string():
    raw = '["US Law Enforcement", "Tribal Law Enforcement", "Data Collection"]'
    assert coerce_categories(raw) == [
        "US Law Enforcement",
        "Tribal Law Enforcement",
        "Data Collection",
    ]


def test_categories_comma_split_strips_brackets_and_quotes():
    raw = "['Taskforce, 'Day of Recognition', 'US Law Enforcement']"
    assert coerce_categories(raw) == [
        "Taskforce",
        "Day of Recognition",
        "US Law Enforcement",
    ]


def test_categories_from_mangled_airtable_multiselect():
    mangled = [
        "['Taskforce",
        "'Day of Recognition'",
        "'US Law Enforcement'",
        "'MMIP Relatives']",
    ]
    assert coerce_categories(mangled) == [
        "Taskforce",
        "Day of Recognition",
        "US Law Enforcement",
        "MMIP Relatives",
    ]


def test_unknown_progression_falls_back():
    data = coerce_bill_fields({"Progression": "N/A"})
    assert data["Progression"] == "Progression"


def test_empty_last_update_defaults_to_today():
    data = coerce_bill_fields({"Last Update": "", "Name": "Test"})
    assert data["Last Update"] == date.today().isoformat()


def test_empty_optional_url_omitted():
    data = coerce_bill_fields(
        {
            "Bill Overview (Link)": "https://example.gov/bill",
            "Optional Link": "",
            "Bill Text": "javascript:void(0)",
        }
    )
    assert data["Bill Overview (Link)"] == "https://example.gov/bill"
    assert "Optional Link" not in data
    assert "Bill Text" not in data
