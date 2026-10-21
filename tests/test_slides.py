from vevoxbot.models import Poll
from vevoxbot.slides import parse_polls

TRUE_BANG = """What is the value of ans at the end of this program?
           String a = "hi";
           boolean ans = (a == a);
1. true
2. false
3. NullPointerException
                             Answer: true(!)
                             Why? Same reference.
"""

LONG_ANSWER = """What is the value of ans at the end of this program?
                Thing x;
                int ans = x.go();
1.   1
2.   2
3.   3
4.   Program raises NullPointerException
public class Thing {                         Answer: Program raises NullPointerException
}
"""

OPINION = """How far along in HW09 are you?
1. Not started yet
2. Task 0 finished
3. Working on tasks 1-4
4. Working on task 5
5. Working on task 6
6. All done!
"""

BULLETS = """Announcements
• HW09 due Thursday
  – 1. read the instructions
"""


def test_parses_answer_true_bang():
    assert parse_polls([TRUE_BANG]) == [
        Poll(page=1, choices=3, answer=1, kind="graded",
             q="What is the value of ans at the end of this program?")
    ]


def test_parses_answer_long_text():
    [poll] = parse_polls([LONG_ANSWER])
    assert (poll.choices, poll.answer, poll.kind) == (4, 4, "graded")


def test_opinion_poll():
    [poll] = parse_polls([OPINION])
    assert (poll.choices, poll.answer, poll.kind) == (6, 2, "opinion")


def test_non_poll_pages_ignored():
    assert parse_polls([BULLETS, "Title slide\nLecture 30"]) == []


def test_page_numbers_are_1_based():
    [poll] = parse_polls([BULLETS, "Moral\nUse equals", TRUE_BANG])
    assert poll.page == 3


def test_answer_by_option_number_text():
    page = "Which is bigger?\n1. 3\n2. 7\nAnswer: 7\n"
    assert parse_polls([page])[0].answer == 2


def test_graded_without_answer_line_is_blind():
    page = "What does f 3 return?\n1. 3\n2. 6\n3. 9\n"
    [poll] = parse_polls([page])
    assert (poll.answer, poll.kind) == (1, "graded")


TRUE_FALSE = """True or False: One can build a button from a
label and a notifier.
                       Answer: True
"""


def test_true_false_poll():
    [poll] = parse_polls([TRUE_FALSE])
    assert (poll.choices, poll.answer, poll.kind) == (2, 1, "graded")


def test_true_false_answer_false():
    [poll] = parse_polls([TRUE_FALSE.replace("Answer: True", "Answer: False")])
    assert poll.answer == 2


def test_answer_given_as_option_number():
    page = "What is the type of f?\n1. unit -> int\n2. unit -> unit\n3. int -> unit\n4. int -> int\nAnswer: 3\n"
    assert parse_polls([page])[0].answer == 3


def test_numeric_option_text_wins_over_number():
    page = "What is ans?\n1. 2\n2. 3\n3. 1\nAnswer: 3\n"
    assert parse_polls([page])[0].answer == 2
