from datetime import date, datetime

import pytest

from vevoxbot.config import ET
from vevoxbot.models import Poll, Sheet
from vevoxbot.tracker import Pick, Tracker

LEC22 = Sheet(22, date(2026, 10, 21), 40, "manual", [
    Poll(4, 6, 2, "opinion"),
    Poll(25, 3, 1, "graded"),
    Poll(26, 3, 2, "graded"),
    Poll(27, 3, 1, "graded"),
    Poll(39, 4, 4, "graded"),
    Poll(40, 4, 3, "graded"),
])


def at(h, m):
    return datetime(2026, 10, 21, h, m, tzinfo=ET)


@pytest.fixture
def tracker():
    return Tracker(LEC22, class_start=at(10, 15))


def test_expected_times(tracker):
    assert tracker.expected(0) == at(10, 21)
    assert tracker.expected(5) == at(11, 15)


def test_in_order(tracker):
    polls = [(at(10, 21), 6), (at(10, 52), 3), (at(10, 54), 3), (at(10, 55), 3), (at(11, 12), 4), (at(11, 14), 4)]
    assert [tracker.choose(n, t).answer for t, n in polls] == [2, 1, 2, 1, 4, 3]


def test_skips_by_button_count(tracker):
    pick = tracker.choose(3, at(10, 40))  # p4 still live (19 min overdue), p25 due 10:52:30
    assert (pick.index, pick.answer) == (1, 1)
    assert tracker.pointer == 2


def test_skip_rule(tracker):
    # p4 (due 10:21) is 24 min overdue, but a 6-button poll is still recognized as that late HW poll
    pick = tracker.choose(6, at(10, 45))
    assert (pick.index, pick.answer) == (0, 2)


def test_skipped_question_passed_over(tracker):
    pick = tracker.choose(3, at(10, 45))  # p4 skipped, p25 due 10:52:30
    assert (pick.index, pick.answer) == (1, 1)


def test_exhausted_sheet_votes_blind(tracker):
    tracker.pointer = 6
    assert tracker.choose(4, at(11, 15)) == Pick(None, 1, "no match")


def test_mismatched_count_votes_blind_and_keeps_place(tracker):
    tracker.pointer = 4
    pick = tracker.choose(3, at(11, 12))  # only 4-option questions left
    assert pick == Pick(None, 1, "no match nearby") and tracker.pointer == 4


def test_correction_moves_back(tracker):
    tracker.pointer = 2
    pick = tracker.choose(3, at(10, 52))
    assert (pick.index, pick.answer) == (2, 2)  # bot thought it was p26
    moved = tracker.correct(pick, 3, [80.0, 10.0, 10.0], opened_at=at(10, 52))
    assert moved == 1 and tracker.pointer == 2
    assert tracker.choose(3, at(10, 54)).answer == 2  # p26 is next after all


def test_correction_ignores_close_vote(tracker):
    tracker.pointer = 2
    pick = tracker.choose(3, at(10, 52))
    assert tracker.correct(pick, 3, [45.0, 40.0, 15.0], opened_at=at(10, 52)) is None
    assert tracker.pointer == 3


def test_correction_noop_when_class_agrees(tracker):
    pick = tracker.choose(3, at(10, 52))
    assert tracker.correct(pick, 3, [90.0, 5.0, 5.0], opened_at=at(10, 52)) is None


def test_no_correction_for_opinion(tracker):
    pick = tracker.choose(6, at(10, 21))
    assert tracker.correct(pick, 6, [81.0, 17.0, 2.0, 0, 0, 0], opened_at=at(10, 21)) is None


def test_far_match_not_taken(tracker):
    # an unplanned 4-button poll early in class must not jump to p39 (due 11:13)
    pick = tracker.choose(4, at(10, 16))
    assert pick == Pick(None, 1, "no match nearby") and tracker.pointer == 0
    assert tracker.choose(6, at(10, 21)).answer == 2  # the HW poll still lines up
