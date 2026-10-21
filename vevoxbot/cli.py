"""bot login | check | sheet | run | off | on"""
import argparse
import os
import subprocess
import sys
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path

from .config import CLASS_DAYS, CLASS_START, ET, REPO_DIR, RUN_END, RUN_START, SESSION_URL, state_path
from .gate import next_class_day, set_skip, skip_dates
from .live import run_class, summary_markdown
from .models import Lecture, Sheet
from .schedule import fetch_rows, find_row, lecture_on, parse_rows
from .sheet import build_sheet
from .slides import download_slides
from .tracker import Tracker
from .vevox import VevoxPage

SHEETS = REPO_DIR / "sheets"
RUNS = REPO_DIR / "runs"


def log(msg: str) -> None:
    print(f"{datetime.now(ET):%H:%M:%S} {msg}", flush=True)


def today() -> date:
    return datetime.now(ET).date()


def at(day: date, t: time) -> datetime:
    return datetime.combine(day, t, tzinfo=ET)


def lecture_for(day: date):
    return lecture_on(day, parse_rows(fetch_rows(), day.year))


def cmd_login(args) -> int:
    from playwright.sync_api import sync_playwright

    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(SESSION_URL)
        print("Sign in with PennKey + Duo in the browser window. Close the window once the CIS 1200 page shows.")
        while not page.is_closed():
            if page.url.startswith("https://vevox.app"):
                try:
                    ctx.storage_state(path=str(path))
                    os.chmod(path, 0o600)
                except Exception:
                    pass
            try:
                page.wait_for_timeout(2000)
            except Exception:
                break
        browser.close()
    print(f"Saved login to {path}")
    if args.upload:
        with open(path) as f:
            subprocess.run(["gh", "secret", "set", "VEVOX_STATE"], stdin=f, cwd=REPO_DIR, check=True)
        print("Uploaded to the VEVOX_STATE secret.")
    return 0


def cmd_check(args) -> int:
    if not state_path().exists():
        print(f"No saved login at {state_path()}. Run: bot login")
        return 2
    with VevoxPage(state_path(), log=log) as v:
        if v.signed_in():
            print("Vevox login OK.")
            return 0
    print("LOGIN EXPIRED: Vevox sent the bot to PennKey. Run: bot login --upload")
    return 2


def cmd_sheet(args) -> int:
    day = args.date or next_class_day(today())
    lec = lecture_for(day)
    if lec is None:
        print(f"{day}: no class.")
        return 0
    if lec.number is None:
        print(f"{day}: slides for '{lec.title}' are not posted yet.")
        return 3
    with tempfile.TemporaryDirectory() as tmp:
        sheet = build_sheet(lec, download_slides(lec.number, Path(tmp)))
    sheet.save(SHEETS / f"{day}.json")
    print(f"{day} lec{lec.number:02d} '{lec.title}': {len(sheet.polls)} polls (by {sheet.source})")
    for p in sheet.polls:
        print(f"  slide {p.page:>3}  {p.choices} choices  answer {p.answer}  {p.kind:<7}  {p.q[:60]}")
    return 0


def load_or_build(day: date, lec: Lecture, use_claude: bool) -> Sheet:
    path = SHEETS / f"{day}.json"
    if path.exists():
        return Sheet.load(path)
    if lec.number is not None:
        with tempfile.TemporaryDirectory() as tmp:
            sheet = build_sheet(lec, download_slides(lec.number, Path(tmp)), use_claude=use_claude)
        sheet.save(path)
        return sheet
    log("No slides posted: every poll gets the blind answer.")
    return Sheet(lecture=0, day=day, pages=1, source="none", polls=[])


def class_lecture(day: date) -> Lecture | None:
    """The class to attend on `day`, or None if the schedule says there is none. A schedule page that
    fails to load or lacks the row is not proof of "no class", so on a class weekday we attend anyway."""
    try:
        row = find_row(day, parse_rows(fetch_rows(), day.year))
    except Exception as e:
        log(f"schedule unavailable ({e!r}); attending anyway")
        row = None
    if row is not None:
        return row if row.is_class else None
    if day.weekday() not in CLASS_DAYS:
        return None
    log("today isn't on the schedule page; attending anyway")
    return Lecture(day, "not on schedule", None)


