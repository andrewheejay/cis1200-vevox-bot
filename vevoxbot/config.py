"""Fixed facts about the class, the Vevox session, and the bot's timing."""
import os
from datetime import time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SESSION_URL = "https://vevox.app/#/m/458974653"
SCHEDULE_URL = "https://www.seas.upenn.edu/~cis120/26fa/schedule/"
SLIDES_URL = "https://www.seas.upenn.edu/~cis120/26fa/files/slides/lec{n:02d}.pdf"

ET = ZoneInfo("America/New_York")
CLASS_DAYS = {0, 2, 4}  # Mon, Wed, Fri
CLASS_START = time(10, 15)
CLASS_LEN = timedelta(minutes=60)
RUN_START = time(10, 12)
RUN_END = time(11, 20)
SKIP_AFTER = timedelta(minutes=20)

OPINION_ANSWER = 2
BLIND_ANSWER = 1

REPO_DIR = Path(__file__).resolve().parent.parent


def state_path() -> Path:
    """Where the saved Vevox login (Playwright storage state) lives."""
    default = Path.home() / ".config" / "cis1200-vevox-bot" / "state.json"
    return Path(os.environ.get("VEVOX_STATE_FILE", default))
