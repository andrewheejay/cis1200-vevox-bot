"""Keeps the bot's place in the answer sheet when polls arrive with only numbered buttons."""
from dataclasses import dataclass
from datetime import datetime

from .config import BLIND_ANSWER, CLASS_LEN, SKIP_AFTER
from .models import Sheet

MIN_TOP_PCT = 40.0  # the class's favourite must have at least this share...
MIN_LEAD = 15.0  # ...and beat the bot's answer by this many points before we trust it


@dataclass
class Pick:
    index: int | None  # position in sheet.polls, None for a blind guess
    answer: int
    reason: str


class Tracker:
    def __init__(self, sheet: Sheet, class_start: datetime):
        self.sheet = sheet
        self.class_start = class_start
        self.pointer = 0

    def expected(self, i: int) -> datetime:
        return self.class_start + CLASS_LEN * (self.sheet.polls[i].page / self.sheet.pages)

    def choose(self, n_buttons: int, now: datetime) -> Pick:
        """The next question in deck order that isn't 20+ min overdue. Vevox shows the same generic
        buttons for every poll, so the button count only caps the answer, it never identifies the question."""
        polls = self.sheet.polls
        live = [i for i in range(self.pointer, len(polls)) if now - self.expected(i) < SKIP_AFTER]
        if not live:
            return Pick(None, BLIND_ANSWER, "no match")
        i = live[0]
        skipped = i - self.pointer
        self.pointer = i + 1
        answer = polls[i].answer if polls[i].answer <= n_buttons else BLIND_ANSWER
        return Pick(i, answer, "next in order" + (f", {skipped} overdue skipped" if skipped else ""))

    def correct(self, pick: Pick, n_buttons: int, percentages: list[float], opened_at: datetime) -> int | None:
        """If the class clearly preferred another answer, move to the sheet question that fits it."""
        if pick.index is None or self.sheet.polls[pick.index].kind != "graded" or not percentages:
            return None
        top_pct = max(percentages)
        top = percentages.index(top_pct) + 1
        ours = percentages[pick.answer - 1] if pick.answer <= len(percentages) else 0.0
        if top == pick.answer or top_pct < MIN_TOP_PCT or top_pct - ours < MIN_LEAD:
            return None
        polls = self.sheet.polls
        fits = [j for j, p in enumerate(polls) if p.answer == top and p.kind == "graded"]
        if not fits:
            return None
        j = min(fits, key=lambda j: (abs(self.expected(j) - opened_at), abs(j - pick.index)))
        self.pointer = j + 1
        return j
