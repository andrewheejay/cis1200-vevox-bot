# CIS 1200 Vevox Attendance Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A bot that, on Mon/Wed/Fri class days, joins Andrew's Vevox session headlessly and answers every poll within 10 s from an answer sheet built from that day's CIS 1200 slides. It runs on GitHub Actions or on the Mac with the same code.

**Architecture:** A small Python package `vevoxbot`. Pure modules (schedule parsing, slide-to-sheet parsing, place tracking, websocket frame parsing, time gating) are unit-tested. Two thin browser modules (schedule fetch, Vevox page driver) use Playwright. A CLI (`bot login|check|sheet|run|off|on`) wires them together. Two GitHub Actions workflows call the CLI: one the evening before class (login check + answer sheet) and one at class time.

**Tech Stack:** Python ≥3.12, Playwright (Chromium), pytest, `pdftotext` (poppler), Claude Code CLI (`claude -p`), GitHub Actions, `gh` CLI, `uv` for local env.

**Spec:** `docs/superpowers/specs/2026-10-20-vevox-attendance-bot-design.md`

## Global Constraints

- Session URL `https://vevox.app/#/m/458974653`; schedule `https://www.seas.upenn.edu/~cis120/26fa/schedule/`; slides `https://www.seas.upenn.edu/~cis120/26fa/files/slides/lec{NN:02d}.pdf`.
- Class Mon/Wed/Fri 10:15–11:15 `America/New_York`. Bot is live 10:12–11:20 ET.
- Answer within 10 s of a poll opening (aim ≤3 s). Never call Claude during class.
- **At most one vote per Vevox `pollId`; never change a submitted answer.**
- Skip rule: a sheet question whose rough time is ≥20 min past is treated as skipped. Rough time = `10:15 + 60 min × page / total_pages`.
- Opinion polls answer **2**. Blind fallback (no plausible sheet match) answers **1**. Any answer larger than the button count becomes 1.
- Never store the PennKey password. Never write the Vevox storage state, `secret`, `userSessionId`, `deviceId`, or `anonymousDeviceId` into logs, summaries, or the repo.
- Repo is **private**. `claude -p` authenticates via `CLAUDE_CODE_OAUTH_TOKEN`; never pass `--bare`.
- Same code runs locally (`uv run bot run`) and in Actions.

## Review Focus

1. **DST change on Sun Nov 1, 2026.** Both UTC cron firings must resolve to exactly one class run per day in EDT and EST (Task 8 test `test_gate_dst`).
2. **No-class days** (rows titled "No Class…", "Midterm…", "Final Exam"). `run` exits 0 without opening Vevox (Task 2 `test_no_class_rows`, Task 8 `test_run_no_class`).
3. **Polls the sheet can't explain** (before the first expected question, after the sheet is exhausted, answer > buttons). The bot still votes (Task 5 `test_exhausted_sheet_votes_blind`, `test_answer_clamped_to_buttons`).
4. **Page reload / websocket reconnect replays an already-voted `pollId` as open.** No second vote (Task 7 `test_replayed_poll_not_revoted`).
5. **Claude returns prose, malformed JSON, or out-of-range numbers.** Fall back to the deterministic parser (Task 4 `test_build_sheet_falls_back`).

---

### Task 1: Project skeleton, config, and the Sheet model

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `vevoxbot/__init__.py`, `vevoxbot/config.py`, `vevoxbot/models.py`, `tests/test_models.py`

