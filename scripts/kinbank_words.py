#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["langcodes", "language_data", "unidecode"]
# ///
"""Find Kinbank terms that lexicalize KinDiv concepts exactly.

Kinbank (Passmore et al. 2023, CC BY 4.0) records, for each language, the term
used at each genealogical position: ``mFeB`` is a man's father's older brother.
A term's meaning is the set of positions it is listed under, and a KinDiv concept
is a set of positions too, so the two can be compared directly.

Positions are reduced to *atoms*: ego sex, a chain of kin letters
(F M B Z S D H W), and relative age only where KinDiv distinguishes it (ego's
sibling, a parent's sibling, the sibling whose child is meant, a cousin relative
to ego, the brother or sister in FBW/FZH). Coarse positions expand: ``mB`` is both
``meB`` and ``myB``, ``mC`` is ``mS`` and ``mD``.

A term matches a concept **exactly** when its atoms equal the concept's atoms, it
is listed under no position outside the atom space, and the language was asked
about every *neighbouring* atom (flip ego sex, the sex or side of any link, or the
relative age) -- so we know the term does not extend there. Without that check, a
language recorded for male ego only would seem to have "male anchor" terms
everywhere.

Writes ``kinbank-candidates.tsv``.

Usage: uv run scripts/kinbank_words.py [path/to/kinbank]
"""

from __future__ import annotations

import csv
import logging
import re
import sys
import unicodedata
from collections import defaultdict
from functools import cache
from pathlib import Path

import build
import langcodes
from kintype import (  # noqa: F401  (kinbank_concepts uses them through this module)
    CONCRETE,
    DISJUNCTIONS,
    FLIP,
    Atom,
    age_slot,
    expand,
    kindiv_atoms,
)

logger = logging.getLogger(__name__)

GENERAL = re.compile(r"[CPEG]")
KINBANK = re.compile(r"([mf])((?:[ey]?[A-Z])+)")


def kinbank_atoms(parameter: str) -> set[Atom] | None:
    """Atoms of a Kinbank position, or None if it lies outside the atom space.

    >>> sorted(kinbank_atoms("mB"))
    [('m', (('e', 'B'),)), ('m', (('y', 'B'),))]
    >>> kinbank_atoms("mFeBS") == kinbank_atoms("mFBS")   # parent's age is not kept
    True
    >>> kinbank_atoms("mA") is None
    True
    >>> kinbank_atoms("mG") == kinbank_atoms("mB") | kinbank_atoms("mZ")
    True
    """
    match = KINBANK.fullmatch(parameter)
    if not match:
        return None
    ego, body = match.groups()
    links = re.findall(r"([ey]?)([A-Z])", body)
    # G is a sibling: parameters.csv calls mG "Grandparent", but the forms under it
    # are English "sibling", Swedish "syskon", Hungarian "testvér"
    if any(letter not in CONCRETE and letter not in "CPEG" for _, letter in links):
        return None
    atoms = expand(ego, links)
    return {atom for atom in atoms if atom[1]}


def neighbours(atom: Atom) -> set[Atom]:
    """Atoms one step away: flip ego sex, one link's sex or side, or the age."""
    ego, links = atom
    found = {({"m": "f", "f": "m"}[ego], links)}
    for i, (age, letter) in enumerate(links):
        flipped = list(links)
        flipped[i] = (age, FLIP[letter])
        if age_slot("".join(l for _, l in flipped)) == age_slot(
            "".join(l for _, l in links)
        ):
            found.add((ego, tuple(flipped)))
        if age:
            flipped = list(links)
            flipped[i] = ({"e": "y", "y": "e"}[age], letter)
            found.add((ego, tuple(flipped)))
    return found


def word_atoms(parameters: set[str]) -> frozenset[Atom] | None:
    """Atoms of all the positions a term is listed under, or None if any is unmappable."""
    atom_sets = [kinbank_atoms(p) for p in parameters]
    if any(a is None for a in atom_sets):
        return None
    return frozenset(set().union(*atom_sets))


