from datetime import date, datetime, timezone

from vevoxbot.gate import next_class_day, should_run_class, should_run_evening, skip_dates


def utc(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


def test_gate_dst():
    # EDT (before Nov 1): the 13:50 UTC firing is 9:50 ET
    assert should_run_class(utc(2026, 10, 21, 13, 50))
    # EST (after Nov 1): the 14:50 UTC firing is 9:50 ET; 13:50 UTC is 8:50 ET, too early
    assert should_run_class(utc(2026, 11, 4, 14, 50))
    assert not should_run_class(utc(2026, 11, 4, 13, 50))
    # In EDT the 14:50 UTC firing (10:50 ET) still passes: it only runs if the first run isn't (retry)


def test_gate_rejects_wrong_days_and_late_starts():
    assert not should_run_class(utc(2026, 10, 20, 13, 50))  # Tuesday
    assert not should_run_class(utc(2026, 10, 21, 15, 30))  # 11:30 ET, class is over


def test_gate_evening():
    assert should_run_evening(utc(2026, 10, 21, 1, 0))  # Tue 21:00 EDT
    assert should_run_evening(utc(2026, 11, 4, 2, 0))  # Tue 21:00 EST
    assert not should_run_evening(utc(2026, 11, 4, 1, 0))  # Tue 20:00 EST, too early
    assert not should_run_evening(utc(2026, 11, 5, 2, 0))  # Wed 21:00 EST, no class Thursday


def test_next_class_day():
    assert next_class_day(date(2026, 10, 20)) == date(2026, 10, 21)  # Tue -> Wed
    assert next_class_day(date(2026, 10, 23)) == date(2026, 10, 26)  # Fri -> Mon
    assert next_class_day(date(2026, 10, 21)) == date(2026, 10, 23)  # Wed -> Fri


def test_skip_dates_env(monkeypatch):
    monkeypatch.setenv("SKIP_DATES", "2026-10-23, 2026-11-02")
    assert skip_dates() == {date(2026, 10, 23), date(2026, 11, 2)}
    monkeypatch.setenv("SKIP_DATES", "")
    assert skip_dates() == set()
