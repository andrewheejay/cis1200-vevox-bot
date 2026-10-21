"""Build a lecture's answer sheet: Claude reads the slides, the regex parser is the fallback."""
import json
import subprocess
from pathlib import Path

from .models import Lecture, Poll, Sheet
from .slides import parse_polls, pdf_pages

PROMPT = """You are given the text of one CIS 1200 lecture's slides, page by page (=== PAGE k === markers).
Find every slide that is an in-class poll the professor runs in Vevox. A poll is a question followed by
numbered options (1., 2., ...), or a "True or False:" question (2 options: True = 1, False = 2).
Students only see buttons numbered 1..N, so report the option NUMBER.

For each poll return {"page": k, "choices": N, "answer": number, "kind": "graded" or "opinion", "q": short question}.
- answer: use the "Answer:" text on the slide when present ("Answer: 3" may name option 3 or option text "3";
  prefer the option whose text matches). If no answer is printed, solve the question yourself.
- Opinion/survey polls (e.g. "How far along in HW05 are you?") have kind "opinion" and answer 2.
- Ordinary numbered lists that are not questions are not polls.
Output ONLY the JSON array, in page order, nothing else."""


class SheetError(Exception):
    pass


def validate_polls(raw: list[dict], n_pages: int) -> list[Poll]:
    polls = []
    try:
        for item in raw:
            p = Poll(int(item["page"]), int(item["choices"]), int(item["answer"]), item["kind"], str(item.get("q", "")))
            if not (1 <= p.page <= n_pages and 2 <= p.choices <= 9 and 1 <= p.answer <= p.choices):
                raise SheetError(f"out of range: {item}")
            if p.kind not in ("graded", "opinion"):
                raise SheetError(f"bad kind: {item}")
            polls.append(p)
    except (KeyError, TypeError, ValueError) as e:
        raise SheetError(f"malformed poll: {e}") from e
    return sorted(polls, key=lambda p: p.page)


def claude_polls(pages: list[str], run=subprocess.run) -> list[Poll]:
    text = "\n".join(f"=== PAGE {k} ===\n{t}" for k, t in enumerate(pages, 1))
    out = run(["claude", "-p", PROMPT, "--output-format", "json"],
              input=text, capture_output=True, text=True, timeout=240)
    if out.returncode != 0:
        raise SheetError(f"claude exited {out.returncode}")
    try:
        env = json.loads(out.stdout)
        result = env["result"]
        raw = json.loads(result[result.index("["): result.rindex("]") + 1])
    except (ValueError, KeyError, TypeError) as e:
        raise SheetError(f"no JSON array in claude output: {e}") from e
    if env.get("is_error") or not isinstance(raw, list):
        raise SheetError("claude reported an error")
    return validate_polls(raw, len(pages))


def build_sheet(lecture: Lecture, pdf: Path, run=subprocess.run, use_claude: bool = True) -> Sheet:
    pages = pdf_pages(pdf)
    parsed = parse_polls(pages)
    polls, source = parsed, "parser"
    if use_claude:
        try:
            from_claude = claude_polls(pages, run=run)
            if from_claude or not parsed:
                polls, source = from_claude, "claude"
        except Exception:  # any Claude trouble (missing CLI, limits, odd output) -> the parser's sheet
            pass
    return Sheet(lecture=lecture.number, day=lecture.day, pages=len(pages), source=source, polls=polls)