**Interfaces:**
- Produces:
  - `config`: `SESSION_URL`, `SCHEDULE_URL`, `SLIDES_URL` (format string with `{n:02d}`), `ET = ZoneInfo("America/New_York")`, `CLASS_DAYS = {0, 2, 4}`, `CLASS_START = time(10, 15)`, `CLASS_LEN = timedelta(minutes=60)`, `RUN_START = time(10, 12)`, `RUN_END = time(11, 20)`, `SKIP_AFTER = timedelta(minutes=20)`, `OPINION_ANSWER = 2`, `BLIND_ANSWER = 1`, `REPO_DIR` (repo root `Path`), `state_path() -> Path` (env `VEVOX_STATE_FILE`, default `~/.config/cis1200-vevox-bot/state.json`).
  - `models`: `@dataclass(frozen=True) Lecture(day: date, title: str, number: int | None)` with property `is_class -> bool` (False when title matches `no class|midterm|final exam`, case-insensitive). `@dataclass Poll(page: int, choices: int, answer: int, kind: Literal["graded","opinion"], q: str = "")`. `@dataclass Sheet(lecture: int, day: date, pages: int, source: str, polls: list[Poll])` with `to_json() -> str`, `@classmethod from_json(s: str) -> Sheet`, `save(path: Path)`, `@classmethod load(path: Path) -> Sheet`.

- [ ] **Step 1:** `git init`, write `pyproject.toml` (package `vevoxbot`, deps `playwright`, dev dep `pytest`, console script `bot = vevoxbot.cli:main`), `.gitignore` (`state.json`, `*.pdf`, `runs/`, `.venv/`, `__pycache__/`), commit the existing `docs/`.
- [ ] **Step 2: Write failing tests** `test_sheet_roundtrip` (Sheet with two Polls → `from_json(to_json())` equals original, `day` survives as `date`) and `test_lecture_is_class` (`"No Class: Fall Break"`, `"Midterm 2"`, `"Final Exam"` → False; `"Transition to Java"` → True).
- [ ] **Step 3:** Run `uv run pytest tests/test_models.py -v`. Expected: FAIL (import error).
- [ ] **Step 4:** Implement `config.py` and `models.py`.
- [ ] **Step 5:** Run tests. Expected: PASS. Commit `feat: project skeleton and sheet model`.

### Task 2: Schedule lookup

**Files:** Create `vevoxbot/schedule.py`, `tests/test_schedule.py`

**Interfaces:**
- Consumes: `Lecture`, `SCHEDULE_URL`.
- Produces: `parse_rows(rows: list[str], year: int) -> list[Lecture]`. Each row is `"Wed 10/21 | Transition to Java | lec22.pdf"` (third cell may be empty → `number=None`). `lecture_on(day: date, lectures: list[Lecture]) -> Lecture | None` returns the row for `day` (None if no row or `not is_class`). `fetch_rows() -> list[str]` renders the schedule page in headless Chromium and returns `"date | title | slides"` for every `tr` that is not `.homework` and whose first cell starts with a weekday.

- [ ] **Step 1: Failing tests:** `test_parse_rows` (rows above → `Lecture(date(2026,10,21), "Transition to Java", 22)`, an empty third cell → `number=None`), `test_no_class_rows` (`lecture_on` for "Fri 11/6 | Midterm 2 |" and "Mon 9/7 | No Class: Labor Day |" → None), `test_lecture_on_missing_day` (Tue → None).
- [ ] **Step 2:** Run. Expected FAIL.
- [ ] **Step 3:** Implement. `fetch_rows` uses `page.evaluate` over `tr:not(.homework)` cells, the same extraction as recon.
- [ ] **Step 4:** Run tests, PASS. Manual check: `uv run python -c "from vevoxbot.schedule import *; print(fetch_rows()[:3])"` prints real rows. Commit.

### Task 3: Deterministic slide parser

**Files:** Create `vevoxbot/slides.py`, `tests/test_slides.py`

**Interfaces:**
- Produces: `pdf_pages(pdf: Path) -> list[str]` (runs `pdftotext -layout pdf -`, splits on `\f`, drops a trailing empty page). `parse_polls(pages: list[str]) -> list[Poll]`: a page is a poll if it has consecutive lines `1. …`, `2. …` (≥2 options, numbered from 1, leading whitespace allowed). `q` = first non-empty line before option 1. `choices` = highest consecutive number. Answer: find `Answer:\s*(.+)` on the page, normalize (lowercase, strip `(!)`, punctuation, whitespace), and pick the option whose normalized text equals it, or failing that contains/is contained by it. Matched → `kind="graded"`. No `Answer:` line → `kind="opinion"`, `answer=OPINION_ANSWER` if `q` contains "you"/"your", else `kind="graded"`, `answer=BLIND_ANSWER`. `download_slides(n: int, dest_dir: Path) -> Path`.

