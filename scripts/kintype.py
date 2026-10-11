"""The kin-type code algebra: the genealogical positions a code denotes.

A position (an *atom*) is the anchor's sex and a path of elementary links outward
from the anchor, at most one of them carrying a relative age. A code denotes a set
of positions, and one concept is a hypernym of another when its set contains the
other's. See FEATURES.md.
"""

from __future__ import annotations

import itertools

#: an atom: (ego sex, ((age, letter), ...)), age "" where not distinguished
Atom = tuple[str, tuple[tuple[str, str], ...]]

#: Kinbank letters that stand for a choice of concrete kin letters
DISJUNCTIONS = {"C": "SD", "P": "FM", "E": "HW", "G": "BZ", "Q": "BZ"}
CONCRETE = set("FMBZSDHW")
FLIP = {"F": "M", "M": "F", "B": "Z", "Z": "B", "S": "D", "D": "S", "H": "W", "W": "H"}


def age_slot(letters: str) -> int | None:
    """Return the index of the link whose relative age KinDiv distinguishes.

    >>> age_slot("B"), age_slot("FB"), age_slot("BS"), age_slot("FBS"), age_slot("FBW")
    (0, 1, 0, 2, 1)
    >>> age_slot("FF") is None
    True
    """
    parent, sibling, child, spouse = set("FM"), set("BZ"), set("SD"), set("HW")
    sets = [parent, sibling, child, spouse]
    shape = tuple(next(i for i, s in enumerate(sets) if c in s) for c in letters)
    return {(1,): 0, (0, 1): 1, (1, 2): 0, (0, 1, 2): 2, (0, 1, 3): 1}.get(shape)


def expand(egos: str, links: list[tuple[str, str]]) -> set[Atom]:
    """Expand ego sexes, disjunctive letters and unspecified ages into atoms."""
    atoms: set[Atom] = set()
    choices = [DISJUNCTIONS.get(letter, letter) for _, letter in links]
    for ego in egos:
        for letters in itertools.product(*choices):
            slot = age_slot("".join(letters))
            ages = [""] * len(letters)
            if slot is not None:
                given = links[slot][0]
                for age in (given,) if given else ("e", "y"):
                    ages[slot] = age
                    atoms.add((ego, tuple(zip(ages, letters))))
            else:
                atoms.add((ego, tuple(zip(ages, letters))))
    return atoms


def subdomain_of(code: str) -> str:
    """Guess a kin type's subdomain from its shape (for concepts outside KinDiv).

    >>> subdomain_of("Hu;Fa"), subdomain_of("x;Ss;Da"), subdomain_of("El;Fa;Br;So")
    ('in-laws', 'nephews and nieces', 'cousins')
    >>> subdomain_of("Fa|Fa;Br")
    'mergers'
    """
    if "|" in code:
        parts = {subdomain_of(part) for part in code.split("|")}
        return parts.pop() if len(parts) == 1 else "mergers"
    terms = [t for t in code.split(";") if t not in ("x", "o", "El", "Yn")]
    if any(t in ("Hu", "Wi", "Sp") for t in terms):
        return "spouses" if len(terms) == 1 else "in-laws"
    role = "".join(
        "P" if t in ("Fa", "Mo", "Pa") else "S" if t in ("Br", "Ss", "Sb") else "C"
        for t in terms
    )
    return {
        "P": "parents",
        "S": "siblings",
        "C": "children",
        "PP": "grandparents",
        "CC": "grandchildren",
        "PS": "uncles and aunts",
        "SC": "nephews and nieces",
        "PSC": "cousins",
    }.get(role, "relatives")


#: KinDiv kin terms as Kinbank letters (Q: sibling)
KINDIV_LETTERS = {
    "Fa": "F",
    "Mo": "M",
    "Pa": "P",
    "Pr": "P",
    "Br": "B",
    "Ss": "Z",
    "Sb": "Q",
    "So": "S",
    "Da": "D",
    "Ch": "C",
    "Hu": "H",
    "Wi": "W",
    "Sp": "E",
}
#: KinDiv nodes that are unions of kin types
UNIONS = {
    "Unc": ("Pa;Br", "Pa;Ss;Hu"),
    "Aun": ("Pa;Ss", "Pa;Br;Wi"),
    "BrL": ("Sp;Br", "Ss;Hu"),
    "SsL": ("Sp;Ss", "Br;Wi"),
}


def kindiv_atoms(code: str, subdomain: str) -> set[Atom] | None:
    """Atoms of a KinDiv concept, or None for nodes too broad to match (Rel, InL).

    >>> sorted(kindiv_atoms("x;Fa;El;Br", "uncles and aunts"))
    [('m', (('', 'F'), ('e', 'B')))]
    >>> len(kindiv_atoms("Pa;Sb;Ch", "cousins"))   # 2 egos x 8 kin types x 2 ages
    32
    """
    if "|" in code:
        parts = [kindiv_atoms(part, subdomain_of(part)) for part in code.split("|")]
        return None if None in parts else set().union(*parts)
    if code in UNIONS:
        return set().union(*(kindiv_atoms(part, subdomain) for part in UNIONS[code]))
    parts = code.split(";")
    egos = {"x": "m", "o": "f"}.get(parts[0], "mf")
    if parts[0] in ("x", "o"):
        parts = parts[1:]
    links: list[list[str]] = []
    age = ""
    for part in parts:
        if part in ("El", "Yn"):
            age = "e" if part == "El" else "y"
            continue
        if part == "Gr":
            letter = "C" if subdomain == "grandchildren" else "P"
            links.append(["", letter])
        elif part == "Pb":
            links.extend([["", "P"], ["", "Q"]])
        elif part in KINDIV_LETTERS:
            links.append(["", KINDIV_LETTERS[part]])
        else:
            return None
        if age and subdomain != "cousins":
            links[-1][0], age = age, ""
    if age:  # cousins: the age is the cousin's, relative to ego
        links[-1][0] = age
    return expand(egos, [tuple(link) for link in links])
