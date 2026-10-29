"""Read ProSub's kin terms, for review only (never for the build).

ProSub (github.com/matbahasa/ProSub; Okano et al. 2022) asks, for eight Asian
languages, which words are used for 27 kin positions, and whether each can
refer to the speaker (``1st``), to the addressee (``2nd``), or serve as an
address term or a title. It has no licence yet, so its words go only into the
review files, as suggestions for a speaker to check. The clone is expected at
``../ProSub``; without it the review files are written without them.

A word's extension is the union of the positions of the items it is listed
under (Malay *pak cik* under all four uncles is ``Pa;Br``), as for Kinbank; it
is suggested for the concept with that extension, or else for each of its items.
"""

from __future__ import annotations

import csv
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field

import build

PROSUB = build.ROOT.parent / "ProSub"
DATA = PROSUB / "data_all_v2.0.tsv"
#: our lexicon tag -> ProSub's language code
LANGUAGES = {
    "ja": "jpn",
    "ko": "kor",
    "id": "ind",
    "ms": "zsm",
    "jv": "jav",
    "th": "tha",
    "vi": "vie",
    "my": "myn",
}
#: ProSub's kin items (category ``Family``) as kin codes
ITEMS = {
    "8": "Fa",
    "9": "Mo",
    "10": "Fa;El;Br",
    "11": "Mo;El;Br",
    "12": "Fa;Yn;Br",
    "13": "Mo;Yn;Br",
    "14": "Fa;El;Ss",
    "15": "Mo;El;Ss",
    "16": "Fa;Yn;Ss",
    "17": "Mo;Yn;Ss",
    "18": "Fa;Fa",
    "19": "Mo;Fa",
    "20": "Fa;Mo",
    "21": "Mo;Mo",
    "22": "El;Br",
    "23": "El;Ss",
    "24": "Yn;Br",
    "25": "Yn;Ss",
    "26": "Ch",
    "27": "So",
    "28": "Da",
    "29": "Ch;Ch",
    "30": "So;Wi",
    "31": "Da;Hu",
    "32": "Sb;So",
    "33": "Sb;Da",
    "34": "Pa;Sb;Ch",
}
#: ProSub's uses, in the order we list them
USES = ("1st", "2nd", "address", "title")


@dataclass
class Word:
    """A ProSub word: the items it is listed under, its gloss and its uses."""

    form: str
    items: set[str] = field(default_factory=set)
    gloss: str = ""
    uses: set[str] = field(default_factory=set)


def version() -> str:
    """The ProSub commit the review files were written from, or ''."""
    try:
        return subprocess.run(
            ["git", "-C", str(PROSUB), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def read_words(tag: str) -> dict[str, Word]:
    """ProSub's kin words for a language, by form; empty without the clone.

    ProSub numbers homographs (*pak cik01*); the number is dropped. A use counts
    when any of the word's rows judges it ``yes``.
    """
    code = LANGUAGES.get(tag)
    if not code or not DATA.exists():
        return {}
    words: dict[str, Word] = {}
    with DATA.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle, delimiter="\t"):
            row = [cell.strip() for cell in row]
            if len(row) < 10 or row[0] != code or row[4] != "Family":
                continue
            if row[1] not in ITEMS or not row[5]:
                continue
            form = re.sub(r"\d+$", "", row[5]).strip()
            word = words.setdefault(form, Word(form))
            word.items.add(row[1])
            word.gloss = word.gloss or row[7]
            if row[9] == "yes":
                word.uses.add(row[8])
    return words


def suggestions(tag: str, concepts: dict) -> dict[str, list[tuple[str, str]]]:
    """ProSub words by the concept suggested for them: (form, review line).

    Each line reads ``form "gloss" [items] uses``; a word whose extension matches
    no concept is suggested for each of its items, marked ``(partial)``.
    """
    words = read_words(tag)
    if not words:
        return {}
    extent = build.positions(concepts)
    by_extent = {atoms: code for code, atoms in extent.items()}
    found: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for word in words.values():
        atoms = frozenset().union(*(extent[ITEMS[i]] for i in word.items))
        items = ",".join(sorted(word.items, key=int))
        uses = " ".join(u for u in USES if u in word.uses) or "no person use"
        gloss = f' "{word.gloss}"' if word.gloss else ""
        line = f"{word.form}{gloss} [{items}] {uses}"
        if atoms in by_extent:
            found[by_extent[atoms]].append((word.form, line))
        else:
            for item in sorted(word.items, key=int):
                found[ITEMS[item]].append((word.form, f"{line} (partial)"))
    return found
