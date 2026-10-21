# CIS 1200 Vevox attendance bot

Answers the CIS 1200 Vevox polls (Mon/Wed/Fri 10:15–11:15 ET) from that day's lecture slides, as you,
so attendance counts on mornings you sleep through. Design: `docs/superpowers/specs/`.

## How it runs
- **Evening before class** (Sun/Tue/Thu ~9:17 pm ET, `evening` workflow): checks the saved Vevox login
  still works and builds the next class's answer sheet with Claude (falls back to a slide parser),
  committing it to `sheets/`. **If this run fails, GitHub emails you** — usually it means the login expired.
- **Class days** (~9:41 am ET, `class` workflow): opens Vevox headlessly, votes once per poll within a
  few seconds, and writes a summary (Actions run page → Summary; full log in the run's artifact).

## One-time setup
```sh
uv sync
uv run playwright install chromium
uv run bot login --upload      # sign in with PennKey + Duo, close the window; stores the VEVOX_STATE secret
claude setup-token             # in your own terminal; copy the token it prints
gh secret set CLAUDE_CODE_OAUTH_TOKEN   # paste it
```
Re-run `uv run bot login --upload` whenever the evening check says the login expired.

## Day to day
```sh
uv run bot off            # going to class tomorrow: switch the bot off for the next class day
uv run bot off 2026-11-09 # ...or a specific day
uv run bot on 2026-11-09  # undo
uv run bot sheet          # preview the next class's answer sheet
uv run bot check          # is the saved login still good?
```

## Running on the Mac instead
Same code: `caffeinate -ims uv run bot run` on the morning of class (Mac plugged in, lid open).
`bot run --date YYYY-MM-DD --dry-run --no-wait` with `VEVOXBOT_MINUTES=2` is a safe smoke test.

## Rules it follows
- Polls show only generic buttons (1..5 or so), so it keeps its place in the deck by order and time: the next
  unanswered question; one ~20 min overdue counts as skipped; if the class clearly picked a different answer
  it re-syncs to the nearby slide question with that answer. Opinion polls → 2, no idea → 1.
- One vote per poll; it never changes a submitted answer.
