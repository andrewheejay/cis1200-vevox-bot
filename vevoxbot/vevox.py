"""The Vevox participant page: live poll state from its websocket, and clicking answer buttons."""
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from .config import SESSION_URL

CLOSED_STATES = {"results", "closed", "ended", "finished", "none"}
SECRET_KEYS = re.compile(r'"(secret|key|deviceId|anonymousDeviceId|userSessionId|email|thirdPartyUserId|appId)"\s*:\s*"[^"]*"')

# Visible elements left of the Results card whose whole text is one digit are the answer buttons.
FIND_BUTTONS = """() => {
  const best = {};
  for (const e of document.querySelectorAll('body *')) {
    const t = (e.innerText || '').trim();
    if (!/^[1-9]$/.test(t) || e.children.length > 2) continue;
    const r = e.getBoundingClientRect();
    if (r.width < 8 || r.height < 8 || r.x + r.width / 2 > 770) continue;
    const c = {n: +t, x: r.x + r.width / 2, y: r.y + r.height / 2, pointer: getComputedStyle(e).cursor === 'pointer'};
    if (!best[t] || (c.pointer && !best[t].pointer)) best[t] = c;
  }
  return Object.values(best).sort((a, b) => a.n - b.n);
}"""


@dataclass
class PollUpdate:
    poll_id: int  # -1 when no poll is current
    state: str
    n_choices: int | None
    percentages: list[float] | None  # in button order, once results are shown


def is_open(state: str) -> bool:
    return state not in CLOSED_STATES


def redact(text: str) -> str:
    return SECRET_KEYS.sub(lambda m: f'"{m.group(1)}":"<redacted>"', text)


def parse_frame(text: str) -> PollUpdate | None:
    try:
        msg = json.loads(text)
        data = msg["data"]
    except (ValueError, KeyError, TypeError):
        return None
    if not isinstance(data, dict) or "currentPoll" not in data:
        return None
    poll = data["currentPoll"]
    if poll is None:
        return PollUpdate(-1, "none", None, None)
    n_choices, percentages = None, None
    questions = poll.get("questionData") or []
    if questions:
        choice_ids = [c["id"] for c in questions[0]["question"].get("choices") or []]
        n_choices = len(choice_ids) or None
        result = questions[0].get("pollResult")
        if result and choice_ids:
            by_id = {c["choiceId"]: float(c.get("votePercentage") or 0) for c in result.get("choices") or []}
            percentages = [by_id.get(i, 0.0) for i in choice_ids]
    return PollUpdate(int(poll["pollId"]), str(poll["pollState"]), n_choices, percentages)


class VevoxPage:
    """Headless Vevox session as Andrew. Use as a context manager."""

    def __init__(self, state_file: Path, headless: bool = True, log=print, record: Path | None = None):
        self.state_file, self.headless, self.log, self.record = state_file, headless, log, record
        self.latest: PollUpdate | None = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._ctx = self._browser.new_context(storage_state=str(self.state_file), viewport={"width": 1280, "height": 720})
        self.page = self._ctx.new_page()
        self.page.on("websocket", lambda ws: ws.on("framereceived", self._on_frame))
        self.page.goto(SESSION_URL)
        deadline = time.time() + 25
        while time.time() < deadline and not self._settled():
            self.page.wait_for_timeout(500)
        self.dismiss_dialogs()
        return self

    def __exit__(self, *exc):
        self._browser.close()
        self._pw.stop()

    def _settled(self) -> bool:
        return not self.signed_in() or self.page.get_by_text("Exit Session").count() > 0

    def _on_frame(self, payload) -> None:
        text = payload if isinstance(payload, str) else payload.decode("utf-8", "replace")
        if self.record:
            with open(self.record, "a") as f:
                f.write(json.dumps({"t": time.strftime("%H:%M:%S"), "frame": redact(text)[:200_000]}) + "\n")
        update = parse_frame(text)
        if update:
            if not self.latest or (update.poll_id, update.state) != (self.latest.poll_id, self.latest.state):
                self.log(f"poll {update.poll_id}: {update.state} ({update.n_choices} choices)")
            self.latest = update

    def signed_in(self) -> bool:
        url = self.page.url
        return url.startswith("https://vevox.app") and "pennkey" not in url and "weblogin" not in url

    def wait(self, seconds: float) -> None:
        """Sleep while letting Playwright deliver websocket events (time.sleep would starve them)."""
        self.page.wait_for_timeout(seconds * 1000)

    def dismiss_dialogs(self) -> None:
        ok = self.page.get_by_role("button", name="OK", exact=True)
        if ok.count() and ok.first.is_visible():
            ok.first.click()

    def _buttons(self) -> list[dict]:
        return self.page.evaluate(FIND_BUTTONS)

    def buttons(self) -> list[int]:
        return [b["n"] for b in self._buttons()]

    def vote(self, n: int) -> bool:
        self.dismiss_dialogs()
        target = next((b for b in self._buttons() if b["n"] == n), None)
        if not target:
            return False
        self.page.mouse.click(target["x"], target["y"])
        self.page.wait_for_timeout(500)
        submit = self.page.get_by_role("button", name=re.compile(r"^\s*(submit|send|vote)\s*$", re.I))
        if submit.count() and submit.first.is_visible():
            submit.first.click()
        return True

    def screenshot(self, path: Path) -> None:
        self.page.screenshot(path=str(path))
