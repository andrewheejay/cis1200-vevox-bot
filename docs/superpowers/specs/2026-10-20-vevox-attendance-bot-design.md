# CIS 1200 Vevox Attendance Bot: Design

*2026-10-20. Written from a conversation with Andrew (the student) plus recon done that evening.*

## Intent

CIS 1200 meets Mon/Wed/Fri, 10:15–11:15 Eastern. The professor runs polls in Vevox, and attendance credit comes from answering them. Andrew wants credit on the mornings he sleeps through class. The professor has explicitly allowed students to build bots for this, and agentic coding counts. The bot joins the Vevox session as Andrew and answers every poll that opens during class.

**Success** means every poll opened during class gets an answer from Andrew's account within 10 seconds, without Andrew's computer being on, and as many as possible are correct.

## Goals

- Runs unattended in the cloud on class days. Andrew's laptop can be closed or off.
- Answers every poll within **10 seconds** of it appearing (aim for ≤3 s).
- Picks answers from **that day's lecture slides only**, tracking where the lecture is in the deck.
- Never leaves a poll unanswered. When unsure it still answers; with no idea at all it picks **1 or 2**.
- Warns Andrew early enough to fix problems, especially an expired login, the evening before class rather than at 10:15.
- Leaves a per-class summary Andrew can read when he wakes up.

## Non-goals

- Automating PennKey password entry or Duo. The PennKey password is never stored anywhere.
- Vevox Q&A board, word clouds, or other question types (see *Left to the builder* for what to do if one shows up).
- Use by anyone other than Andrew.

## Anti-goals (failure even if it technically works)

- **Silent failure.** The bot breaks and Andrew doesn't find out until attendance is missed.
- **A poll goes unanswered** because the bot was unsure, slow, or confused.
- **Leaking the Vevox session** (public repo, logs, artifacts). It is equivalent to being logged in as Andrew.
- Erratic behavior visible to the professor, such as changing a submitted answer repeatedly or voting in polls outside class.

## Established facts (recon, 2026-10-20)

### Slides
- Schedule: `https://www.seas.upenn.edu/~cis120/26fa/schedule/`. The table is generated client-side by `js/schedule.js`. Rendering it in a headless browser and reading the rows gives `date | title | lecNN.pdf` directly. Rows with no lecture ("No Class: …", "Midterm …") have no slide link and don't advance NN.
- Slide PDFs: `https://www.seas.upenn.edu/~cis120/26fa/files/slides/lecNN.pdf` (two digits, zero-padded). Plain HTTPS, no auth.
- Slides for a lecture are up by the **evening before** (lec22 for Wed 10/21 was posted by Tue 10/20 9 pm). Lectures without posted slides show a grey title and an empty slide cell.
- Poll slides are a question followed by lines `1. …`, `2. …`. The answer is often printed on the slide (`Answer: false`, `Answer: true(!)`, `Answer: Program raises NullPointerException`), which then has to be mapped back to an option number. Some polls are opinion polls with no right answer ("How far along in HW05 are you?", 6 options). One deck can have several polls with **identical stems and options** (lec22 slides 25–27 are all "What is the value of ans…" with true/false/NPE).
- `pdftotext -layout` extracts all of this cleanly from the decks checked (lec21, lec22).

