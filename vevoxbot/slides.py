"""Deterministic poll extraction from lecture slide text (the fallback when Claude is unavailable)."""
import re
import subprocess
import urllib.request
from pathlib import Path

from .config import BLIND_ANSWER, OPINION_ANSWER, SLIDES_URL
from .models import Poll

OPTION = re.compile(r"^\s*(\d)\.\s+(\S.*)$")
ANSWER = re.compile(r"Answer:\s*(.+)", re.I)
COLUMN_GAP = re.compile(r"\s{3,}")
YOU = re.compile(r"\byour?\b", re.I)
TRUE_FALSE = re.compile(r"^\s*true or false\b", re.I | re.M)


def pdf_pages(pdf: Path) -> list[str]:
    out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True)
    pages = out.stdout.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


def download_slides(n: int, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"lec{n:02d}.pdf"
    with urllib.request.urlopen(SLIDES_URL.format(n=n), timeout=60) as r:
        dest.write_bytes(r.read())
    return dest


def _norm(s: str) -> str:
    s = COLUMN_GAP.split(s.strip())[0].lower().replace("(!)", "")
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())


def _options(lines: list[str]) -> list[str]:
    """The first run of consecutively numbered option lines (1., 2., ...), as normalized text."""
    run: list[str] = []
    for line in lines:
        m = OPTION.match(line)
        if not m:
            continue
        num, text = int(m.group(1)), m.group(2)
        if num == len(run) + 1:
            run.append(_norm(text))
        elif len(run) >= 2:
            break
        elif num == 1:
            run = [_norm(text)]
    return run if len(run) >= 2 else []


def _match(answer: str, options: list[str]) -> int | None:
    a = _norm(answer)
    for i, opt in enumerate(options, 1):
        if opt == a:
            return i
    if a.isdigit() and 1 <= int(a) <= len(options):  # "Answer: 3" naming the option number
        return int(a)
    for i, opt in enumerate(options, 1):
        if opt and a and (opt in a or a in opt):
            return i
    return None


def parse_polls(pages: list[str]) -> list[Poll]:
    polls = []
    for page_no, text in enumerate(pages, 1):
        lines = text.splitlines()
        options = _options(lines)
        if not options and TRUE_FALSE.search(text):
            options = ["true", "false"]  # Vevox shows these as buttons 1 and 2
        if not options:
            continue
        q = next((" ".join(l.split()) for l in lines if l.strip()), "")
        found = ANSWER.search(text)
        answer = _match(found.group(1), options) if found else None
        if answer is not None:
            polls.append(Poll(page_no, len(options), answer, "graded", q))
        elif not found and YOU.search(q):
            polls.append(Poll(page_no, len(options), OPINION_ANSWER, "opinion", q))
        else:
            polls.append(Poll(page_no, len(options), BLIND_ANSWER, "graded", q))
    return polls
