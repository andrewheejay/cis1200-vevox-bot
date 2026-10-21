from pathlib import Path

from vevoxbot.mac import launch_agent


def test_launch_agent_runs_mon_wed_fri_at_1005():
    agent = launch_agent(Path("/repo"), "/opt/homebrew/bin/uv", "/opt/homebrew/bin:/usr/bin:/bin")
    times = agent["StartCalendarInterval"]
    assert sorted(t["Weekday"] for t in times) == [1, 3, 5]
    assert {(t["Hour"], t["Minute"]) for t in times} == {(10, 5)}
    assert agent["EnvironmentVariables"]["PATH"] == "/opt/homebrew/bin:/usr/bin:/bin"


def test_launch_agent_answers_right_away_and_stays_awake():
    command = launch_agent(Path("/repo"), "/opt/homebrew/bin/uv", "/usr/bin")["ProgramArguments"][-1]
    assert 'cd "/repo"' in command and "caffeinate -ims" in command
    assert command.rstrip().endswith('"/opt/homebrew/bin/uv" run bot run')  # no --defer: the Mac goes first
