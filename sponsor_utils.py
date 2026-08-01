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

        if ethnicity and ethnicity != "N/A":
            if offices_held:
                role = offices_held
            name_with_ethnicity = f"{name} ({ethnicity})"
            processed_indigenous_sponsors.append(
                _format_sponsor_line(name_with_ethnicity, role, additional_details)
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