def broader_synonym(
    form: str,
    atoms: frozenset[Atom],
    outside: set[Atom],
    extent: dict[str, frozenset[Atom] | None],
) -> str:
    """Name another term that covers `form`'s positions and a neighbour it lacks.

    Kinbank often records one term per position, so German *Opa* appears only
    under MF because FF got *Großvater*. When a broader term like *Großvater*
    spans both, `form`'s absence from the neighbour is weak evidence, and the
    match is flagged.
    """
    for other, other_atoms in extent.items():
        if (
            other != form
            and other_atoms
            and atoms < other_atoms
            and other_atoms & outside
        ):
            return other
    return ""


#: Kinbank varieties that transcribe a language written in Latin script: English
#: and German in IPA or dictionary respelling
TRANSCRIBED = {"p_englishstan1293", "p_germanstan1295"}
#: characters of dictionary respelling (Webster's *ŭngʹkəl*), not IPA
RESPELLING = set("ĭŭăĕŏʹ'")


#: languages whose likely script in CLDR is not what their texts use: Old Norse
#: and Old Irish are edited in Latin letters, not runes or ogham
LATIN_WRITTEN = {"non", "sga"}


@cache
def likely_script(tag: str) -> str:
    """The script a language is usually written in (ISO 15924), or ''."""
    if tag in LATIN_WRITTEN:
        return "Latn"
    try:
        return langcodes.Language.get(tag).maximize().script or ""
    except (ValueError, LookupError):
        return ""


def transcription(form: str, tag: str, variety: str) -> str:
    """How a Kinbank form transcribes the language, or '' if it is written normally.

    ``IPA`` or ``respelling`` for the transcribing English and German varieties;
    ``romanization`` for a Latin-letter form of a language usually written in
    another script (Mandarin *xiong di*, Hindi *bhāī*, Russian *brat*).

    >>> transcription("xiong di", "cmn", "v_mandarinchinamand1415")
    'romanization'
    >>> transcription("брат", "ru", "p_russianruss1263a")
    ''
    >>> transcription("brat", "pl", "v_polishpoli1260")
    ''
    """
    if variety in TRANSCRIBED:
        return "respelling" if RESPELLING & set(form) else "IPA"
    script = likely_script(tag)
    latin = any(
        ch.isalpha() and unicodedata.name(ch, "").startswith("LATIN") for ch in form
    )
    return "romanization" if latin and script not in ("", "Latn") else ""


def iso_to_tag(iso: str) -> str:
    """Our tag for an ISO 639-3 code: the one languages.tsv uses, if any.

    >>> iso_to_tag("cmn"), iso_to_tag("hbs"), iso_to_tag("eng"), iso_to_tag("taf")
    ('cmn', 'sh', 'en', 'taf')
    """
    return OUR_TAGS.get(iso) or langcodes.standardize_tag(iso)


#: Kinbank's individual-language codes whose macrolanguage we already tag
MACRO = {
    "tgl": "tl",  # langcodes would make this fil
    "hbs": "sh",
    "pes": "fa",
    "arb": "ar",
    "zsm": "ms",
    "swh": "sw",
    "ekk": "et",
    "lvs": "lv",
    "als": "sq",
    "khk": "mn",
    "azj": "az",
    "ydd": "yi",
    "kmr": "ku",
}

#: ISO 639-3 -> the tag languages.tsv already uses for that language
OUR_TAGS = {
    langcodes.get(tag).to_alpha3(): tag for tag in build.LANGUAGE_TAGS.values()
} | MACRO


def read_kinbank(
    cldf: Path,
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, set[str]]]]:
    """Return Kinbank's languages by id, and each language's forms with positions."""
    languages = {row["ID"]: row for row in build_rows(cldf / "languages.csv")}
    forms: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in build_rows(cldf / "forms.csv"):
        if row["Form"]:
            forms[row["Language_ID"]][row["Form"]].add(row["Parameter_ID"])
    return languages, forms