- [ ] **Step 1: Failing tests** with synthetic page strings (do not commit real slide text):
  - `test_parses_answer_true_bang`: options `1. true / 2. false / 3. NullPointerException`, `Answer: true(!)` → `Poll(page=1, choices=3, answer=1, kind="graded")`.
  - `test_parses_answer_long_text`: 4 options ending `4.   Program raises NullPointerException`, `Answer: Program raises NullPointerException` → answer 4.
  - `test_opinion_poll`: "How far along in HW05 are you?" with 6 options, no Answer → `choices=6, answer=2, kind="opinion"`.
  - `test_non_poll_pages_ignored`: bullet slides and a page with a lone `1.` → `[]`.
  - `test_page_numbers_are_1_based`: poll on 3rd page → `page == 3`.
- [ ] **Step 2:** Run, FAIL. **Step 3:** Implement. **Step 4:** Run, PASS. Manual: on the real `lec22.pdf`, the result equals the hand sheet (pages 4, 25, 26, 27, 39, 40 with answers 2, 1, 2, 1, 4, 3). Commit.

### Task 4: Claude-built sheet with fallback

**Files:** Create `vevoxbot/sheet.py`, `tests/test_sheet.py`

**Interfaces:**
- Consumes: `Poll`, `Sheet`, `Lecture`, `pdf_pages`, `parse_polls`, `download_slides`.
- Produces: `class SheetError(Exception)`. `validate_polls(raw: list[dict], n_pages: int) -> list[Poll]` (raises `SheetError` unless every item has `1 ≤ page ≤ n_pages`, `2 ≤ choices ≤ 9`, `1 ≤ answer ≤ choices`, `kind ∈ {graded, opinion}`; sorts by page). `claude_polls(pages: list[str], run=subprocess.run) -> list[Poll]` calls `["claude", "-p", PROMPT, "--output-format", "json"]` with the page texts on stdin (`=== PAGE k ===` separators), timeout 240 s. It parses the CLI's JSON envelope `result` field, then extracts the first `[...]` JSON array from it. `build_sheet(lecture: Lecture, pdf: Path, run=subprocess.run) -> Sheet` tries Claude (`source="claude"`) and falls back to `parse_polls` (`source="parser"`) on any `SheetError`/`OSError`/`TimeoutExpired`/non-zero exit.
- PROMPT must say: find every slide that is an in-class multiple-choice poll (question + numbered options); return JSON array of `{page, choices, answer, kind, q}`; `answer` is the 1-based option number; use the "Answer:" text on the slide when present, else solve it; opinion/survey polls → `kind:"opinion", answer:2`; output only the JSON array.

- [ ] **Step 1: Failing tests** with a fake `run` returning a `CompletedProcess`:
  - `test_claude_polls_parses_envelope`: stdout `{"result": "Here:\n[{\"page\":25,\"choices\":3,\"answer\":1,\"kind\":\"graded\",\"q\":\"x\"}]"}` → one Poll.
  - `test_validate_rejects_out_of_range` (`answer: 5, choices: 3` → `SheetError`).
  - `test_build_sheet_falls_back`: fake run returns prose / exit code 1 / raises `TimeoutExpired`. Each case → `source == "parser"` and polls equal `parse_polls(pages)` (monkeypatch `pdf_pages` to return synthetic pages).
- [ ] **Step 2:** Run, FAIL. **Step 3:** Implement. **Step 4:** Run, PASS. Manual: `build_sheet` on real lec22 with Claude available gives the same six answers. Commit.

### Task 5: Place tracker

**Files:** Create `vevoxbot/tracker.py`, `tests/test_tracker.py`

