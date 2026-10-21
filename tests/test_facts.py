"""Tests that the figures facts.py computes are consistent with each other.

Run with:
uv run --with pytest --with langcodes --with language_data --with unidecode pytest tests
"""

from __future__ import annotations

import json

import facts
import pytest

import build


@pytest.fixture(scope="module")
def found() -> dict:
    """The figures, without the ones that need a Kinbank clone."""
    return facts.facts(None)


def test_ili_status_covers_every_concept(found: dict) -> None:
    """Each concept is linked, proposed or unattested."""
    ili = found["ili"]
    total = found["concepts"]["total"]
    assert ili["linked"] + ili["proposed"] + ili["unattested"] == total


def test_concept_sources_add_up(found: dict) -> None:
    """KinDiv's concepts, ours and Kinbank's make up the whole."""
    c = found["concepts"]
    assert c["kindiv_restored"] + c["added"] + c["kinbank"] == c["total"]
    assert c["kinbank_single"] + c["kinbank_mergers"] == c["kinbank"]


def test_unattested_concepts_are_kindivs(found: dict) -> None:
    """The unattested concepts are KinDiv's, all anchor-sex variants."""
    assert found["attestation"]["still_unattested"] == found["ili"]["unattested"]
    unattested = [
        row["concept"]
        for row in build.read_tsv(build.REPORTS / "ili-proposals.tsv")
        if row["status"] == "unattested"
    ]
    assert all(code.startswith(("x;", "o;")) for code in unattested)


def test_gap_conflicts_match_report(found: dict) -> None:
    """The gap figures split the rows of gap-conflicts.tsv by source."""
    gaps = found["gaps"]
    assert gaps["sources"] + gaps["wordnets"] == gaps["contradicted"]
    rows = build.read_tsv(build.REPORTS / "gap-conflicts.tsv")
    assert gaps["contradicted"] == len(rows)
    assert gaps["languages"] == len({row["language"] for row in rows})


def test_romanized_words_add_up(found: dict) -> None:
    """Each romanized word became a pronunciation or stayed a lemma."""
    r = found["romanizations"]
    assert r["pronunciations"] + r["lemmas"] - r["both"] == r["words"]


def test_kinbank_verdicts_add_up(found: dict) -> None:
    """Agreements and disagreements make up the comparisons."""
    k = found["kinbank"]
    assert k["kindiv_exact"] + k["kindiv_equal"] == k["kindiv_agree"]
    assert k["kindiv_agree"] + k["kindiv_disagree"] == k["kindiv_compared"]
    disagree = ("broader", "narrower", "overlapping", "disjoint")
    assert sum(k[f"kindiv_{verdict}"] for verdict in disagree) == k["kindiv_disagree"]


#: positions for a toy grid: a woman's elder and younger brother, and more
EXTENT = {
    "o;El;Br": frozenset({"oeB"}),
    "o;Yn;Br": frozenset({"oyB"}),
    "o;Br": frozenset({"oeB", "oyB"}),
    "Da;Da": frozenset({"DD"}),
    "Gr;Da": frozenset({"DD", "SD"}),
    "Mo": frozenset({"M"}),
}


def verdict(kindiv: dict, form: str, concept: str) -> dict:
    """The non-zero verdicts for one Kinbank match in a Maori-like language."""
    rows = [{"tag": "mi", "form": form, "concept": concept}]
    counts = facts.agreement(EXTENT, kindiv, rows)
    return {key: value for key, value in counts.items() if value}


def test_same_concept_agrees() -> None:
    kindiv = {("mi", "tungāne"): {"o;Br"}}
    assert verdict(kindiv, "tungāne", "o;Br") == {"exact": 1}


def test_equal_extent_agrees() -> None:
    """Maori tungāne: KinDiv's elder and younger brother, Kinbank's brother."""
    kindiv = {("mi", "tungāne"): {"o;El;Br", "o;Yn;Br"}}
    assert verdict(kindiv, "tungāne", "o;Br") == {"equal": 1}


def test_broader_disagrees() -> None:
    """Danish datterdatter: KinDiv's daughter's daughter, Kinbank's granddaughter."""
    kindiv = {("mi", "datterdatter"): {"Da;Da"}}
    assert verdict(kindiv, "datterdatter", "Gr;Da") == {"broader": 1}


def test_narrower_and_disjoint_disagree() -> None:
    kindiv = {("mi", "x"): {"Gr;Da"}, ("mi", "y"): {"Mo"}}
    assert verdict(kindiv, "x", "Da;Da") == {"narrower": 1}
    assert verdict(kindiv, "y", "o;Br") == {"disjoint": 1}


def test_concept_without_extent_is_skipped() -> None:
    kindiv = {("mi", "x"): {"Mo"}}
    assert verdict(kindiv, "x", "Rel") == {"no_extent": 1}


def test_forms_match_after_nfc_and_casefold() -> None:
    """Decomposed tungāne and capitalized Opa find KinDiv's forms."""
    kindiv = {
        ("mi", facts.match_key("tung\u0101ne")): {"o;Br"},
        ("mi", facts.match_key("Opa")): {"Mo"},
    }
    assert verdict(kindiv, "tunga\u0304ne", "o;Br") == {"exact": 1}
    assert verdict(kindiv, "opa", "Mo") == {"exact": 1}


def test_committed_facts_are_current() -> None:
    """reports/facts.json is what facts.py computes now."""
    kinbank = build.ROOT.parent / "kinbank"
    if not (kinbank / "kinbank" / "cldf").is_dir():
        pytest.skip("no Kinbank clone: its own figures cannot be computed")
    committed = json.loads((build.REPORTS / "facts.json").read_text(encoding="utf8"))
    assert facts.facts(kinbank) == committed


def test_lexicons_match_report(found: dict) -> None:
    """One language lexicon per row of lexicons.tsv."""
    rows = build.read_tsv(build.REPORTS / "lexicons.tsv")
    assert found["lexicons"]["total"] == len(rows)
    assert found["lexicons"]["with_gaps"] == sum(int(row["gaps"]) > 0 for row in rows)


def test_leaves_are_numbers(found: dict) -> None:
    """Every leaf is an int or a float, for the paper's macros."""

    def leaves(node: object) -> list[object]:
        if isinstance(node, dict):
            return [leaf for value in node.values() for leaf in leaves(value)]
        return [node]

    assert all(
        isinstance(leaf, (int, float)) and not isinstance(leaf, bool)
        for leaf in leaves(found)
    )
