"""The Mac's copy of the bot: a launchd job that answers first on class mornings whenever the Mac is awake."""
import os
import plistlib
import subprocess
from pathlib import Path

LABEL = "com.andrewheejay.cis1200-vevox-bot"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def launch_agent(repo: Path, uv: str, path: str) -> dict:
    """Mon/Wed/Fri 10:05 (launchd runs a missed time when the Mac wakes): pull tonight's sheet, then answer
    right away with no --defer, while caffeinate keeps the Mac from idling to sleep."""
    command = (f'cd "{repo}" && {{ [ "$(git branch --show-current)" = main ] && git pull -q --ff-only origin main; }}; '
               f'exec /usr/bin/caffeinate -ims "{uv}" run bot run')
    return {
        "Label": LABEL,
        "ProgramArguments": ["/bin/zsh", "-c", command],
        "StartCalendarInterval": [{"Weekday": d, "Hour": 10, "Minute": 5} for d in (1, 3, 5)],
        "EnvironmentVariables": {"PATH": path},
        "StandardOutPath": str(repo / "runs" / "mac.log"),
        "StandardErrorPath": str(repo / "runs" / "mac.log"),
    }


def _domain() -> str:
    return f"gui/{os.getuid()}"


def install(repo: Path, uv: str) -> Path:
    (repo / "runs").mkdir(exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    with open(PLIST, "wb") as f:
        plistlib.dump(launch_agent(repo, uv, os.environ.get("PATH", "/usr/bin:/bin")), f)
    subprocess.run(["launchctl", "bootout", f"{_domain()}/{LABEL}"], capture_output=True)  # replace an old copy
    subprocess.run(["launchctl", "bootstrap", _domain(), str(PLIST)], check=True)
    return PLIST


def uninstall() -> None:
    subprocess.run(["launchctl", "bootout", f"{_domain()}/{LABEL}"], capture_output=True)
    PLIST.unlink(missing_ok=True)
