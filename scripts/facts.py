#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["langcodes", "language_data", "unidecode"]
# ///
"""Compute every kinship figure the paper cites, and write them to facts.json.

One command, one file, so that any number in the paper can be checked against
the data without re-deriving it by hand; the paper's ``facts_tex.py`` turns the
file into macros (``\\fact{kin.concepts.total}``). Run it after changing
anything. It reruns `build.py`'s pipeline in memory, writing nothing but the
JSON, so it agrees with the release that `build.py` would write from the same
data. The Kinbank figures that `build.py` does not use (how many varieties
Kinbank has, which record half siblings) come from a clone of Kinbank and are
left out, with a warning, if there is none.

Keys are short, lowercase and stable, grouped by topic; every leaf is a number,
an int or a percentage rounded to one decimal as the paper gives it.

Usage: uv run scripts/facts.py [--kinbank ../kinbank] [--out reports/facts.json]
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import kinbank_concepts

import build as b

logger = logging.getLogger(__name__)

#: the Kinbank-admitted concepts the paper gives family counts for
FAMILY_EXAMPLES = {
    "x_ss_da": "x;Ss;Da",
    "hu_fa": "Hu;Fa",
    "fa_fa_br": "Fa|Fa;Br",
    "cross_cousin": "Fa;Ss;Ch|Mo;Br;Ch",
    "grandparent_grandchild": "Ch;Ch|Pa;Pa",
    "opposite_sex_sibling": "o;Br|x;Ss",
    "omaha": "Mo;Br|Mo;Br;So",
}
#: concepts whose number of languages the paper gives (Table 1)
LANGUAGE_EXAMPLES = {"fa_fa_br": "Fa|Fa;Br"}
#: the gender-neutral concepts where wordnet words contradict the most gaps
NEUTRAL = ("Pa;Sb;Ch", "Sb", "Gr;Pr")
#: Kinbank's half-sibling positions: mhB, fehZ, mhB_FS, ...
HALF = re.compile(r"[mf][ey]?h[BZ]")
#: Kinbank's step-sibling positions: mFWS_notBorhB, ...
STEP = re.compile(r"not[BZ]orh[BZ]")
#: the positions a word for any half sibling fills
ANY_HALF = {"mhB", "mhZ", "fhB", "fhZ"}
#: "Kinbank: 230 languages, 73 families, 7 macroareas"
KINBANK_SOURCE = re.compile(r"Kinbank: (\d+) languages, (\d+) families")
#: how a Kinbank concept compares with KinDiv's for the same word (`agreement`)
VERDICTS = ("exact", "equal", "broader", "narrower", "overlapping", "disjoint")

#: a figure, as the paper's macros take it
Figure = int | float
#: one topic's figures (Kinbank's family counts are nested a level deeper)
Group = dict[str, Figure | dict[str, int]]


def percent(part: int, whole: int) -> float:
    """A percentage rounded to one decimal, as the paper gives it."""
    return round(100 * part / whole, 1) if whole else 0.0


def match_key(form: str) -> str:
    """A form as compared across sources: cleaned as `build.clean`, NFC, casefolded.

    >>> match_key("Opa") == match_key("opa")
    True
    """
    return unicodedata.normalize("NFC", b.clean(form).casefold())


def kindiv_forms() -> list[tuple[str, str, str]]:
    """KinDiv's words as (language, form, concept label), one per form.

    A cell may hold several comma-separated forms (Kannada), as in `build.py`.
    """
    return [
        (row["Language"], form, b.relabel(row["Concept"]))
        for row in b.read_tsv(b.KINDIV / "words")
        for form in map(b.clean, row["Word"].split(","))
        if form
    ]


def kindiv_codes() -> list[str]:
    """KinDiv's concepts, with the two it uses but does not list (restored).

    Upstream KinDiv uses ``Fa;Sb;So`` and ``Fa;Sb;Da`` in `relations` and `gaps`
    but leaves them out of `concepts`; `extra-concepts.tsv` restores them.
    """
    kindiv = [row["Abreviation"] for row in b.read_tsv(b.KINDIV / "concepts")]
    used = {row["Gap concept"] for row in b.read_tsv(b.KINDIV / "gaps")} | {
        code
        for row in b.read_tsv(b.KINDIV / "relations")
        for code in (row["Hyponym_concept"], row["Hypernym_concept"])
    }
    extra = [row["Abreviation"] for row in b.read_tsv(b.DATA / "extra-concepts.tsv")]
    return kindiv + [code for code in extra if code in used]


def concept_facts(concepts: dict[str, b.Concept]) -> dict[str, int]:
    """Where the concepts come from.

    KinDiv's own; the two it uses in `relations` and `gaps` without listing them
    (restored); the nuclear family, in-laws and named nodes we add (from OEWN and
    TUFS); and the ones Kinbank evidence admits, single kin types or mergers.
    """
    kindiv = [row["Abreviation"] for row in b.read_tsv(b.KINDIV / "concepts")]
    restored = kindiv_codes()[len(kindiv) :]
    extra = b.read_tsv(b.DATA / "extra-concepts.tsv")
    kinbank = [row for row in extra if row["Source"].startswith("Kinbank")]
    mergers = [row for row in kinbank if "|" in row["Abreviation"]]
    return {
        "total": len(concepts),
        "kindiv": len(kindiv),
        "restored": len(restored),
        "kindiv_restored": len(kindiv) + len(restored),
        "added": len(extra) - len(restored) - len(kinbank),
        "kinbank": len(kinbank),
        "kinbank_single": len(kinbank) - len(mergers),
        "kinbank_mergers": len(mergers),
    }


def ili_facts(concepts: dict[str, b.Concept]) -> dict[str, int]:
    """Concepts linked to an existing ILI, proposed as new, or unattested.

    ``kindiv_exact`` counts the exact links among KinDiv's concepts and the two
    restored ones (the paper's "16 of the 200").
    """
    status = [b.ili_status(concept) for concept in concepts.values()]
    kindiv = set(kindiv_codes())
    return {
        "linked": status.count("linked"),
        "proposed": status.count("propose"),
        "unattested": status.count("unattested"),
        "kindiv_exact": sum(
            bool(concept.ili) for code, concept in concepts.items() if code in kindiv
        ),
    }


def attestation_facts(concepts: dict[str, b.Concept]) -> dict[str, int]:
    """KinDiv's concepts with no KinDiv word, and how many still have none."""
    by_label = {concept.label: code for code, concept in concepts.items()}
    rows = b.read_tsv(b.KINDIV / "words")
    with_words = {by_label[b.relabel(row["Concept"])] for row in rows}
    kindiv = [row["Abreviation"] for row in b.read_tsv(b.KINDIV / "concepts")]
    unattested = [code for code in kindiv if code not in with_words]
    still = [code for code in unattested if not concepts[code].languages]
    return {
        "kindiv_unattested": len(unattested),
        "still_unattested": len(still),
        "newly_attested": len(unattested) - len(still),
    }


def kindiv_facts() -> dict[str, int]:
    """KinDiv as published: concepts, words and recorded gaps.

    ``words`` are records of `words` (a Manchu word spans several lines of the
    file); ``senses`` are distinct (language, form, concept) triples and
    ``lemmas`` distinct (language, form) pairs, after splitting cells that hold
    several forms. Gaps are distinct (language, concept) pairs, as the file
    repeats some.
    """
    words = b.read_tsv(b.KINDIV / "words")
    forms = kindiv_forms()
    gaps = b.read_tsv(b.KINDIV / "gaps")
    return {
        "concepts": len(b.read_tsv(b.KINDIV / "concepts")),
        "words": len(words),
        "senses": len(set(forms)),
        "lemmas": len({(language, form) for language, form, _ in forms}),
        "word_languages": len({row["Language"] for row in words}),
        "gaps": len({(row["Language"], row["Gap concept"]) for row in gaps}),
        "gap_languages": len({row["Language"] for row in gaps}),
    }


def hierarchy_facts(
    concepts: dict[str, b.Concept], ancestry: dict[str, set[str]]
) -> dict[str, int]:
    """The derived hierarchy.

    ``derived_links`` are the hypernym links the derived hierarchy has that the
    stated one (KinDiv's `relations` with our `extra-relations.tsv`) does not
    imply. ``named_nodes`` are the concepts written as a name rather than a
    chain (``Rel``, ``Unc``, ...), and ``named_disjunctions`` those of them that
    stand for a set of kin types.
    """
    parents = b.nearest(set(concepts), ancestry)
    stated = b.read_relations()
    extent = b.positions(concepts)
    extra = [row["Abreviation"] for row in b.read_tsv(b.DATA / "extra-concepts.tsv")]
    named = [code for code in extra if code.isalpha() and code not in b.NOUNS]
    return {
        "multiple_hypernyms": sum(len(p) > 1 for p in parents.values()),
        "derived_links": sum(
            parent not in b.closure(code, stated)
            for code, found in parents.items()
            for parent in found
        ),
        "named_nodes": len(named),
        "named_disjunctions": sum(code in extent for code in named),
    }


def gap_facts(languages: dict[str, b.Language]) -> dict[str, int]:
    """Words that contradict a KinDiv gap, as listed in `gap-conflicts.tsv`.

    Three units: ``contradicted``, ``sources`` and ``wordnets`` count rows of
    the table (a word, a concept and one of its sources, `build.gap_conflicts`),
    those from an existing wordnet counted apart; ``*_words`` count distinct
    (language, word) pairs and ``*_gaps`` distinct (language, concept) gaps. A
    word or gap with both kinds of source counts under both.
    """
    from_wordnet = {
        row["source"] for row in b.read_tsv(b.CANDIDATES / "wordnet-words.tsv")
    }
    rows = b.gap_conflicts(languages)
    sources = [row for row in rows if row[4] not in from_wordnet]
    wordnets = [row for row in rows if row[4] in from_wordnet]

    def words(found: list[tuple[str, ...]]) -> int:
        return len({(row[0], row[3]) for row in found})

    def gaps(found: list[tuple[str, ...]]) -> int:
        return len({(row[0], row[2]) for row in found})

    return {
        "contradicted": len(rows),
        "words": words(rows),
        "gaps": gaps(rows),
        "languages": len({row[0] for row in rows}),
        "sources": len(sources),
        "source_words": words(sources),
        "source_gaps": gaps(sources),
        "source_languages": len({row[0] for row in sources}),
        "wordnets": len(wordnets),
        "wordnet_words": words(wordnets),
        "wordnet_gaps": gaps(wordnets),
        "wordnet_languages": len({row[0] for row in wordnets}),
        "wordnet_neutral": sum(row[2] in NEUTRAL for row in wordnets),
        "wordnet_neutral_gaps": gaps([row for row in wordnets if row[2] in NEUTRAL]),
    }


def romanization_facts(languages: dict[str, b.Language]) -> dict[str, int]:
    """Kinbank's romanized words, and what became of them in the build.

    The unit is a romanized word: a distinct (language, form) pair among the
    romanized Kinbank matches the build uses (not those flagged with a broader
    synonym). Each became the ``pronunciation`` of a native-script word or
    stayed a ``lemma``, marked as a transcription; ``both`` did each for
    different concepts. ``pronunciations + lemmas - both == words``.
    """
    rows = b.read_tsv(b.CANDIDATES / "kinbank-candidates.tsv")
    used = {
        (row["tag"], b.clean(row["form"]))
        for row in rows
        if row["transcription"] == "romanization" and not row["broader_synonym"]
    }
    pronounced = {
        (language.tag, sound)
        for language in languages.values()
        for sounds in language.pronunciations.values()
        for sound, notation in sounds
        if notation == "romanization"
    }
    lemmas = {
        (language.tag, form)
        for language in languages.values()
        for form in language.transcribed
    }
    return {
        "words": len(used),
        "languages": len({tag for tag, _ in used}),
        "pronunciations": len(pronounced & used),
        "lemmas": len(lemmas & used),
        "both": len(pronounced & lemmas & used),
    }


def agreement(
    extent: dict[str, frozenset],
    kindiv: dict[tuple[str, str], set[str]],
    candidates: list[dict[str, str]],
) -> Counter[str]:
    """How Kinbank's concept for a word compares with the concepts KinDiv gives it.

    `kindiv` maps (language tag, `match_key` of a form) to KinDiv's concepts for
    it; `candidates` are Kinbank matches (`kinbank-candidates.tsv`, flagged or
    not). Each match whose form KinDiv also lists for the language gets one
    verdict (`VERDICTS`), comparing Kinbank's concept with the union of the
    positions of KinDiv's: ``exact``, the same concept; ``equal``, the same
    positions (Maori *tungāne*, a woman's brother, which KinDiv lists under a
    woman's elder and younger brother); ``broader``, Kinbank's strictly contain
    KinDiv's (Danish *datterdatter*, Spanish *hermano* as sibling); ``narrower``;
    ``overlapping``; and ``disjoint``. Only ``exact`` and ``equal`` agree. A
    match whose concept has no positions, and is not KinDiv's, is counted as
    ``no_extent`` and not compared.
    """
    counts: Counter[str] = Counter(dict.fromkeys(VERDICTS + ("no_extent",), 0))
    for row in candidates:
        assigned = kindiv.get((row["tag"], match_key(row["form"])))
        if not assigned:
            continue
        theirs = extent.get(row["concept"])
        if row["concept"] in assigned:
            counts["exact"] += 1
        elif theirs is None:
            counts["no_extent"] += 1
        else:
            ours = frozenset().union(*(extent.get(code, ()) for code in assigned))
            if theirs == ours:
                counts["equal"] += 1
            elif theirs > ours:
                counts["broader"] += 1
            elif theirs < ours:
                counts["narrower"] += 1
            else:
                counts["overlapping" if theirs & ours else "disjoint"] += 1
    return counts


def kinbank_facts(concepts: dict[str, b.Concept]) -> Group:
    """Kinbank figures that need only this repository's tables.

    ``kindiv_*`` compare Kinbank's concepts with KinDiv's for the same words
    (`agreement`): ``kindiv_agree`` is ``kindiv_exact + kindiv_equal`` of
    ``kindiv_compared``, the rest disagree.
    """
    rows = b.read_tsv(b.CANDIDATES / "kinbank-candidates.tsv")
    by_label = {concept.label: code for code, concept in concepts.items()}
    kindiv: dict[tuple[str, str], set[str]] = defaultdict(set)
    for language, form, label in kindiv_forms():
        kindiv[b.LANGUAGE_TAGS[language], match_key(form)].add(by_label[label])
    verdicts = agreement(b.positions(concepts), kindiv, rows)
    compared = sum(verdicts[verdict] for verdict in VERDICTS)
    agreeing = verdicts["exact"] + verdicts["equal"]
    families = {}
    for row in b.read_tsv(b.DATA / "extra-concepts.tsv"):
        if match := KINBANK_SOURCE.match(row["Source"]):
            families[row["Abreviation"]] = int(match.group(2))
    return {
        "kindiv_compared": compared,
        "kindiv_agree": agreeing,
        "kindiv_agree_pct": percent(agreeing, compared),
        "kindiv_disagree": compared - agreeing,
        **{f"kindiv_{verdict}": verdicts[verdict] for verdict in VERDICTS},
        "kindiv_no_extent": verdicts["no_extent"],
        "transcribing_varieties": len(
            {
                row["kinbank_language"]
                for row in rows
                if row["transcription"] in ("IPA", "respelling")
            }
        ),
        "families": {key: families[code] for key, code in FAMILY_EXAMPLES.items()},
    }


def cldf_rows(path: Path) -> list[dict[str, str]]:
    """Read a CLDF CSV table."""
    with path.open(encoding="utf8", newline="") as handle:
        return list(csv.DictReader(handle))


def kinbank_clone_facts(cldf: Path) -> dict[str, int]:
    """Figures read from Kinbank itself: its varieties, and its half siblings.

    ``varieties`` are the rows of its `languages` table (one per wordlist),
    ``glottocodes`` the distinct languoids they belong to.
    ``half_sibling_languages`` fill any half- or step-sibling position;
    ``half_sibling_general_families`` are the families with a single word for
    every half sibling (one form at mhB, mhZ, fhB and fhZ).
    ``unmatched_extensions`` are the distinct meanings of verified terms that
    no concept has and no broader synonym covers (`kinbank_concepts.unmatched`),
    ``unmatched_one_family`` those found in a single language family.
    """
    languages = {row["ID"]: row for row in cldf_rows(cldf / "languages.csv")}
    half: dict[tuple[str, str], set[str]] = defaultdict(set)
    filled = set()
    for row in cldf_rows(cldf / "forms.csv"):
        parameter = row["Parameter_ID"]
        if row["Form"] and (HALF.match(parameter) or STEP.search(parameter)):
            filled.add(row["Language_ID"])
            half[row["Language_ID"], row["Form"]].add(parameter)
    general = {
        languages[language]["Family"]
        for (language, _), found in half.items()
        if ANY_HALF <= found
    }
    families, _, _ = kinbank_concepts.unmatched(cldf)
    one_family = sum(len(found) == 1 for found in families.values())
    return {
        "varieties": len(languages),
        "glottocodes": len(
            {row["Glottocode"] for row in languages.values() if row["Glottocode"]}
        ),
        "half_sibling_languages": len(filled),
        "half_sibling_general_families": len(general),
        "unmatched_extensions": len(families),
        "unmatched_one_family": one_family,
        "unmatched_one_family_pct": percent(one_family, len(families)),
    }


def lexicons_with_gaps(languages: dict[str, b.Language]) -> int:
    """The language lexicons with a gap synset: a gap no word of theirs fills."""
    return sum(
        bool(
            language.gaps.keys()
            - {code for senses in language.words.values() for code, _ in senses}
        )
        for language in languages.values()
    )


def facts(kinbank: Path | None) -> dict[str, Group]:
    """Every figure, grouped by topic; Kinbank's own only if `kinbank` exists.

    ``wordnet_words`` counts the rows of `wordnet-words.tsv` (a word, a concept
    and the wordnet it comes from), ``senses`` its distinct (language, word,
    concept) triples and ``lemmas`` its distinct (language, word) pairs.
    """
    concepts, ancestry, languages = b.pipeline()
    wordnet = b.read_tsv(b.CANDIDATES / "wordnet-words.tsv")
    tufs = b.read_tsv(b.DATA / "tufs-kindiv.tsv")
    kinbank_group = kinbank_facts(concepts)
    cldf = kinbank / "kinbank" / "cldf" if kinbank else None
    if cldf and cldf.is_dir():
        kinbank_group.update(kinbank_clone_facts(cldf))
    elif kinbank:
        logger.warning("no Kinbank clone at %s: its own figures are left out", kinbank)
    else:
        logger.warning("no Kinbank clone given: its own figures are left out")
    return {
        "concepts": concept_facts(concepts),
        "ili": ili_facts(concepts),
        "attestation": attestation_facts(concepts),
        "lexicons": {
            "total": len(languages),
            "with_gaps": lexicons_with_gaps(languages),
        },
        "kindiv": kindiv_facts(),
        "hierarchy": hierarchy_facts(concepts, ancestry),
        "concept_languages": {
            key: len(concepts[code].languages)
            for key, code in LANGUAGE_EXAMPLES.items()
        },
        "gaps": gap_facts(languages),
        "romanizations": romanization_facts(languages),
        "wordnet_words": {
            "words": len(wordnet),
            "senses": len(
                {(row["tag"], b.clean(row["word"]), row["concept"]) for row in wordnet}
            ),
            "lemmas": len({(row["tag"], b.clean(row["word"])) for row in wordnet}),
            "languages": len({row["tag"] for row in wordnet}),
        },
        "kinbank": kinbank_group,
        "tufs": {"languages": len({row["tufs_lang"] for row in tufs})},
        "admission": {
            "min_families": kinbank_concepts.MIN_FAMILIES,
            "min_macroareas": kinbank_concepts.MIN_AREAS,
            "min_families_merger": kinbank_concepts.MIN_FAMILIES_MERGER,
        },
    }


def main() -> None:
    """Write facts.json."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kinbank",
        type=Path,
        default=b.ROOT.parent / "kinbank",
        help="a clone of Kinbank (default: ../kinbank)",
    )
    parser.add_argument("--out", type=Path, default=b.REPORTS / "facts.json")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # the build's own warnings (untranscribed IPA forms) are not figures
    logging.getLogger("build").setLevel(logging.ERROR)
    found = facts(args.kinbank)
    args.out.write_text(json.dumps(found, indent=2) + "\n", encoding="utf8")
    logger.info("wrote %s", args.out)


if __name__ == "__main__":
    main()