**Interfaces:**
- Consumes: `Sheet`, `Poll`, config constants.
- Produces: `@dataclass Pick(index: int | None, answer: int, reason: str)`. `class Tracker(sheet: Sheet, class_start: datetime)` with `pointer: int`, `expected(i: int) -> datetime`, `choose(n_buttons: int, now: datetime) -> Pick`, `correct(pick: Pick, n_buttons: int, percentages: list[float], opened_at: datetime) -> int | None`.
- `choose`: candidates are indices ≥ pointer with `now - expected(i) < SKIP_AFTER`. Take the first candidate whose `choices == n_buttons`, else the first candidate. None → `Pick(None, BLIND_ANSWER, "no match")`. Answer > `n_buttons` → `BLIND_ANSWER`. Set `pointer = index + 1`.
- `correct`: only for a graded pick with an index. `top` = 1-based argmax. Return None if `top == pick.answer`, `max < 40`, or `max - percentages[pick.answer-1] < 15`. Candidates = all indices with `choices == n_buttons`, `answer == top`, `kind == "graded"`. Choose the one minimizing `(abs(expected(j) - opened_at), abs(j - pick.index))`, set `pointer = j + 1`, and return `j`. None if there are no candidates.

- [ ] **Step 1: Failing tests** using the lec22 sheet (pages 40; polls p4 6ch ans2 opinion, p25 3ch 1, p26 3ch 2, p27 3ch 1, p39 4ch 4, p40 4ch 3), class_start 2026-10-21 10:15 ET:
  - `test_in_order`: polls at 10:21 (6 btn), 10:52, 10:54, 10:55 (3 btn), 11:12, 11:14 (4 btn) → answers 2,1,2,1,4,3.
  - `test_skips_by_button_count`: first poll at 10:50 with 3 buttons → index 1 (p25).
  - `test_skip_rule`: first poll at 10:45 with 6 buttons → p4 expected 10:21, 24 min overdue → no 6-choice candidate; picks first live candidate (index 1), answer clamped to that poll's answer (1).
  - `test_exhausted_sheet_votes_blind`: after all six, another poll → `Pick(None, 1, ...)`.
  - `test_answer_clamped_to_buttons`: poll p39 (answer 4) chosen with 3 buttons → answer 1.
  - `test_correction_moves_back`: bot picked p26 (answered 2) for a poll opened 10:52; class 80% on 1, 10% on 2 → `correct` returns index 1 (p25, answer 1), pointer 2; the next 3-button poll gets p26's answer 2.
  - `test_correction_ignores_close_vote`: 45% vs 40% → None.
  - `test_no_correction_for_opinion`.
- [ ] **Step 2:** Run, FAIL. **Step 3:** Implement. **Step 4:** Run, PASS. Commit.

### Task 6: Vevox frames and page driver

**Files:** Create `vevoxbot/vevox.py`, `tests/test_vevox.py`, `tests/fixtures/frame_results.json` (redacted structure seen in recon: `DeviceSessionPollStateVer2`, pollId 134, `pollState` "results", 6 choices, `pollResult.choices[].votePercentage` 81.2/16.5/2.3/0/0/0)

**Interfaces:**
- Produces: `@dataclass PollUpdate(poll_id: int, state: str, n_choices: int | None, percentages: list[float] | None)`. `parse_frame(text: str) -> PollUpdate | None` (returns None for `ping`/`pong`/non-JSON/frames without `currentPoll`; a `currentPoll: null` frame → `PollUpdate(-1, "none", None, None)`). `CLOSED_STATES = {"results", "closed", "ended", "finished", "none"}`. `is_open(state: str) -> bool`. `class VevoxPage` used as a context manager `VevoxPage(state_file: Path, headless: bool = True, log=print)`: `.signed_in() -> bool` (after load, URL is on `vevox.app` and not PennKey); `.latest: PollUpdate | None` (updated from websocket frames); `.buttons() -> list[int]` (visible single-digit elements left of x=770 at 1280×720, as in the spike); `.vote(n: int) -> bool` (dismiss dialogs, click button `n`, click a `submit|send|vote` button if one appears, return True if a click landed); `.dismiss_dialogs()`; `.screenshot(path: Path)`.

