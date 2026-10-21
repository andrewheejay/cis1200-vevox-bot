import pytest

from vevoxbot import cli

ROWS = [
    "Wed 10/21 | Transition to Java | lec22.pdf",
    "Fri 10/23 | Interfaces, Static Methods | ",
    "Fri 11/6 | Midterm 2 | ",
]


@pytest.fixture
def no_browser(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("Vevox must not be opened")

    monkeypatch.setattr(cli, "VevoxPage", boom)
    monkeypatch.setattr(cli, "fetch_rows", lambda: ROWS)


def test_run_no_class(no_browser, monkeypatch, capsys):
    monkeypatch.setenv("SKIP_DATES", "")
    assert cli.main(["run", "--date", "2026-11-06"]) == 0
    assert "no class" in capsys.readouterr().out.lower()


def test_run_skipped_date(no_browser, monkeypatch, capsys):
    monkeypatch.setenv("SKIP_DATES", "2026-10-23")
    assert cli.main(["run", "--date", "2026-10-23"]) == 0
    assert "switched off" in capsys.readouterr().out.lower()


def test_sheet_slides_not_posted(no_browser, capsys):
    assert cli.main(["sheet", "--date", "2026-10-23"]) == 3
    assert "not posted" in capsys.readouterr().out.lower()


class FakeVevox:
    opened = 0

    def __init__(self, *a, **kw):
        self.latest = None

    def __enter__(self):
        FakeVevox.opened += 1
        return self

    def __exit__(self, *exc):
        return False

    def signed_in(self):
        return True

    def wait(self, s):
        pass

    def buttons(self):
        return []

    def vote(self, n):
        return False

    def voted(self):
        return False


@pytest.fixture
def fake_vevox(monkeypatch, tmp_path):
    FakeVevox.opened = 0
    monkeypatch.setattr(cli, "VevoxPage", FakeVevox)
    monkeypatch.setattr(cli, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(cli, "SHEETS", tmp_path / "sheets")
    monkeypatch.setenv("SKIP_DATES", "")
    monkeypatch.setenv("VEVOXBOT_MINUTES", "0.005")


def test_run_missing_row_still_runs(fake_vevox, monkeypatch):
    monkeypatch.setattr(cli, "fetch_rows", lambda: [])  # schedule page rendered empty
    cli.main(["run", "--date", "2026-10-23", "--no-wait"])
    assert FakeVevox.opened == 1


def test_run_schedule_crash_still_runs(fake_vevox, monkeypatch):
    def broken():
        raise TimeoutError("schedule page timed out")

    monkeypatch.setattr(cli, "fetch_rows", broken)
    cli.main(["run", "--date", "2026-10-23", "--no-wait"])
    assert FakeVevox.opened == 1


def test_run_sheet_crash_still_runs(fake_vevox, monkeypatch):
    monkeypatch.setattr(cli, "fetch_rows", lambda: ROWS)

    def broken(*a, **kw):
        raise OSError("download failed")

    monkeypatch.setattr(cli, "download_slides", broken)
    cli.main(["run", "--date", "2026-10-21", "--no-wait"])
    assert FakeVevox.opened == 1


def test_run_without_any_poll_updates_is_flagged(fake_vevox, monkeypatch, capsys):
    monkeypatch.setattr(cli, "fetch_rows", lambda: ROWS)
    monkeypatch.setattr(cli, "load_or_build", lambda day, lec, use_claude: cli.Sheet(22, lec.day, 40, "manual", []))
    assert cli.main(["run", "--date", "2026-10-21", "--no-wait"]) == 1
    assert "never received" in capsys.readouterr().out.lower()


def test_run_after_class_is_over_does_nothing(no_browser, monkeypatch, capsys):
    """A Mac that wakes up at 1 pm shouldn't open Vevox for a class that ended at 11:15."""
    monkeypatch.setenv("SKIP_DATES", "")
    monkeypatch.delenv("VEVOXBOT_MINUTES", raising=False)
    assert cli.main(["run", "--date", "2026-10-19"]) == 0
    assert "over" in capsys.readouterr().out
