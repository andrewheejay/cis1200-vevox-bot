from datetime import date, datetime, timedelta

from vevoxbot.config import ET
from vevoxbot.live import run_class, summary_markdown
from vevoxbot.models import Poll, Sheet
from vevoxbot.tracker import Tracker
from vevoxbot.vevox import PollUpdate

LEC22 = Sheet(22, date(2026, 10, 21), 40, "claude", [
    Poll(4, 6, 2, "opinion"), Poll(25, 3, 1, "graded"), Poll(26, 3, 2, "graded"),
    Poll(27, 3, 1, "graded"), Poll(39, 4, 4, "graded"), Poll(40, 4, 3, "graded"),
])


def at(h, m, s=0):
    return datetime(2026, 10, 21, h, m, s, tzinfo=ET)


class FakePage:
    """Replays (time, latest, buttons) events against a fake clock."""

    def __init__(self, events):
        self.events = sorted(events, key=lambda e: e[0])
        self.t = at(10, 12)
        self.latest = None
        self._buttons = []
        self.votes = []

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += timedelta(seconds=seconds)
        while self.events and self.events[0][0] <= self.t:
            _, latest, buttons = self.events.pop(0)
            if latest is not ...:
                self.latest = latest
            if buttons is not ...:
                self._buttons = buttons

    def buttons(self):
        return list(self._buttons)

    def vote(self, n):
        if n not in self._buttons:
            return False
        self.votes.append(n)
        return True


def opened(poll_id, n):
    return PollUpdate(poll_id, "open", n, None)


def results(poll_id, pcts):
    return PollUpdate(poll_id, "results", len(pcts), pcts)


def run(page, tracker=None, **kw):
    tracker = tracker or Tracker(LEC22, class_start=at(10, 15))
    return run_class(page, tracker, end=at(11, 20), now=page.now, sleep=page.sleep, log=lambda *_: None, **kw)


def test_votes_each_poll_once():
    page = FakePage([
        (at(10, 21), opened(135, 6), [1, 2, 3, 4, 5, 6]),
        (at(10, 22), results(135, [81, 17, 2, 0, 0, 0]), []),
        (at(10, 52), opened(136, 3), [1, 2, 3]),
        (at(10, 53), results(136, [90, 5, 5]), []),
    ])
    records = run(page)
    assert page.votes == [2, 1]
    assert [r.page for r in records] == [4, 25]
    assert all(r.voted for r in records)


def test_replayed_poll_not_revoted():
    page = FakePage([
        (at(10, 21), opened(135, 6), [1, 2, 3, 4, 5, 6]),
        (at(10, 22), results(135, [81, 17, 2, 0, 0, 0]), []),
        (at(10, 23), opened(135, 6), [1, 2, 3, 4, 5, 6]),  # reconnect replays the same poll
    ])
    run(page)
    assert page.votes == [2]


def test_correction_applied_on_results():
    tracker = Tracker(LEC22, class_start=at(10, 15))
    tracker.pointer = 2
    page = FakePage([
        (at(10, 52), opened(136, 3), [1, 2, 3]),
        (at(10, 53), results(136, [80, 10, 10]), []),
        (at(10, 54), opened(137, 3), [1, 2, 3]),
    ])
    records = run(page, tracker)
    assert records[0].moved_to == 1 and records[0].class_top == 1
    assert page.votes == [2, 2]  # after moving back to p25, the next poll is p26 (answer 2)


def test_waits_for_buttons_when_count_unknown():
    page = FakePage([
        (at(10, 52), PollUpdate(136, "open", None, None), []),
        (at(10, 52, 2), ..., [1, 2, 3]),
    ])
    records = run(page)
    assert records[0].n_buttons == 3 and page.votes == [1]


def test_dom_fallback_votes_once_per_appearance():
    page = FakePage([
        (at(10, 52), ..., [1, 2, 3]),
        (at(10, 55), ..., []),
        (at(10, 56), ..., [1, 2, 3]),
    ])
    records = run(page)
    assert len(page.votes) == 2 and records[0].poll_id is None


def test_dry_run_never_clicks():
    page = FakePage([(at(10, 21), opened(135, 6), [1, 2, 3, 4, 5, 6])])
    records = run(page, dry_run=True)
    assert page.votes == [] and len(records) == 1


def test_summary_lists_polls():
    page = FakePage([
        (at(10, 21), opened(135, 6), [1, 2, 3, 4, 5, 6]),
        (at(10, 52), opened(136, 3), [1, 2, 3]),
    ])
    md = summary_markdown(run(page), LEC22)
    assert "lec22" in md and "| 4 |" in md and "| 25 |" in md


def test_ws_announcement_after_dom_vote_not_double():
    page = FakePage([
        (at(10, 52), ..., [1, 2, 3]),
        (at(10, 52, 3), opened(136, 3), ...),  # websocket catches up after the page scan voted
    ])
    records = run(page)
    assert page.votes == [1] and len(records) == 1 and records[0].poll_id == 136


def test_ws_gets_priority_over_page_scan():
    page = FakePage([
        (at(10, 52), ..., [1, 2, 3]),
        (at(10, 52) + timedelta(milliseconds=500), opened(136, 3), ...),  # announcement arrives just after the buttons render
    ])
    records = run(page)
    assert page.votes == [1] and records[0].poll_id == 136


class FlakyPage(FakePage):
    """buttons() blows up for a while, like a page mid-reload."""

    def __init__(self, events, broken_until):
        super().__init__(events)
        self.broken_until = broken_until
        self.recovered = 0

    def buttons(self):
        if self.t < self.broken_until:
            raise RuntimeError("Execution context was destroyed")
        return super().buttons()

    def recover(self):
        self.recovered += 1


def test_exception_in_tick_does_not_stop_voting():
    page = FlakyPage([
        (at(10, 21), opened(135, 6), [1, 2, 3, 4, 5, 6]),
        (at(10, 52), opened(136, 3), [1, 2, 3]),
    ], broken_until=at(10, 25))
    records = run(page)
    assert page.votes[-1] == 1 and records[-1].voted  # the 10:52 poll still got its vote
    assert page.recovered >= 1


def test_keeps_retrying_while_poll_open():
    page = FakePage([
        (at(10, 52), PollUpdate(136, "open", 3, None), []),
        (at(10, 52, 6), ..., [1, 2, 3]),  # buttons only show up 6 s after the announcement
    ])
    records = run(page)
    assert page.votes == [1] and records[0].voted