- [ ] **Step 1: Failing tests:** `test_parse_results_frame` (fixture → poll 134, "results", 6, percentages[0]≈81.2), `test_parse_ignores_ping`, `test_is_open` ("results" False, an unknown state like "open"/"voting" True).
- [ ] **Step 2:** Run, FAIL. **Step 3:** Implement (port from `watcher.py` spike). **Step 4:** Run, PASS. Commit.

### Task 7: Live loop and summary

**Files:** Create `vevoxbot/live.py`, `tests/test_live.py`

**Interfaces:**
- Consumes: `Tracker`, `PollUpdate`, `is_open`, `VevoxPage` (duck-typed: `latest`, `buttons()`, `vote(n)`).
- Produces: `@dataclass Record(poll_id: int | None, opened_at: datetime, n_buttons: int, pick: Pick, page: int | None, voted: bool, class_top: int | None = None, class_top_pct: float | None = None, moved_to: int | None = None)`. `run_class(page, tracker: Tracker, end: datetime, now=..., sleep=time.sleep, log=print, dry_run: bool = False) -> list[Record]`. `summary_markdown(records: list[Record], sheet: Sheet) -> str`.
- Loop (every 0.25 s until `now() >= end`): if `page.latest` is open and its `poll_id` hasn't been voted on, then `n = latest.n_choices or len(page.buttons())`, `pick = tracker.choose(n, now())`, `page.vote(pick.answer)` (skipped when `dry_run`), and record it. If `n` is 0, wait up to 3 s for buttons, then vote 1. When a voted poll reaches state `"results"` with percentages, call `tracker.correct(...)` once and fill `class_top`/`moved_to`. DOM fallback: if `page.latest` is None and `page.buttons()` is non-empty and ≥45 s since the last vote, vote with `poll_id=None`. Retry a failed `vote` up to 3 times within 6 s.

- [ ] **Step 1: Failing tests** with a `FakePage` scripted by fake time:
  - `test_votes_each_poll_once` (two polls open then go to results → two votes with sheet answers).
  - `test_replayed_poll_not_revoted` (poll 135 open → voted; frames replay 135 "open" after a fake reconnect → still one vote).
  - `test_correction_applied_on_results` (results with class top ≠ ours → `moved_to` set).
  - `test_dry_run_never_clicks`.
  - `test_summary_lists_polls` (markdown contains each page number and answer).
- [ ] **Step 2:** Run, FAIL. **Step 3:** Implement. **Step 4:** Run, PASS. Commit.

### Task 8: CLI, skip switch, and time gate

