"""
Name normalization map.

Keys   : raw name exactly as it appears in the CSV (case-insensitive match)
Values : canonical display name to use everywhere

Add entries whenever a person's name differs between the timesheet and
the Order Details export (e.g. typos, nick-names, role-based suffixes).
"""

# raw name (lowercase) → canonical name
NAME_MAP: dict[str, str] = {
    # Timesheet name      : canonical
    "ali arevalo":  "Ali Arevalo",
    # Order Details name  : same canonical
    "ali arevalov": "Ali Arevalo",

    # Add more as needed:
    # "old name":  "Correct Name",
}


def normalize(name: str) -> str:
    """Return the canonical name for a raw CSV name, or the name itself."""
    return NAME_MAP.get(name.strip().lower(), name.strip())
