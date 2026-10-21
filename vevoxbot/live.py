"""The in-class loop: notice each poll, vote once from the answer sheet, learn from the class's results."""
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from .config import BLIND_ANSWER
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
    due: datetime | None = None  # when to click (the cloud waits a few seconds for the Mac)
    by_other: bool = False  # the answer was already in when it was time to click


def _try_vote(page, answer: int, log) -> bool:
    try:
        buttons = page.buttons()
        if answer not in buttons and buttons:
            answer = BLIND_ANSWER if BLIND_ANSWER in buttons else buttons[0]
        return bool(buttons) and page.vote(answer)
    except Exception as e:
        log(f"vote failed: {e!r}"[:200])
        return False


def _already_in(page) -> bool:
    try:
        return page.voted()
    except Exception:
        return False


def _settle(page, rec: Record, now, log, dry_run) -> None:
    """Once it's time, click the chosen answer, unless this account's answer is already in."""
    if rec.voted or dry_run or (rec.due and now() < rec.due):
        return
    if _already_in(page):
        rec.voted = rec.by_other = True
        log(f"poll {rec.poll_id}: an answer is already in (the Mac's), not clicking")
    elif _try_vote(page, rec.pick.answer, log):
        rec.voted = True
        log(f"poll {rec.poll_id}: clicked {rec.pick.answer}")


def _vote(page, tracker: Tracker, poll_id, n_hint, now, sleep, log, dry_run, due=None) -> Record:
    """Choose once (this advances the tracker, so a bot that isn't clicking still keeps its place), then click
    if it's time; otherwise _settle clicks later."""
    opened_at = now()
    n = n_hint
    waited = 0.0
    while not n and waited < 3:  # websocket didn't say how many choices; give the buttons a moment
        try:
            n = len(page.buttons())
        except Exception:
            n = 0
        if not n:
            sleep(TICK)
            waited += TICK
    pick = tracker.choose(n, opened_at)
    slide = tracker.sheet.polls[pick.index].page if pick.index is not None else None
    log(f"poll {poll_id}: {n} buttons -> slide {slide}, answer {pick.answer} ({pick.reason})")
    rec = Record(poll_id, opened_at, n, pick, slide, False, due=due)
    _settle(page, rec, now, log, dry_run)
    return rec


def run_class(page, tracker: Tracker, end: datetime, now, sleep=time.sleep, log=print, dry_run=False,
              defer: float = 0) -> list[Record]:
    """defer: seconds to wait after a poll opens before clicking, and then only if no answer is in yet."""
    records: list[Record] = []
    by_poll: dict[int, Record] = {}
    state = {"last_vote_at": None, "buttons_since": None, "dom_voted": False}
    errors = 0
    while now() < end:
        try:
            _tick(page, tracker, records, by_poll, state, now, sleep, log, dry_run, defer)
            errors = 0
        except Exception as e:  # one bad tick must never end voting for the rest of class
            errors += 1
            log(f"error (#{errors}): {e!r}"[:200])
            if errors >= 3 and hasattr(page, "recover"):
                try:
                    log("reloading Vevox")
                    page.recover()
                except Exception as e2:
                    log(f"reload failed: {e2!r}"[:200])
                errors = 0
        try:
            sleep(TICK)
        except Exception:
            time.sleep(TICK)
    return records


def _tick(page, tracker, records, by_poll, state, now, sleep, log, dry_run, defer) -> None:
    u = page.latest
    if u and is_open(u.state) and u.poll_id >= 0:
        rec = by_poll.get(u.poll_id)
        if rec is None:
            recent = records[-1] if records else None
            if recent and recent.poll_id is None and (now() - recent.opened_at).total_seconds() < ADOPT_WINDOW:
                recent.poll_id = u.poll_id  # the page scan already voted on this poll
                by_poll[u.poll_id] = recent
            else:
                rec = _vote(page, tracker, u.poll_id, u.n_choices, now, sleep, log, dry_run,
                            due=now() + timedelta(seconds=defer))
                by_poll[u.poll_id] = rec
                records.append(rec)
                state["last_vote_at"] = rec.opened_at
                state["dom_voted"] = True
        else:
            _settle(page, rec, now, log, dry_run)  # its time came, or the buttons showed up late
    elif u and u.state == "results" and u.percentages and u.poll_id in by_poll:
        rec = by_poll[u.poll_id]
        if rec.class_top is None:
            rec.class_top_pct = max(u.percentages)
            rec.class_top = u.percentages.index(rec.class_top_pct) + 1
            rec.moved_to = tracker.correct(rec.pick, rec.n_buttons, u.percentages, rec.opened_at)
            log(f"poll {u.poll_id}: class picked {rec.class_top} ({rec.class_top_pct:.0f}%)"
                + (f", moved to slide {tracker.sheet.polls[rec.moved_to].page}" if rec.moved_to is not None else ""))
    if page.buttons():
        if state["buttons_since"] is None:
            state["buttons_since"] = now()
        ws_quiet = u is None or not is_open(u.state)
        settled = (now() - state["buttons_since"]).total_seconds() >= max(DOM_DEBOUNCE, defer)
        last = state["last_vote_at"]
        cooled = last is None or (now() - last).total_seconds() >= DOM_COOLDOWN
        if ws_quiet and settled and cooled and not state["dom_voted"]:  # a poll the websocket never announced
            rec = _vote(page, tracker, None, 0, now, sleep, log, dry_run, due=now())
            records.append(rec)
            state["last_vote_at"] = rec.opened_at
            state["dom_voted"] = True
    else:
        state["buttons_since"], state["dom_voted"] = None, False


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
                     f"| {'already in' if r.by_other else 'yes' if r.voted else 'NO'} | {top} | {note} |")
    return "\n".join(lines) + "\n"
