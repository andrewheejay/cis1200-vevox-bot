import json
from pathlib import Path

from vevoxbot.vevox import PollUpdate, is_open, parse_frame, redact

FIXTURE = (Path(__file__).parent / "fixtures" / "frame_results.json").read_text()


def test_parse_results_frame():
    u = parse_frame(FIXTURE)
    assert (u.poll_id, u.state, u.n_choices) == (134, "results", 6)
    assert round(u.percentages[0], 1) == 81.2 and round(u.percentages[1], 1) == 16.5


def test_parse_open_frame_without_results():
    d = json.loads(FIXTURE)
    d["data"]["currentPoll"].update(pollId=135, pollState="open")
    del d["data"]["currentPoll"]["questionData"][0]["pollResult"]
    assert parse_frame(json.dumps(d)) == PollUpdate(135, "open", 6, None)


def test_parse_no_current_poll():
    assert parse_frame('{"message": "X", "data": {"currentPoll": null}}') == PollUpdate(-1, "none", None, None)


def test_parse_ignores_ping():
    assert parse_frame("ping") is None
    assert parse_frame('{"status": "success", "data": {"tenancyId": null}}') is None


def test_is_open():
    assert not is_open("results")
    assert not is_open("none")
    assert not is_open("closing")  # Vevox: open -> closing -> closed -> results
    assert is_open("open") and is_open("voting")


def test_redact_secrets():
    raw = '{"data":{"secret":"abc+/=","key":"k","deviceId":"d-1","anonymousDeviceId":"a-2","userSessionId":"u3","email":"me@x.com"}}'
    out = redact(raw)
    for value in ("abc+/=", "d-1", "a-2", "u3", "me@x.com"):
        assert value not in out
