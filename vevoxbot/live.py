"""The in-class loop: notice each poll, vote once from the answer sheet, learn from the class's results."""
import time
from dataclasses import dataclass
from datetime import datetime

from .models import Sheet
from .tracker import Pick, Tracker
from .vevox import is_open

TICK = 0.25
DOM_COOLDOWN = 45  # seconds between page-scan votes when the websocket says nothing
DOM_DEBOUNCE = 1.5  # buttons must be on screen this long before the page scan acts (websocket goes first)
ADOPT_WINDOW = 20  # a websocket announcement this soon after a page-scan vote is the same poll


@dataclass
class Record:
    poll_id: int | None
    opened_at: datetime
    n_buttons: int
    pick: Pick
    page: int | None
    voted: bool
    class_top: int | None = None
    class_top_pct: float | None = None
    moved_to: int | None = None


def _vote(page, tracker: Tracker, poll_id, n_hint, now, sleep, log, dry_run) -> Record:
    opened_at = now()
    n = n_hint or len(page.buttons())
    waited = 0.0
    while not n and waited < 3:  # websocket didn't say how many choices; wait for the buttons
        sleep(TICK)
        waited += TICK
        n = len(page.buttons())
    pick = tracker.choose(n, opened_at)
    slide = tracker.sheet.polls[pick.index].page if pick.index is not None else None
    voted = False
    if not dry_run:
        for _ in range(3):
            if page.vote(pick.answer):
                voted = True
                break
            sleep(1)
    log(f"poll {poll_id}: {n} buttons -> slide {slide}, answered {pick.answer} ({pick.reason})"
        f"{'' if voted else ' [NOT CLICKED]'}")
    return Record(poll_id, opened_at, n, pick, slide, voted)


def run_class(page, tracker: Tracker, end: datetime, now, sleep=time.sleep, log=print, dry_run=False) -> list[Record]:
    records: list[Record] = []
    by_poll: dict[int, Record] = {}
    last_vote_at = None
    buttons_since = None  # when the current run of visible buttons started
    dom_voted = False  # page scan already voted for this run of visible buttons
    while now() < end:
        u = page.latest
        if u and is_open(u.state) and u.poll_id >= 0 and u.poll_id not in by_poll:
            recent = records[-1] if records else None
            if recent and recent.poll_id is None and (now() - recent.opened_at).total_seconds() < ADOPT_WINDOW:
                recent.poll_id = u.poll_id  # the page scan already voted on this poll
                by_poll[u.poll_id] = recent
            else:
                rec = _vote(page, tracker, u.poll_id, u.n_choices, now, sleep, log, dry_run)
                by_poll[u.poll_id] = rec
                records.append(rec)
                last_vote_at = rec.opened_at
                dom_voted = True
        elif u and u.state == "results" and u.percentages and u.poll_id in by_poll:
            rec = by_poll[u.poll_id]
            if rec.class_top is None:
                rec.class_top_pct = max(u.percentages)
                rec.class_top = u.percentages.index(rec.class_top_pct) + 1
                rec.moved_to = tracker.correct(rec.pick, rec.n_buttons, u.percentages, rec.opened_at)
                log(f"poll {u.poll_id}: class picked {rec.class_top} ({rec.class_top_pct:.0f}%)"
                    + (f", moved to slide {tracker.sheet.polls[rec.moved_to].page}" if rec.moved_to is not None else ""))
        if page.buttons():
            if buttons_since is None:
                buttons_since = now()
            ws_quiet = u is None or not is_open(u.state)
            settled = (now() - buttons_since).total_seconds() >= DOM_DEBOUNCE
            cooled = last_vote_at is None or (now() - last_vote_at).total_seconds() >= DOM_COOLDOWN
            if ws_quiet and settled and cooled and not dom_voted:  # a poll the websocket never announced
                rec = _vote(page, tracker, None, 0, now, sleep, log, dry_run)
                records.append(rec)
                last_vote_at = rec.opened_at
                dom_voted = True
        else:
            buttons_since, dom_voted = None, False
        sleep(TICK)
    return records


def summary_markdown(records: list[Record], sheet: Sheet) -> str:
    lines = [
        f"## CIS 1200 lec{sheet.lecture:02d} — {sheet.day.isoformat()}",
        f"Answer sheet: {len(sheet.polls)} polls (built by {sheet.source}). Polls seen: {len(records)}.",
        "",
        "| time | buttons | slide | answered | clicked | class top | note |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in records:
        top = f"{r.class_top} ({r.class_top_pct:.0f}%)" if r.class_top else "–"
        note = r.pick.reason
        if r.moved_to is not None:
            note += f"; moved to slide {sheet.polls[r.moved_to].page}"
        lines.append(f"| {r.opened_at:%H:%M:%S} | {r.n_buttons} | {r.page if r.page else '–'} | {r.pick.answer} "
                     f"| {'yes' if r.voted else 'NO'} | {top} | {note} |")
    return "\n".join(lines) + "\n"