def write_summary(day: date, summary: str) -> None:
    RUNS.mkdir(exist_ok=True)
    (RUNS / f"{day}.md").write_text(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(summary)
    print(summary)


def cmd_run(args) -> int:
    day = args.date or today()
    if day in skip_dates():
        print(f"{day}: bot switched off for this class.")
        return 0
    lec = class_lecture(day)
    if lec is None:
        print(f"{day}: no class.")
        return 0
    try:  # never call Claude once class has started: it can take minutes
        sheet = load_or_build(day, lec, use_claude=datetime.now(ET) < at(day, RUN_START))
    except Exception as e:
        log(f"couldn't build the answer sheet ({e!r}); every poll gets the blind answer")
        sheet = Sheet(lecture=0, day=day, pages=1, source="none", polls=[])
    log(f"lec{sheet.lecture:02d}: {len(sheet.polls)} polls on the sheet (by {sheet.source})")
    minutes = os.environ.get("VEVOXBOT_MINUTES")  # for test runs: stop after N minutes instead of at 11:20
    end = datetime.now(ET) + timedelta(minutes=float(minutes)) if minutes else at(day, RUN_END)
    RUNS.mkdir(exist_ok=True)
    records, code = [], 0
    try:
        with VevoxPage(state_path(), log=log, record=RUNS / f"{day}-frames.jsonl") as v:
            if not v.signed_in():
                log("LOGIN EXPIRED: Vevox sent the bot to PennKey. Run: bot login --upload")
                return 2
            log("signed in to Vevox")
            while not args.no_wait and datetime.now(ET) < at(day, RUN_START):
                v.wait(min(30, (at(day, RUN_START) - datetime.now(ET)).total_seconds()))
            tracker = Tracker(sheet, class_start=at(day, CLASS_START))
            records = run_class(v, tracker, end, now=lambda: datetime.now(ET), sleep=v.wait, log=log,
                                dry_run=args.dry_run)
            if v.latest is None:
                log("WARNING: never received a poll update from Vevox during the run")
                code = 1
    except Exception as e:
        log(f"run crashed: {e!r}")
        code = 2
    finally:
        write_summary(day, summary_markdown(records, sheet))
    if not args.dry_run and any(not r.voted for r in records):
        code = code or 1
    return code


def cmd_off(args) -> int:
    day = args.date or next_class_day(today())
    set_skip(day, off=True)
    print(f"Bot switched OFF for {day}. Undo with: bot on {day}")
    return 0


def cmd_on(args) -> int:
    set_skip(args.date, off=False)
    print(f"Bot switched back ON for {args.date}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bot", description="CIS 1200 Vevox attendance bot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("login", help="sign in once with PennKey + Duo and save the session")
    p.add_argument("--upload", action="store_true", help="also store it as the VEVOX_STATE GitHub secret")
    p.set_defaults(fn=cmd_login)
    sub.add_parser("check", help="is the saved Vevox login still valid?").set_defaults(fn=cmd_check)
    p = sub.add_parser("sheet", help="build the answer sheet (default: next class day)")
    p.add_argument("--date", type=date.fromisoformat)
    p.set_defaults(fn=cmd_sheet)
    p = sub.add_parser("run", help="answer polls for a class (default: today)")
    p.add_argument("--date", type=date.fromisoformat)
    p.add_argument("--dry-run", action="store_true", help="watch and log, never click")
    p.add_argument("--no-wait", action="store_true", help="start answering immediately")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("off", help="switch the bot off for a class (default: next class day)")
    p.add_argument("date", nargs="?", type=date.fromisoformat)
    p.set_defaults(fn=cmd_off)
    p = sub.add_parser("on", help="switch the bot back on for a class")
    p.add_argument("date", type=date.fromisoformat)
    p.set_defaults(fn=cmd_on)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
