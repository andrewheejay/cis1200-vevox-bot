"""VevoxPage against trimmed copies of the real participant page, in a real headless Chromium."""
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from vevoxbot.vevox import VevoxPage

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def vevox_on(browser, fixture: str) -> VevoxPage:
    page = browser.new_page(viewport={"width": 1280, "height": 720})
    page.set_content((FIXTURES / fixture).read_text())
    v = VevoxPage(Path("unused"), log=lambda m: None)
    v.page = page
    return v


def test_buttons_are_the_poll_choices_in_the_right_hand_card(browser):
    assert vevox_on(browser, "poll_open.html").buttons() == [1, 2, 3, 4, 5, 6]


def test_results_view_has_no_buttons(browser):
    assert vevox_on(browser, "poll_results.html").buttons() == []


def test_dismiss_dialogs_closes_the_ok_popup(browser):
    v = vevox_on(browser, "poll_open.html")
    v.dismiss_dialogs()
    assert v.page.locator('[data-testid="profile-dialog-identified"]').count() == 0


@pytest.mark.parametrize("n", [1, 6])
def test_vote_selects_the_choice_under_the_popup_and_below_the_fold(browser, n):
    v = vevox_on(browser, "poll_open.html")
    assert v.vote(n)
    selected = v.page.locator('[data-testid="question-choice"][aria-selected="true"]')
    assert selected.count() == 1 and selected.inner_text().strip() == str(n)


def test_vote_for_a_missing_choice_clicks_nothing(browser):
    v = vevox_on(browser, "poll_open.html")
    assert not v.vote(7)
    assert v.page.locator('[aria-selected="true"]').count() == 0


def test_voted_once_an_answer_is_selected(browser):
    v = vevox_on(browser, "poll_open.html")
    assert not v.voted()
    v.vote(2)
    assert v.voted()
