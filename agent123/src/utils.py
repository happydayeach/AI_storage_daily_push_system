from datetime import datetime


def format_iso8601(value: datetime) -> str:
    """Return a datetime in ISO 8601 format with second precision."""
    return value.isoformat(timespec="seconds")
