"""Which lecture (and slide deck) falls on a given day, from the course schedule page."""
import re
from datetime import date

from .config import SCHEDULE_URL
from .models import Lecture

ROW = re.compile(r"^\w{3} (\d{1,2})/(\d{1,2})\s*\|\s*(.*?)\s*\|\s*(?:lec(\d+)\.pdf)?\s*$")


def parse_rows(rows: list[str], year: int) -> list[Lecture]:
    """Rows look like 'Wed 10/21 | Transition to Java | lec22.pdf' (slides cell may be empty)."""
    lectures = []
    for row in rows:
        m = ROW.match(row.strip())
        if not m:
            continue
        month, day, title, num = m.groups()
        lectures.append(Lecture(date(year, int(month), int(day)), title, int(num) if num else None))
    return lectures


def lecture_on(day: date, lectures: list[Lecture]) -> Lecture | None:
    for lec in lectures:
        if lec.day == day:
            return lec if lec.is_class else None
    return None


ROWS_JS = """() => [...document.querySelectorAll('tr:not(.homework)')]
  .map(r => [...r.cells].slice(0, 3).map(td => td.innerText.trim().replace(/\\s+/g, ' ')))
  .filter(c => c.length >= 2 && /^(Mon|Tue|Wed|Thu|Fri) \\d/.test(c[0]))
  .map(c => c[0] + ' | ' + c[1] + ' | ' + (c[2] || ''))"""


def fetch_rows() -> list[str]:
    """Render the schedule (it is built by JavaScript) and return its lecture rows."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(SCHEDULE_URL, wait_until="networkidle")
        rows = page.evaluate(ROWS_JS)
        browser.close()
    return rows
