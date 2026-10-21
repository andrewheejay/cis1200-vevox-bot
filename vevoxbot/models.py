"""Lectures from the schedule and the answer sheet built from their slides."""
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

NO_CLASS = re.compile(r"no class|midterm|final exam", re.I)


@dataclass(frozen=True)
class Lecture:
    day: date
    title: str
    number: int | None  # lecNN.pdf; None when no slides are posted

    @property
    def is_class(self) -> bool:
        return not NO_CLASS.search(self.title)


@dataclass
class Poll:
    page: int  # 1-based page in the PDF
    choices: int
    answer: int  # 1-based option number
    kind: Literal["graded", "opinion"]
    q: str = ""


@dataclass
class Sheet:
    lecture: int
    day: date
    pages: int
    source: str  # "claude", "parser", or "manual"
    polls: list[Poll] = field(default_factory=list)

    def to_json(self) -> str:
        d = asdict(self)
        d["day"] = self.day.isoformat()
        return json.dumps(d, indent=2)

    @classmethod
    def from_json(cls, s: str) -> "Sheet":
        d = json.loads(s)
        d["day"] = date.fromisoformat(d["day"])
        d["polls"] = [Poll(**p) for p in d["polls"]]
        return cls(**d)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n")

    @classmethod
    def load(cls, path: Path) -> "Sheet":
        return cls.from_json(path.read_text())
