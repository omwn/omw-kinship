#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["langcodes", "language_data", "unidecode"]
# ///
"""Collect words for our concepts from Wikidata (CC0).

A concept linked ``exact`` to a Wikidata item in ``data/concept-wikidata.tsv``
takes two kinds of word from it:

- **lexemes**: a Wikidata lexeme with a sense whose "item for this sense"
  (P5137) is the item, e.g. Tamil அண்ணா "elder brother". These are dictionary
  entries; only nouns are kept. A sense's "language style" (P6191, e.g.
  *colloquial*) is kept as a note.
- **labels**: the item's label in each language, when it is a single word. A
  label names the item, so many are descriptions (Swedish *förälders förälder*
  "parent's parent"); those with a space, slash, comma or bracket are left out,
  and so are labels that only copy the English one.

Writes ``data/candidates/wikidata-words.tsv``: one row per (language, concept,
word), with its source (``Wikidata L…-S…`` or ``Wikidata Q… label``) and kind.

Usage: uv run scripts/wikidata_words.py
"""

from __future__ import annotations

import csv
import logging
import re
import urllib.parse
import urllib.request

import build
import langcodes
from kinbank_words import iso_to_tag

logger = logging.getLogger(__name__)

ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "omw-kinship/0.2 (https://github.com/omwn/omw-kinship)"
NOUN = "http://www.wikidata.org/entity/Q1084"
LEXEMES = """
SELECT ?item ?sense ?lemma ?category ?iso ?ietf ?style WHERE {{
  VALUES ?item {{ {items} }}
  ?sense wdt:P5137 ?item .
  ?lexeme ontolex:sense ?sense ; wikibase:lemma ?lemma ;
          wikibase:lexicalCategory ?category ; dct:language ?language .
  OPTIONAL {{ ?language wdt:P220 ?iso }}
  OPTIONAL {{ ?language wdt:P305 ?ietf }}
  OPTIONAL {{ ?sense wdt:P6191/rdfs:label ?style FILTER(LANG(?style) = "en") }}
}}
"""
LABELS = """
SELECT ?item ?label ?lang WHERE {{
  VALUES ?item {{ {items} }}
  ?item rdfs:label ?label .
  BIND(LANG(?label) AS ?lang)
}}
"""
#: Wikimedia language codes that are not the tag we use
WIKIMEDIA = {
    "zh": "cmn",
    "zh-hans": "cmn",
    "zh-hant": "cmn",
    "zh-cn": "cmn",
    "zh-tw": "cmn",
    "zh-sg": "cmn",
    "zh-my": "cmn",
    "zh-hk": "cmn",
    "zh-mo": "cmn",
    "zh-yue": "yue",
    "be-tarask": "be",
    "als": "gsw",
    "bat-smg": "sgs",
    "fiu-vro": "vro",
    "zh-min-nan": "nan",
    "zh-classical": "lzh",
}
#: Wikimedia codes with no language of their own
NOT_LANGUAGES = {"mul", "simple", "und", "zxx"}
#: characters that mark a label as a description, not a word
NOT_A_WORD = re.compile(r"[\s/,;()\[\]]")


def run(query: str) -> list[dict[str, str]]:
    """Run a SPARQL query on Wikidata and return its rows."""
    url = ENDPOINT + "?" + urllib.parse.urlencode({"query": query})
    request = urllib.request.Request(
        url, headers={"Accept": "text/csv", "User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return list(csv.DictReader(response.read().decode("utf8").splitlines()))


def our_tag(code: str) -> str:
    """Our tag for a Wikimedia or ISO language code, or '' if there is none.

    >>> our_tag("zh-hant"), our_tag("sr-ec"), our_tag("eng"), our_tag("mis-x-Q36790")
    ('cmn', 'sh', 'en', '')
    """
    code = code.lower()
    if code in WIKIMEDIA:
        return WIKIMEDIA[code]
    base = code.split("-")[0]
    if base in NOT_LANGUAGES or base == "mis" or not langcodes.tag_is_valid(base):
        return ""
    try:
        return iso_to_tag(langcodes.get(base).to_alpha3())
    except LookupError:
        return ""


def qid(uri: str) -> str:
    """The id at the end of a Wikidata entity URI."""
    return uri.rsplit("/", 1)[1]


def main() -> None:
    """Write wikidata-words.tsv."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    concept_of = {
        row["wikidata"]: row["concept"]
        for row in build.read_tsv(build.DATA / "concept-wikidata.tsv")
        if row["relation"] == "exact"
    }
    items = " ".join(f"wd:{q}" for q in concept_of)
    rows: dict[tuple[str, ...], None] = {}  # ordered, without duplicates

    def add(tag: str, item: str, word: str, source: str, kind: str, note: str) -> None:
        name = langcodes.Language.get(tag).display_name()
        rows[(name, tag, concept_of[item], word, source, kind, note)] = None

    lexemes = run(LEXEMES.format(items=items))
    for row in lexemes:
        if row["category"] != NOUN:
            continue
        # the language's own code, else its ISO 639-3 code, else the lemma's code
        tag = our_tag(row["ietf"]) or our_tag(row["iso"])
        if not tag:
            continue
        add(
            tag,
            qid(row["item"]),
            row["lemma"],
            f"Wikidata {qid(row['sense'])}",
            "lexeme",
            row["style"],
        )
    labels = run(LABELS.format(items=items))
    english = {qid(row["item"]): row["label"] for row in labels if row["lang"] == "en"}
    for row in labels:
        item, label = qid(row["item"]), row["label"]
        tag = our_tag(row["lang"])
        if not tag or NOT_A_WORD.search(label):
            continue
        if tag != "en" and label == english.get(item):
            continue  # a copy of the English label
        add(tag, item, label, f"Wikidata {item} label", "label", "")
    out = build.CANDIDATES / "wikidata-words.tsv"
    with out.open("w", encoding="utf8") as handle:
        handle.write("language\ttag\tconcept\tword\tsource\tkind\tnote\n")
        for row in sorted(rows, key=lambda r: (r[1], r[2], r[5], r[3])):
            handle.write("\t".join(row) + "\n")
    logger.info(
        "wrote %d rows (%d languages) to %s",
        len(rows),
        len({r[1] for r in rows}),
        out.relative_to(build.ROOT),
    )


if __name__ == "__main__":
    main()