def verified_extents(
    words: dict[str, set[str]],
) -> list[tuple[str, frozenset[Atom], str]]:
    """Return (form, atoms, broader synonym) for one language's verifiable terms.

    A term is verifiable when it names only mappable positions and the language
    was asked about every neighbouring atom, so its boundaries are known.
    """
    elicited: set[Atom] = set()
    filled: dict[str, int] = defaultdict(int)
    for parameters in words.values():
        for parameter in parameters:
            elicited |= kinbank_atoms(parameter) or set()
            filled[parameter] += 1
    # a general position filled with several words records alternatives, not one
    # broad term: a sibling, child, parent or spouse ("hermano/hermana"), or a
    # position that two of its words split between disjoint refinements (Hindi
    # cācā and tāū under fFB, where fFyB has cācā and fFeB tāū); words whose
    # refinements overlap or are missing are synonyms (Hungarian fivér and
    # fiútestvér, both under fB and feB; Bengali bon beside bona)
    atoms_of = {p: kinbank_atoms(p) for p in filled}

    def refinements(form: str, position: str) -> frozenset[str]:
        atoms = atoms_of[position]
        return frozenset(
            q for q in words[form] if atoms and atoms_of[q] and atoms_of[q] < atoms
        )

    def is_split(position: str) -> bool:
        parts = {refinements(f, position) for f, ps in words.items() if position in ps}
        parts.discard(frozenset())
        return any(a.isdisjoint(b) for a in parts for b in parts if a != b)

    split = {p for p in filled if is_split(p)}
    alternatives = {
        p for p, n in filled.items() if n > 1 and (GENERAL.search(p[1:]) or p in split)
    }
    extent = {
        form: word_atoms(parameters - alternatives or parameters)
        for form, parameters in words.items()
    }
    found = []
    for form, atoms in extent.items():
        if atoms is None:
            continue  # also names a kin type outside the atom space
        outside = {n for a in atoms for n in neighbours(a)} - atoms
        if outside <= elicited:
            found.append((form, atoms, broader_synonym(form, atoms, outside, extent)))
    return found


def main() -> None:
    """Write kinbank-candidates.tsv."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root = Path(sys.argv[1] if len(sys.argv) > 1 else build.ROOT.parent / "kinbank")
    cldf = root / "kinbank" / "cldf"
    concepts = build.read_concepts()
    by_atoms: dict[frozenset[Atom], list[str]] = defaultdict(list)
    for code, concept in concepts.items():
        atoms = kindiv_atoms(code, concept.subdomain)
        if atoms:
            by_atoms[frozenset(atoms)].append(code)

    languages, forms = read_kinbank(cldf)
    rows = []
    skipped_no_iso = 0
    for language_id, words in forms.items():
        language = languages[language_id]
        if not language["ISO639P3code"]:
            skipped_no_iso += 1
            continue
        for form, atoms, broader in verified_extents(words):
            tag = iso_to_tag(language["ISO639P3code"])
            for code in by_atoms.get(atoms, []):
                rows.append(
                    (
                        code,
                        tag,
                        language["ISO639P3code"],
                        language["Glottolog_Name"] or language["Name"],
                        form,
                        language_id,
                        ";".join(sorted(words[form])),
                        broader,
                        transcription(form, tag, language_id),
                    )
                )
    with (build.CANDIDATES / "kinbank-candidates.tsv").open(
        "w", encoding="utf8"
    ) as out:
        out.write(
            "concept\ttag\tiso639_3\tlanguage\tform\tkinbank_language\tpositions"
            "\tbroader_synonym\ttranscription\n"
        )
        for row in sorted(rows):
            out.write("\t".join(row) + "\n")
    logger.info(
        "%d exact matches in %d Kinbank languages (%d languages skipped: no ISO code)",
        len(rows),
        len({r[5] for r in rows}),
        skipped_no_iso,
    )


def build_rows(path: Path) -> list[dict[str, str]]:
    """Read a CLDF CSV table."""
    with path.open(encoding="utf8", newline="") as handle:
        return list(csv.DictReader(handle))


if __name__ == "__main__":
    main()
