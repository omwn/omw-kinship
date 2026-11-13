"""Tests for the ProSub reader used by the review files."""

from __future__ import annotations

from pathlib import Path

import prosub
import pytest

import build


@pytest.fixture
def malay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A small ProSub table: pak cik under all four uncles, abang under one item."""
    rows = [
        ["zsm", item, "", "", "Family", "pak cik01", "", "uncle", use, judgement]
        for item in ("10", "11", "12", "13")
        for use, judgement in (("1st", "yes"), ("title", "no"))
    ] + [["zsm", "22", "", "", "Family", "abang", "", "elder brother", "2nd", "yes"]]
    data = tmp_path / "data.tsv"
    data.write_text(
        "\n".join("\t".join(row + ["", "", "", "", ""]) for row in rows),
        encoding="utf8",
    )
    monkeypatch.setattr(prosub, "DATA", data)


def test_words_are_suggested_for_the_concept_their_items_cover(malay: None) -> None:
    found = prosub.suggestions("ms", build.read_concepts())
    assert found["Pa;Br"] == [("pak cik", 'pak cik "uncle" [10,11,12,13] 1st')]
    assert found["El:Br"] == [("abang", 'abang "elder brother" [22] 2nd')]


def test_languages_prosub_lacks_get_nothing(malay: None) -> None:
    assert prosub.suggestions("cs", build.read_concepts()) == {}
