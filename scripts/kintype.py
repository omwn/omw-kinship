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
    """Return the index of the link whose relative age can be distinguished.

    The age is compared with the nearest earlier person on the path of the same
    generation: a sibling with the anchor (``B``), a parent's sibling with the
    parent (``FB``), a cousin with the anchor (``FBS``), a spouse's sibling with
    the spouse (``HB``), and a sibling's spouse by the sibling's age (``ZH``).

    >>> age_slot("B"), age_slot("FB"), age_slot("BS"), age_slot("FBS"), age_slot("FBW")
    (0, 1, 0, 2, 1)
    >>> age_slot("HB"), age_slot("ZH")
    (1, 0)
    >>> age_slot("FF") is None
    True
    """
    parent, sibling, child, spouse = set("FM"), set("BZ"), set("SD"), set("HW")
    sets = [parent, sibling, child, spouse]
    shape = tuple(next(i for i, s in enumerate(sets) if c in s) for c in letters)
    return {
        (1,): 0,
        (0, 1): 1,
        (1, 2): 0,
        (0, 1, 2): 2,
        (0, 1, 3): 1,
        (3, 1): 1,
        (1, 3): 0,
    }.get(shape)


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

    >>> subdomain_of("Hu;Fa"), subdomain_of("x;Ss;Da"), subdomain_of("Fa;Br;El:So")
    ('in-laws', 'nephews and nieces', 'cousins')
    >>> subdomain_of("Fa|Fa;Br")
    'mergers'
    """
    if "|" in code:
        parts = {subdomain_of(part) for part in code.split("|")}
        return parts.pop() if len(parts) == 1 else "mergers"
    terms = [t.split(":")[-1] for t in code.split(";") if t not in ("x", "o", "Pl")]
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


#: relative-age modifiers, written before a term with ``:``
AGES = {"El": "e", "Yn": "y"}
#: terms that start a path upward, which never carry a relative age
PARENTS = {"Fa", "Mo", "Pa", "Pb"}


def from_kindiv(code: str) -> str:
    """Rewrite a code in KinDiv's notation in ours.

    KinDiv writes a relative age as a term of its own before the term it
    modifies (``Fa;El;Br``), except for a cousin, whose age goes at the front
    (``El;Fa;Br;So``). We attach the age to the link it describes with ``:``, so
    ``;`` only separates links.

    >>> from_kindiv("x;Fa;El;Br"), from_kindiv("El;Fa;Br;So"), from_kindiv("x;El;Br;Ch")
    ('x;Fa;El:Br', 'Fa;Br;El:So', 'x;El:Br;Ch')
    >>> from_kindiv("Fa|Fa;El;Br"), from_kindiv("Pa;Sb;Ch")
    ('Fa|Fa;El:Br', 'Pa;Sb;Ch')
    """
    if "|" in code:
        return "|".join(from_kindiv(part) for part in code.split("|"))
    out: list[str] = []
    pending, cousin = "", ""
    for part in code.split(";"):
        if part in AGES:
            pending = part
        elif pending and part in PARENTS:  # a cousin's age: it goes on the cousin
            cousin, pending = pending, ""
            out.append(part)
        else:
            out.append(f"{pending}:{part}" if pending else part)
            pending = ""
    if cousin:
        out[-1] = f"{cousin}:{out[-1]}"
    return ";".join(out)


#: marks the anchor of a plural code's atoms
PLURAL = "pl-"


def is_plural(atoms: set[Atom] | frozenset[Atom]) -> bool:
    """True if `atoms` are a plural code's (`PLURAL` on the anchor)."""
    return any(ego.startswith(PLURAL) for ego, _ in atoms)


def kindiv_atoms(code: str) -> set[Atom] | None:
    """Atoms of a concept's code, or None for nodes too broad to match (Rel, InL).

    A relative age (``El:``, ``Yn:``) is allowed only on the link `age_slot`
    names; anywhere else the code is an error.

    ``Pl;`` (after any anchor) makes a code plural: the relatives it covers,
    taken together (Japanese 両親 *ryōshin* "both parents" is ``Pl;Pa``). A
    code without it is unspecified for number. A plural code's atoms are marked
    on the anchor (`PLURAL`), and `build.read_hierarchy` puts it below the
    unspecified codes that cover its members.

    >>> sorted(kindiv_atoms("x;Fa;El:Br"))
    [('m', (('', 'F'), ('e', 'B')))]
    >>> len(kindiv_atoms("Pa;Sb;Ch"))   # 2 egos x 8 kin types x 2 ages
    32
    >>> sorted(kindiv_atoms("x;Hu;El:Br")) == sorted(kindiv_atoms("x;Hu;Br"))[:1]
    True
    >>> sorted(kindiv_atoms("Pl;Pa"))[0], kindiv_atoms("Pl;Pa") & kindiv_atoms("Pa")
    (('pl-f', (('', 'F'),)), set())
    """
    if "|" in code:
        parts = [kindiv_atoms(part) for part in code.split("|")]
        return None if None in parts else set().union(*parts)
    if code in UNIONS:
        return set().union(*(kindiv_atoms(part) for part in UNIONS[code]))
    parts = code.split(";")
    egos = {"x": "m", "o": "f"}.get(parts[0], "mf")
    if parts[0] in ("x", "o"):
        parts = parts[1:]
    plural = parts[0] == "Pl"
    if plural:
        parts = parts[1:]
    links: list[tuple[str, str]] = []
    for part in parts:
        *modifiers, term = part.split(":")
        if any(m not in AGES for m in modifiers) or len(modifiers) > 1:
            raise ValueError(f"{code}: unknown modifier in {part}")
        age = AGES[modifiers[0]] if modifiers else ""
        if term == "Pb" and not age:
            links.extend([("", "P"), ("", "Q")])
        elif term in KINDIV_LETTERS:
            links.append((age, KINDIV_LETTERS[term]))
        else:
            return None
    concrete = "".join(letter for _, letter in links)
    slot = age_slot(concrete.translate(str.maketrans("PQCE", "FBSH")))
    for i, (age, letter) in enumerate(links):
        if age and i != slot:
            raise ValueError(f"{code}: no relative age on link {i + 1} ({letter})")
    atoms = expand(egos, links)
    return {(PLURAL + ego, path) for ego, path in atoms} if plural else atoms
