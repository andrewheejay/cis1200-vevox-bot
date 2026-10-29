# CIS 1200 Vevox attendance bot

Answers the CIS 1200 Vevox polls (Mon/Wed/Fri 10:15–11:15 ET) from that day's lecture slides, as you,
so attendance counts on mornings you sleep through. It runs for free on GitHub Actions; your laptop can be
closed. Optionally your Mac answers too, faster, whenever it happens to be awake.

## What you need

- A Penn account enrolled in CIS 1200 (PennKey + Duo for the one-time login).
- A GitHub account and the `gh` CLI, signed in (`gh auth login`; say yes to authenticating Git).
- [`uv`](https://docs.astral.sh/uv/) and Python 3.12 or newer.
- Optional: [Claude Code](https://docs.claude.com/en/docs/claude-code) with a Claude Pro or Max plan. Claude
  reads the slides and works out the answers. Without it, a regex parser builds the answer sheet from the
  `Answer:` lines printed on the slides, which is worse but still works.
- Optional: a Mac, for the faster local answerer.
- Optional: a free [cron-job.org](https://cron-job.org) account, so the runs start on time (see step 5).

## Setup

### 1. Make your own copy
Don't use GitHub's Fork button: scheduled workflows are switched off in forks, and `gh` would keep pointing
at the original repo. Clone and push to a new repo of your own instead:
```sh
git clone https://github.com/andrewheejay/cis1200-vevox-bot.git
cd cis1200-vevox-bot
git remote remove origin
gh repo create cis1200-vevox-bot --private --source=. --remote=origin --push
```
Private or public is your call. A private repo spends about 1,400 of the 2,000 free Actions minutes a
month on a free account; public repos get unlimited minutes. Nothing secret is ever committed either way.

### 2. Install
```sh
uv sync
uv run playwright install chromium
brew install poppler            # pdftotext, only needed to build answer sheets on your own machine
```

### 3. Save your Vevox login
```sh
uv run bot login --upload
```
A browser window opens. Sign in with PennKey + Duo, wait for the CIS 1200 session page, then close the window.
The saved session goes to `~/.config/cis1200-vevox-bot/state.json` and to the `VEVOX_STATE` secret of your
repo. That session *is* your Vevox login, so keep it there and nowhere else. Your PennKey password is never
stored. Run this again whenever the evening check reports the login expired.

### 4. Give the bot Claude (optional)
```sh
claude setup-token                      # in your own terminal; copy the token it prints
gh secret set CLAUDE_CODE_OAUTH_TOKEN   # paste it
```
The token draws on your Claude plan, not a separate API bill. Skip this step and the parser builds the sheets.

### 5. Start the runs on time (cron-job.org)
GitHub's own schedule often fires an hour or more late, which is too late for a 10:15 class. A free
cron-job.org timer starts both workflows at the right minute; GitHub's schedule stays as a last resort.

1. Create a fine-grained GitHub token at https://github.com/settings/personal-access-tokens/new.
   Only select repositories: your copy. Repository permissions: **Actions: Read and write**, nothing else.
   Expiry: end of semester.
2. On cron-job.org create two jobs. Both use time zone `America/New_York`, request method `POST`, and these
   headers: `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`,
   `X-GitHub-Api-Version: 2022-11-28`, `Content-Type: application/json`.

| Job | Days, time | URL | Body |
|---|---|---|---|
| class | Mon, Wed, Fri 09:40 | `https://api.github.com/repos/<you>/cis1200-vevox-bot/actions/workflows/class.yml/dispatches` | `{"ref":"main","inputs":{"real":"true"}}` |
| evening | Sun, Tue, Thu 21:00 | `https://api.github.com/repos/<you>/cis1200-vevox-bot/actions/workflows/evening.yml/dispatches` | `{"ref":"main"}` |

GitHub answers `204` when it starts a run. A class run started outside 9:30–11:00 ET does nothing.

### 6. Check it works
On GitHub, open **Actions → class → Run workflow** and run it with the defaults. That is a two-minute dry
run: it signs in to Vevox, watches, and never clicks. Green, with `signed in to Vevox` in the log, means the
login and browser are fine. Then run **Actions → evening → Run workflow** once; it builds the next class's
answer sheet and commits it to `sheets/`.

### 7. Your Mac, too (optional)
```sh
uv run bot mac-install
```
This adds a launchd job that runs the bot at 10:05 Mon/Wed/Fri whenever the Mac is awake, pulling the latest
answer sheet first. Keep it plugged in with the lid open on class mornings. If it's asleep the cloud covers;
if it wakes mid-class it joins from the current slide. Log: `runs/mac.log`. Undo: `uv run bot mac-uninstall`.

## What happens each week

- **Evening before class** (Sun/Tue/Thu 9 pm ET, `evening` workflow): checks the saved login still works and
  builds the next class's answer sheet, committing it to `sheets/`. **If this run fails, GitHub emails you.**
  Usually that means the login expired: run `uv run bot login --upload` before bed.
- **Class days** (9:40 am ET, `class` workflow): opens Vevox headlessly, waits for 10:12, then votes 5 seconds
  after each poll opens unless an answer is already in (your Mac's). A summary lands on the run's page
  (Actions → the run → Summary); the full log is in the run's artifact.
- **Your Mac, if installed and awake**: answers each poll the moment it opens.

## Day to day
```sh
uv run bot off            # going to class tomorrow: switch the bot off for the next class day
uv run bot off 2026-11-09 # ...or a specific day
uv run bot on 2026-11-09  # undo
uv run bot sheet          # preview the next class's answer sheet
uv run bot check          # is the saved login still good?
```
`bot off` switches off both the cloud and the Mac. The switch is the `SKIP_DATES` variable on your repo.

## How it picks answers
- Vevox shows only numbered buttons, never the question, so the bot keeps its place in the deck by order and
  time: each poll is the next unanswered question on the sheet. A question about 20 minutes overdue counts
  as skipped. If the class clearly picked a different answer than the sheet's, and almost nobody picked the
  bot's, it re-syncs to the nearby slide question with that answer.
- Opinion polls ("how far along are you?") get 2. A poll it can't place at all gets 1. It always votes.
- One vote per poll, and it never changes a submitted answer.

## When something breaks
- **"LOGIN EXPIRED" or the evening run emails you**: `uv run bot login --upload`.
- **A class run says "Not class time; nothing to do."**: it was started outside 9:30–11:00 ET. Check the
  cron-job.org job's time zone and schedule.
- **No sheet for tomorrow**: the slides weren't posted yet when the evening run happened. The class run builds
  one itself if they are up by class time (with Claude before 10:12, with the parser after); if they still
  aren't, every poll gets the blind answer.
- **Safe local smoke test** (watches for two minutes, never clicks):
  ```sh
  VEVOXBOT_MINUTES=2 uv run bot run --dry-run --no-wait
  ```

## Hacking on it
```sh
uv run pytest
```
`vevoxbot/` is the package: `schedule` (which lecture is today), `slides` and `sheet` (slides → answer sheet),
`tracker` (where the lecture is in the deck), `vevox` and `live` (the browser and the poll loop), `gate`
(time windows and the off switch), `mac` (the launchd job), `cli`. Class facts and timing live in
`vevoxbot/config.py`.
