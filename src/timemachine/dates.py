from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def et_today() -> date:
    return datetime.now(ET).date()


def now_utc() -> datetime:
    return datetime.now(UTC)


def now_utc_iso() -> str:
    return now_utc().isoformat(timespec="seconds").replace("+00:00", "Z")


def date_path_parts(d: date) -> tuple[str, str]:
    return f"{d.year:04d}", d.isoformat()
