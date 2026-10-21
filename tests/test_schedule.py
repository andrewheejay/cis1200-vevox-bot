from datetime import date

from vevoxbot.models import Lecture
from vevoxbot.schedule import lecture_on, parse_rows

ROWS = [
    "Mon 9/7 | No Class: Labor Day | ",
    "Mon 10/19 | GUI Design: Events, Notifiers, and Controllers | lec21.pdf",
    "Wed 10/21 | Transition to Java | lec22.pdf",
    "Fri 10/23 | Interfaces, Static Methods | ",
    "Fri 11/6 | Midterm 2 | ",
]


def test_parse_rows():
    lectures = parse_rows(ROWS, 2026)
    assert Lecture(date(2026, 10, 21), "Transition to Java", 22) in lectures
    assert Lecture(date(2026, 10, 23), "Interfaces, Static Methods", None) in lectures


def test_no_class_rows():
    lectures = parse_rows(ROWS, 2026)
    assert lecture_on(date(2026, 11, 6), lectures) is None
    assert lecture_on(date(2026, 9, 7), lectures) is None


def test_lecture_on_missing_day():
    assert lecture_on(date(2026, 10, 20), parse_rows(ROWS, 2026)) is None


def test_lecture_on_class_day():
    assert lecture_on(date(2026, 10, 21), parse_rows(ROWS, 2026)).number == 22
