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
    # Vevox shows the same generic buttons (here 1-6) for every poll
    times = [at(10, 21), at(10, 52), at(10, 54), at(10, 55), at(11, 12), at(11, 14)]
    assert [tracker.choose(6, t).answer for t in times] == [2, 1, 2, 1, 4, 3]


def test_button_count_is_ignored(tracker):
    # a 5-button poll is still the next question in order, even though p4 has 6 options
    assert (tracker.choose(5, at(10, 21)).index, tracker.pointer) == (0, 1)
    assert tracker.choose(5, at(10, 52)).index == 1


def test_skip_rule(tracker):
    pick = tracker.choose(6, at(10, 45))  # p4 was due 10:21: 24 min overdue, treated as skipped
    assert (pick.index, pick.answer) == (1, 1)


def test_exhausted_sheet_votes_blind(tracker):
    tracker.pointer = 6
    assert tracker.choose(4, at(11, 15)) == Pick(None, 1, "no match")


def test_answer_clamped_to_buttons(tracker):
    tracker.pointer = 4
    pick = tracker.choose(3, at(11, 12))  # p39's answer 4 isn't on screen
    assert (pick.index, pick.answer) == (4, 1)


def test_correction_moves_back(tracker):
    tracker.pointer = 2
    pick = tracker.choose(3, at(10, 52))
    assert (pick.index, pick.answer) == (2, 2)  # bot thought it was p26
    moved = tracker.correct(pick, 5, [80.0, 10.0, 10.0, 0, 0], opened_at=at(10, 52))
    assert moved == 1 and tracker.pointer == 2
    assert tracker.choose(5, at(10, 54)).answer == 2  # p26 is next after all


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

