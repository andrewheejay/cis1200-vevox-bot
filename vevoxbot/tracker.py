"""Keeps the bot's place in the answer sheet when polls arrive with only numbered buttons."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from .config import BLIND_ANSWER, CLASS_LEN, SKIP_AFTER
from .models import Sheet

MIN_TOP_PCT = 40.0  # the class's favourite must have at least this share...
MIN_LEAD = 15.0  # ...and beat the bot's answer by this many points before we trust it
NEAR = timedelta(minutes=15)  # how far ahead a button-count match may jump


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
        """Next unanswered question if its option count fits; else a fitting one due soon; else a
        fitting one we'd written off as skipped (the professor ran late); else a blind guess."""
        polls = self.sheet.polls
        ahead = range(self.pointer, len(polls))
        live = [i for i in ahead if now - self.expected(i) < SKIP_AFTER]
        if not live and not any(polls[i].choices == n_buttons for i in ahead):
            return Pick(None, BLIND_ANSWER, "no match")
        fits = [i for i in ahead if polls[i].choices == n_buttons]
        if live and polls[live[0]].choices == n_buttons:
            i, why = live[0], "next in order"
        elif near := [i for i in fits if i in live and self.expected(i) - now <= NEAR]:
            i, why = near[0], "button count matches a question due soon"
        elif late := [i for i in fits if i not in live]:
            i, why = late[-1], "button count matches an overdue question"
        else:
            return Pick(None, BLIND_ANSWER, "no match nearby")
        self.pointer = i + 1
        answer = polls[i].answer if polls[i].answer <= n_buttons else BLIND_ANSWER
        return Pick(i, answer, why)

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
        fits = [j for j, p in enumerate(polls) if p.choices == n_buttons and p.answer == top and p.kind == "graded"]
        if not fits:
            return None
        j = min(fits, key=lambda j: (abs(self.expected(j) - opened_at), abs(j - pick.index)))
        self.pointer = j + 1
        return j
