import json
import subprocess
from datetime import date
from pathlib import Path

import pytest

from vevoxbot import sheet as sheet_mod
from vevoxbot.models import Lecture, Poll
from vevoxbot.sheet import SheetError, build_sheet, claude_polls, validate_polls
from vevoxbot.slides import parse_polls

PAGES = [
    "Title\nLecture 22",
    "What is ans?\n1. true\n2. false\n3. NullPointerException\nAnswer: false\n",
]
LECTURE = Lecture(date(2026, 10, 21), "Transition to Java", 22)


def fake_run(stdout="", returncode=0, exc=None):
    calls = []

    def run(cmd, **kw):
        calls.append((cmd, kw))
        if exc:
            raise exc
        return subprocess.CompletedProcess(cmd, returncode, stdout, "")

    run.calls = calls
    return run


def envelope(result: str) -> str:
    return json.dumps({"type": "result", "is_error": False, "result": result})


def test_claude_polls_parses_envelope():
    run = fake_run(envelope('Here:\n[{"page":2,"choices":3,"answer":2,"kind":"graded","q":"x"}]'))
    assert claude_polls(PAGES, run=run) == [Poll(2, 3, 2, "graded", "x")]
    cmd, kw = run.calls[0]
    assert cmd[:2] == ["claude", "-p"] and "--bare" not in cmd
    assert "=== PAGE 2 ===" in kw["input"]


def test_validate_rejects_out_of_range():
    with pytest.raises(SheetError):
        validate_polls([{"page": 2, "choices": 3, "answer": 5, "kind": "graded"}], n_pages=2)
    with pytest.raises(SheetError):
        validate_polls([{"page": 9, "choices": 3, "answer": 1, "kind": "graded"}], n_pages=2)
    with pytest.raises(SheetError):
        validate_polls([{"page": 2, "choices": 3, "answer": 1, "kind": "maybe"}], n_pages=2)


@pytest.mark.parametrize("run", [
    fake_run(envelope("I could not find any polls, sorry.")),
    fake_run("", returncode=1),
    fake_run(exc=subprocess.TimeoutExpired("claude", 240)),
    fake_run(exc=FileNotFoundError("claude")),
    fake_run(envelope('[{"page": 2, "choices": 3, "answer": 7, "kind": "graded"}]')),
])
def test_build_sheet_falls_back(monkeypatch, run):
    monkeypatch.setattr(sheet_mod, "pdf_pages", lambda pdf: PAGES)
    s = build_sheet(LECTURE, Path("lec22.pdf"), run=run)
    assert s.source == "parser"
    assert s.polls == parse_polls(PAGES)
    assert (s.lecture, s.day, s.pages) == (22, date(2026, 10, 21), 2)


def test_build_sheet_uses_claude(monkeypatch):
    monkeypatch.setattr(sheet_mod, "pdf_pages", lambda pdf: PAGES)
    run = fake_run(envelope('[{"page":2,"choices":3,"answer":2,"kind":"graded","q":"x"}]'))
    s = build_sheet(LECTURE, Path("lec22.pdf"), run=run)
    assert s.source == "claude" and s.polls == [Poll(2, 3, 2, "graded", "x")]


def test_empty_claude_result_uses_parser(monkeypatch):
    monkeypatch.setattr(sheet_mod, "pdf_pages", lambda pdf: PAGES)
    s = build_sheet(LECTURE, Path("lec22.pdf"), run=fake_run(envelope("[]")))
    assert s.source == "parser" and len(s.polls) == 1
