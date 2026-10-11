#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["langcodes", "language_data", "unidecode", "wn>=1.1"]
# ///
"""Collect words for the ILI-linked concepts from existing wordnets.

A concept linked to the Collaborative Interlingual Index (``ili=`` in
``data/concept-ili.tsv``, exact matches only) can take its words from any
wordnet with a synset for that ILI: Japanese 息子 for *son* (``So``). The
wordnets are the ones Cygnet is built from (see `cygnet_wordnets.py`), except
the TUFS lexicons, which are already a source of their own.

Writes ``data/candidates/wordnet-words.tsv``: one row per (language, concept,
word), with the lexicon it came from. Within a language and concept, words keep
the order the wordnet lists them in.

Usage: uv run scripts/wordnet_words.py
"""

from __future__ import annotations

import logging
import tomllib

import build
import cygnet_wordnets
import langcodes
import wn
from kinbank_words import iso_to_tag

logger = logging.getLogger(__name__)

#: lexicons left out: TUFS is read directly (`tufs_words.py`)
SKIP_PREFIXES = ("tufs-",)


def cygnet_languages() -> list[str]:
    """The language keys of Cygnet's wordnet list."""
    with (cygnet_wordnets.CYGNET / "wordnets.toml").open("rb") as handle:
        return list(tomllib.load(handle))


def main() -> None:
    """Write wordnet-words.tsv."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    linked = {c.ili: c.code for c in build.read_concepts().values() if c.ili}
    rows: dict[tuple[str, ...], None] = {}  # ordered, without duplicates
    for key in cygnet_languages():
        tag = iso_to_tag(key)
        name = langcodes.Language.get(tag).display_name()
        found = 0
        try:
            wordnets = cygnet_wordnets.wordnets(key)
        # a source Wn cannot read, or one with a malformed lexicon (an empty version)
        except (wn.Error, KeyError) as error:
            logger.warning("%s: skipped: %s: %s", key, type(error).__name__, error)
            continue
        for wordnet in wordnets:
            lexicon = wordnet.lexicons()[0]
            if lexicon.id.startswith(SKIP_PREFIXES):
                continue
            source = f"{lexicon.id}:{lexicon.version}"
            for ili, code in linked.items():
                for synset in wordnet.synsets(ili=ili):
                    for lemma in synset.lemmas():
                        rows[(name, tag, code, lemma, source, ili)] = None
                        found += 1
        logger.info("%s (%s): %d words", key, tag, found)
    out = build.CANDIDATES / "wordnet-words.tsv"
    with out.open("w", encoding="utf8") as handle:
        handle.write("language\ttag\tconcept\tword\tsource\tili\n")
        # a stable sort: each wordnet's own order within a language and concept
        for row in sorted(rows, key=lambda r: (r[1], r[2])):
            handle.write("\t".join(row) + "\n")
    logger.info("wrote %d rows to %s", len(rows), out.relative_to(build.ROOT))


if __name__ == "__main__":
    main()
