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
