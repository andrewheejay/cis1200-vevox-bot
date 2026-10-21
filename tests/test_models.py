from datetime import date

from vevoxbot.models import Lecture, Poll, Sheet


def test_sheet_roundtrip():
    sheet = Sheet(
        lecture=22,
        day=date(2026, 10, 21),
        pages=40,
        source="manual",
        polls=[
            Poll(page=4, choices=6, answer=2, kind="opinion", q="How far along in HW05 are you?"),
            Poll(page=25, choices=3, answer=1, kind="graded"),
        ],
    )
    back = Sheet.from_json(sheet.to_json())
    assert back == sheet
    assert isinstance(back.day, date)


def test_lecture_is_class():
    assert not Lecture(date(2026, 10, 2), "No Class: Fall Break", None).is_class
    assert not Lecture(date(2026, 11, 6), "Midterm 2", None).is_class
    assert not Lecture(date(2026, 12, 10), "Final Exam", None).is_class
    assert Lecture(date(2026, 10, 21), "Transition to Java", 22).is_class
