"""Whether the bot should act right now, and on which days it has been switched off."""
import os
import subprocess
from datetime import date, datetime, time, timedelta

from .config import CLASS_DAYS, ET, REPO_DIR

CLASS_WINDOW = (time(9, 30), time(11, 0))  # a late cron firing still gets to answer the rest of class
EVENING_DAYS = {6, 1, 3}  # Sun, Tue, Thu: the evening before each class
EVENING_WINDOW = (time(20, 30), time(22, 30))


def should_run_class(now_utc: datetime) -> bool:
    et = now_utc.astimezone(ET)
    return et.weekday() in CLASS_DAYS and CLASS_WINDOW[0] <= et.time() < CLASS_WINDOW[1]


def should_run_evening(now_utc: datetime) -> bool:
    et = now_utc.astimezone(ET)
    return et.weekday() in EVENING_DAYS and EVENING_WINDOW[0] <= et.time() < EVENING_WINDOW[1]


def next_class_day(today: date) -> date:
    d = today + timedelta(days=1)
    while d.weekday() not in CLASS_DAYS:
        d += timedelta(days=1)
    return d


def _parse_dates(text: str) -> set[date]:
    return {date.fromisoformat(part.strip()) for part in text.split(",") if part.strip()}


def _gh_variable() -> str:
    out = subprocess.run(["gh", "variable", "get", "SKIP_DATES"], cwd=REPO_DIR, capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else ""


def skip_dates() -> set[date]:
    """Class days Andrew switched the bot off for (repo variable SKIP_DATES, or the env var in Actions)."""
    if "SKIP_DATES" in os.environ:
        return _parse_dates(os.environ["SKIP_DATES"])
    try:
        return _parse_dates(_gh_variable())
    except OSError:
        return set()


def set_skip(day: date, off: bool) -> set[date]:
    days = _parse_dates(_gh_variable())
    days = days | {day} if off else days - {day}
    body = ",".join(sorted(d.isoformat() for d in days if d >= date.today() - timedelta(days=7)))
    subprocess.run(["gh", "variable", "set", "SKIP_DATES", "--body", body or " "], cwd=REPO_DIR, check=True)
    return days
