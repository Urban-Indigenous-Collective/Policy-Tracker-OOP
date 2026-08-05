def split_sponsors(sponsors_string: str) -> list[str]:
    sponsors_list = []
    bracket_level = 0
    current_sponsor = ""
    for char in sponsors_string:
        if char == "," and bracket_level == 0:
            sponsors_list.append(current_sponsor.strip())
            current_sponsor = ""
        else:
            if char == "[":
                bracket_level += 1
            elif char == "]" and bracket_level > 0:
                bracket_level -= 1
            current_sponsor += char
    if current_sponsor:
        sponsors_list.append(current_sponsor.strip())
    return sponsors_list


def _use_offices_held_as_role(offices_held: str, role: str) -> bool:
    """Use roster offices_held only when LegiScan gave no role, and it is a title not career history."""
    if not offices_held or offices_held == "N/A":
        return False
    if role:
        return False
    # Manual MMIP coordinator roster lines — the title is the whole point.
    if "MMIP Coordinator" in offices_held:
        return True
    # Wikipedia list pages store full career timelines; skip those for sponsor display.
    lowered = offices_held.lower()
    career_markers = (
        "present",
        "–",
        "-",
        "19",
        "20",
        "speaker of",
        "state representative",
        "state senator",
    )
    if any(marker in lowered for marker in career_markers):
        return False
    return True


def process_sponsors(sponsors_string: str, indigenous_db) -> tuple[str, str]:
    sponsors_list = split_sponsors(sponsors_string)
    processed_sponsors = []
    processed_indigenous_sponsors = []

    for sponsor in sponsors_list:
        if " - " in sponsor:
            name, details = sponsor.split(" - ", 1)
            name = name.strip()
            details = details.strip()
        else:
            name = sponsor.strip()
            details = ""

        if "(" in details and ")" in details:
            role = details.split("(")[0].strip()
            additional_details = details[details.find("(") + 1 : details.find(")")].strip()
        else:
            role = details
            additional_details = ""

        indigenous_data = indigenous_db.get_indigenous_sponsor_entry(name)
        ethnicity = indigenous_data.get("ethnicity") if indigenous_data else None
        offices_held = indigenous_data.get("offices_held") if indigenous_data else None

        if indigenous_data:
            display_role = role
            if ethnicity and ethnicity != "N/A":
                if _use_offices_held_as_role(offices_held or "", role):
                    display_role = offices_held
                name_with_ethnicity = f"{name} ({ethnicity})"
            else:
                name_with_ethnicity = name
            processed_indigenous_sponsors.append(
                _format_sponsor_line(name_with_ethnicity, display_role, additional_details)
            )
        else:
            name_with_ethnicity = name

        processed_sponsors.append(_format_sponsor_line(name_with_ethnicity, role, additional_details))

    return ", ".join(processed_sponsors), ", ".join(processed_indigenous_sponsors)


def _format_sponsor_line(name: str, role: str, additional_details: str) -> str:
    if role and additional_details:
        return f"{name} - {role} ({additional_details})"
    if role:
        return f"{name} - {role}"
    if additional_details:
        return f"{name} ({additional_details})"
    return name