### Vevox
- Session: `https://vevox.app/#/m/458974653`, titled "CIS 1200 - 26fa", `projectType: authenticated_lite`. Opening it requires **Penn SSO** (PennKey + Duo).
- After login, Vevox keeps its auth in `localStorage` on `https://vevox.app` (`auth-session-id`, `ReactorAPIDeviceId`, `ReactorAPIAnonymousDeviceId`, …). Penn and Duo cookies are session-only and not needed afterwards. **A Playwright `storage_state` saved after login worked in a fresh headless browser** with no SSO. How long it stays valid is not yet known (being measured). Whether it works from GitHub's IP ranges is not yet known.
- On load the participant page sometimes shows a "Profile" dialog; its "OK" button dismisses it.
- Live updates arrive over a websocket, `wss://web4-httpapi.vevox.com/api`. The message `DeviceSessionPollStateVer2` carries `currentPoll` with `pollId` (134 for Monday's last poll), `pollState` (`"results"` observed; the name of the open/voting state is still to be confirmed), `pollType: "single"`, `pollCountdown`, and `questionData[0]`. `questionData[0]` holds `question` (`@type: DeviceChoiceVoteQuestion`, `text: "Choose..."`, `choices[]` with text `"1"…"N"`, `minNumSel`/`maxNumSel` 1), `pollResult.choices[].votePercentage`, and `correctAnswer: null`.
- Polls give **no question text and no option text**, only buttons labelled `1…N`. Observed: N = 6 for the 6-option HW poll, so **N likely equals the slide's option count** (to be confirmed).
- The correct answer is **never shown**. After a poll, participants see the class's vote percentages.
- Andrew reports an answer window of about 10 seconds.

### Accounts and tools
- Andrew has a Claude Max plan. `claude setup-token` produces a one-year token (`CLAUDE_CODE_OAUTH_TOKEN`) that draws from Max plan limits, with no separate billing, and is documented for CI use via `claude -p`. It does not work with the plain Messages API/SDK.
- GitHub CLI is authenticated as `andrewheejay`.

## How it works (decided)

1. **Hosting.** A scheduled GitHub Actions workflow in a **private** repo under Andrew's account. Cron is UTC, so it must handle EDT→EST on **Sun Nov 1, 2026** (e.g. schedule both UTC times and have the job exit if it isn't the right ET hour). Start around **9:50 ET** to absorb cron delays, wait in-job until ~10:13, run until ~11:20.
2. **Login.** A local `login` command opens a real browser, Andrew signs in with PennKey + Duo, and the script saves the Vevox `storage_state` and stores it as an encrypted GitHub secret (`gh secret set`). Re-running it is how Andrew refreshes an expired login.
3. **Evening-before check** (Sun/Tue/Thu around 9 pm ET, before each class day). Open Vevox headless with the saved session. If it lands on PennKey login, alert Andrew so he can re-run `login` before bed. Also find tomorrow's lecture on the schedule, build the answer sheet (step 4), and alert if there are no slides or there's no class.
4. **Answer sheet.** Download that day's PDF. `claude -p` (with `CLAUDE_CODE_OAUTH_TOKEN`) returns JSON listing every poll slide in deck order: page number, option count, correct option number, graded vs opinion, and confidence. It uses the printed "Answer:" when present and otherwise works the problem out. Opinion polls get **2**. The output is validated. If Claude is unavailable (plan limit, error), a deterministic parser (`pdftotext` plus regex for numbered options and `Answer:` lines) produces a best-effort sheet. Answering must never depend on Claude being reachable during class.
5. **Live answering.** Headless Chromium (Playwright) with the saved session. It detects a new poll from the websocket (new `pollId` entering the open state), with DOM polling as a backup. It chooses an answer from the sheet and **clicks the button in the page** like a normal participant; it does not forge websocket messages. One answer per poll.
6. **Keeping its place** (rules from Andrew):
   - Keep a pointer to the next unanswered question on the sheet.
   - Each question's rough time is `10:15 + 60 min × page / total_pages`.
   - When a poll opens with N buttons, prefer the next question whose option count is N.
   - **Skip rule:** if a question's rough time is ~20 minutes past and no poll has come for it, treat it as skipped and move on.
   - **Correction rule:** once results are visible, if the class's top choice differs from the bot's answer on a graded question, look for nearby questions (same option count) whose answer equals the class's top choice. If there's a convincing one, move the pointer to just after it. In Andrew's words: "find all the questions from the slides that had answer 4 and try to find the right place to continue."
   - **Fallback:** no plausible match → answer 1 or 2.
7. **Summary.** After class, record each poll: time opened, N, which sheet question it matched, the bot's answer, the class's top choice and %, and whether they agreed. Failures alert Andrew.
8. **Secrets.** Vevox session and Claude token are GitHub secrets. Logs and artifacts never contain them (the recorded websocket traffic includes a `secret`, `userSessionId`, and device IDs, which must be redacted).
9. **Days Andrew attends** (Andrew's choice). The bot runs **every class day by default**. Andrew turns it off for a given class with **one command, the night before**. The exact mechanism is the builder's call, e.g. a repo variable holding a skip date set by a tiny script. It must be impossible for the bot to vote on a day that was switched off.
10. **One vote per poll.** The bot votes at most once per Vevox `pollId` and never changes a submitted answer.

## Rollout (decided)
- **Wed 10/21:** a throwaway watcher runs on Andrew's Mac (10:05–11:25). It records the poll UI, websocket messages, and results, and **also votes** from the hand-built lec22 sheet (in order, skip rule, once per `pollId`). This confirms the open-state name, button count, countdown, and dialog behavior before the real bot relies on them. It also shows whether the session is still valid after ~13 hours.
- **Fri 10/23 target** (builder's call, since Andrew said ASAP). Ship a first version that answers from the Claude-built sheet in deck order with the skip rule and one-vote-per-poll. Add the **correction rule** right after, using Wednesday's recording of what results look like. If the cloud path isn't proven by Thursday night, Friday runs from Andrew's Mac with the same code.
- **If the saved session doesn't hold up in the cloud** (expires too fast, rotates on use, or is rejected from GitHub IPs): **deliberately deferred.** Andrew will decide once there's evidence. Candidates are running on the Mac, a small paid server (~$4–6/mo; Andrew has AWS), or re-logging-in more often with reminders. Until then, the Mac is the interim fallback. Build so the same bot code runs on both the Mac and GitHub Actions.

## Constraints
- 10-second answer window.
- GitHub Actions cron can fire late (usually minutes). The private-repo free tier is 2,000 min/month; this needs roughly 15–20 h/month across the class runs and the nightly checks. Size this correctly.
- Max plan rate limits can make `claude -p` fail; see the fallback in step 4.
- Calendar exceptions: holidays, midterm days (e.g. Fri 11/6), Thanksgiving. The schedule page is the source of truth.

## Left to the builder
- Language and libraries (Python + Playwright is what the spike used and works).
- Exact thresholds for the correction rule (how lopsided the class vote must be, how far from the pointer to search).
- Which of 1 or 2 to use as the blind fallback.
- Repo name and layout.
- Non-choice question types, if one ever appears: answer something minimal if possible, otherwise log and alert.
- The alert channel. The default is GitHub's built-in failure emails plus the job summary page.

## Pieces built during exploration (throwaway)
In the session scratchpad: `login_spike.py` (save and inspect a Vevox session), `watcher.py` (record/answer one lecture), `sheet.json` (hand-built answer sheet for lec22). These can be reused as reference, but they are not the product.
