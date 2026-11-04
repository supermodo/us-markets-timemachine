from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

SNAPSHOT_DAY_CUTOFF = time(10, 0)


def snapshot_date() -> date:
    """Return the date a run's snapshots belong to.

    A run before the cutoff counts as the previous ET day. The nightly cron starts
    hours late and can slip past midnight ET; under the calendar date that run would
    take the next evening's date, and since captures never overwrite, the next
    evening's snapshot would be refused and lost for good. It also makes a morning
    rerun harmless: it finds the night's files in place instead of claiming today's.
    """
    et = now_utc().astimezone(ET)
    return et.date() - timedelta(days=1) if et.time() < SNAPSHOT_DAY_CUTOFF else et.date()


def now_utc() -> datetime:
    return datetime.now(UTC)


def now_utc_iso() -> str:
    return now_utc().isoformat(timespec="seconds").replace("+00:00", "Z")


def date_path_parts(d: date) -> tuple[str, str]:
    return f"{d.year:04d}", d.isoformat()
