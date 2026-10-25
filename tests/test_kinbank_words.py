"""Tests for kinbank_words.py."""

from kinbank_words import kinbank_atoms, verified_extents
from kintype import kindiv_atoms

HINDI = {
    "cācā": {"fFB", "fFyB", "mFB", "mFyB"},
    "tāū": {"fFB", "fFeB", "mFB", "mFeB"},
    "māmā": {"fMB", "mMB"},
    "buā": {"fFZ", "mFZ"},
    "mausī": {"fMZ", "mMZ"},
}


def extents(words: dict[str, set[str]]) -> dict[str, frozenset]:
    return {form: atoms for form, atoms, _ in verified_extents(words)}


def test_refined_position_with_several_words_is_alternatives() -> None:
    """Hindi cācā and tāū both fill fFB, so fFB lists alternatives (issue #2)."""
    found = extents(HINDI)
    assert found["cācā"] == frozenset(kindiv_atoms("Fa;Yn;Br", "uncles and aunts"))
    assert found["tāū"] == frozenset(kindiv_atoms("Fa;El;Br", "uncles and aunts"))
    assert found["māmā"] == frozenset(kindiv_atoms("Mo;Br", "uncles and aunts"))


def test_single_word_in_refined_position_stays_broad() -> None:
    """One word in fFB and in both of its refinements is the broad term."""
    words = dict(HINDI, cācā={"fFB", "fFyB", "fFeB", "mFB", "mFyB", "mFeB"})
    del words["tāū"]
    assert extents(words)["cācā"] == frozenset(
        kinbank_atoms("fFB") | kinbank_atoms("mFB")
    )


def test_synonyms_in_a_refined_position_stay_broad() -> None:
    """Hungarian fivér and fiútestvér fill fB and feB alike: synonyms, not alternatives."""
    words = {
        "fivér": {"fB", "feB", "mB", "meB"},
        "fiútestvér": {"fB", "feB", "mB", "meB"},
        "öcs": {"fyB", "myB"},
        "nővér": {"fZ", "mZ"},
    }
    assert extents(words)["fivér"] == frozenset(
        kinbank_atoms("fB") | kinbank_atoms("mB")
    )


def test_word_without_refinements_does_not_split() -> None:
    """Bengali bon (fZ, fyZ) beside bona (fZ only) is still a sister, not younger."""
    words = {
        "bon": {"fZ", "fyZ", "mZ", "myZ"},
        "bona": {"fZ", "mZ"},
        "dādā": {"feB", "meB"},
        "bhāi": {"fB", "mB"},
    }
    assert extents(words)["bon"] == frozenset(kinbank_atoms("fZ") | kinbank_atoms("mZ"))