**Files:** Create `vevoxbot/cli.py`, `vevoxbot/gate.py`, `vevoxbot/__main__.py`, `tests/test_gate.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `gate.should_run_class(now_utc: datetime) -> bool`: true iff ET weekday ∈ `CLASS_DAYS` and 9:30 ≤ ET time < 11:00. `gate.should_run_evening(now_utc) -> bool`: true iff ET weekday ∈ {Sun, Tue, Thu} and 20:30 ≤ ET time < 22:30. `gate.next_class_day(today: date) -> date`.
  - `skip_dates() -> set[date]` from env `SKIP_DATES` (comma-separated ISO), else `gh variable get SKIP_DATES`, else empty.
  - `main(argv=None) -> int` subcommands:
    - `login [--upload]`: headed browser; Andrew signs in; save storage state to `state_path()` (chmod 600) when the window closes; `--upload` runs `gh secret set VEVOX_STATE < state_path()`.
    - `check`: exit 0 if signed in, else 2.
    - `sheet [--date YYYY-MM-DD]`: default next class day. No class → print + exit 0. Else build and save `sheets/<date>.json` and print the polls.
    - `run [--date] [--dry-run] [--no-wait]`: skipped date → exit 0. No class → exit 0. Load or build the sheet. Not signed in → exit 2. Wait until `RUN_START`. Run `run_class` until `RUN_END`. Write `runs/<date>.md` and append to `$GITHUB_STEP_SUMMARY`. Exit 1 if any `Record.voted` is False.
    - `off [DATE]` / `on DATE`: add/remove the date in the `SKIP_DATES` repo variable via `gh variable set`. Default DATE = next class day.
- [ ] **Step 1: Failing tests:**
  - `test_gate_dst`: UTC 13:50 and 14:50 on Wed 2026-10-21 (EDT) → exactly one True (13:50 → 9:50 ET). On Wed 2026-11-04 (EST) → exactly one True (14:50 → 9:50 ET).
  - `test_gate_evening`: 01:00 UTC Wed 2026-10-21 (Tue 21:00 EDT) → True.
  - `test_next_class_day` (Tue→Wed, Fri→Mon).
  - `test_skip_dates_env`.
  - `test_run_no_class` (`main(["run","--date","2026-11-06"])` with monkeypatched `fetch_rows` → 0, and `VevoxPage` never constructed).
  - `test_run_skipped_date` (`SKIP_DATES=2026-10-23` → 0, `VevoxPage` never constructed).
- [ ] **Step 2:** Run, FAIL. **Step 3:** Implement. **Step 4:** Run, PASS. Manual: `uv run bot sheet --date 2026-10-21` equals the hand sheet; `uv run bot check` → 0; `uv run bot run --date 2026-10-21 --dry-run --no-wait` runs briefly with `RUN_END` overridden by env `VEVOXBOT_END=HH:MM` (add this override). Commit.

### Task 9: GitHub Actions and the private repo

**Files:** Create `.github/workflows/class.yml`, `.github/workflows/evening.yml`, `README.md`

**Interfaces:**
- Consumes: CLI from Task 8. Secrets `VEVOX_STATE`, `CLAUDE_CODE_OAUTH_TOKEN`. Variable `SKIP_DATES`.
- `class.yml`: `schedule: cron "50 13 * * 1,3,5"` and `"50 14 * * 1,3,5"`, plus `workflow_dispatch` (input `dry_run`). `concurrency: {group: class-day, cancel-in-progress: false}`. First step: `python -c` gate via `vevoxbot.gate.should_run_class`; if false, end the job successfully. Then: setup-python 3.12, `pip install -e .`, `python -m playwright install --with-deps chromium`, `sudo apt-get install -y poppler-utils`, `npm i -g @anthropic-ai/claude-code`, write `$VEVOX_STATE` to `state.json` (umask 077, no echo), `VEVOX_STATE_FILE=state.json SKIP_DATES=${{ vars.SKIP_DATES }} python -m vevoxbot run`. `timeout-minutes: 110`. Upload `runs/` as an artifact.
- `evening.yml`: cron `"0 1 * * 1,3,5"` and `"0 2 * * 1,3,5"` + `workflow_dispatch`. Gate `should_run_evening` (bypassed for dispatch). Run `bot check` (failure → GitHub emails Andrew), then `bot sheet`, then commit `sheets/` and push (`permissions: contents: write`).
- [ ] **Step 1:** Write workflows + README (setup: `bot login --upload`, `claude setup-token` → `gh secret set CLAUDE_CODE_OAUTH_TOKEN`, `bot off`/`on`, running on the Mac).
- [ ] **Step 2:** `gh repo create andrewheejay/cis1200-vevox-bot --private --source . --push`.
- [ ] **Step 3:** Andrew runs `uv run bot login --upload` and `claude setup-token` + `gh secret set CLAUDE_CODE_OAUTH_TOKEN` himself (secrets never pass through the assistant).
- [ ] **Step 4:** `gh workflow run evening.yml` → green; `sheets/<next class day>.json` committed. `gh workflow run class.yml -f dry_run=true` → reaches "signed in" from GitHub's runner (answers the cloud-IP question), exits 0.
- [ ] **Step 5:** Commit.
