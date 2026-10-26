#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["langcodes", "language_data", "rdflib", "unidecode"]
# ///
"""Align Wikidata kinship items with our concepts through their SPARQL paths.

About 200 Wikidata kinship items have property P4316, "kinship equivalent in
SPARQL": a graph pattern from ``?person`` to ``?relative`` (*father's brother* is
``?person wdt:P22/wdt:P3373 ?relative . ?relative wdt:P21 wd:Q6581097``). Run
over a family whose members are labelled with their genealogical positions, a
pattern gives the set of positions the item covers, which can be compared with
each concept's (FEATURES.md).

The family is built twice, around a male and a female ego. It has ego's
grandparents, parents, parents' elder and younger siblings with their spouses
and children (cousins older and younger than ego), ego's elder and younger
siblings with their spouses and children, ego's spouses with their parents and
siblings, and ego's children with their spouses and children. Every married
person has both a husband and a wife, since our spouse codes (``Sp``, ``Hu``,
``Wi``) do not fix the sex of the person married; children are born to the
opposite-sex couple. Everyone has a birth date, so age filters work.

``--fetch`` downloads the items to ``data/candidates/wikidata-p4316.tsv``; without
it the saved copy is used. Writes ``data/candidates/wikidata-candidates.tsv``,
the input to the hand-curated ``data/concept-wikidata.tsv``.

Usage: uv run scripts/wikidata_concepts.py [--fetch]
"""

from __future__ import annotations

import csv
import logging
import sys
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field

import build
from kinbank_words import kinbank_atoms
from kintype import Atom
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import XSD

logger = logging.getLogger(__name__)

WD = Namespace("http://www.wikidata.org/entity/")
WDT = Namespace("http://www.wikidata.org/prop/direct/")
MALE, FEMALE = WD.Q6581097, WD.Q6581072
#: the sex each Kinbank letter implies
SEX = {"F": "m", "M": "f", "B": "m", "Z": "f", "S": "m", "D": "f", "H": "m", "W": "f"}
ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "omw-kinship/0.2 (https://github.com/omwn/omw-kinship)"
ITEMS_QUERY = """
SELECT ?item ?label ?path ?ili ?concepticon WHERE {
  ?item wdt:P4316 ?path .
  OPTIONAL { ?item wdt:P5063 ?ili }
  OPTIONAL { ?item wdt:P11473 ?concepticon }
  OPTIONAL { ?item rdfs:label ?label FILTER(LANG(?label) = "en") }
}
"""
PREFIXES = (
    "PREFIX wd: <http://www.wikidata.org/entity/> "
    "PREFIX wdt: <http://www.wikidata.org/prop/direct/> "
)
ITEMS = build.CANDIDATES / "wikidata-p4316.tsv"
OUTPUT = build.CANDIDATES / "wikidata-candidates.tsv"


@dataclass
class Family:
    """A synthetic family as RDF, each person labelled with a Kinbank position."""

    ego_sex: str
    graph: Graph = field(default_factory=Graph)
    label: dict[URIRef, str] = field(default_factory=dict)

    def person(self, label: str, sex: str, year: int) -> URIRef:
        """Add a person at position `label` (``""`` for ego), born in `year`."""
        node = URIRef(f"urn:{self.ego_sex}:{len(self.label)}")
        self.label[node] = label
        self.graph.add((node, WDT.P21, MALE if sex == "m" else FEMALE))
        born = Literal(f"{year}-01-01T00:00:00Z", datatype=XSD.dateTime)
        self.graph.add((node, WDT.P569, born))
        return node

    def marry(self, a: URIRef, b: URIRef) -> None:
        """Make `a` and `b` spouses."""
        self.graph.add((a, WDT.P26, b))
        self.graph.add((b, WDT.P26, a))

    def wed(self, person: URIRef, label: str, sex: str, year: int) -> URIRef:
        """Give `person` a husband and a wife; return the opposite-sex spouse."""
        spouses = {}
        for letter in "HW":
            spouse = self.person(label + letter, SEX[letter], year)
            self.marry(person, spouse)
            spouses[SEX[letter]] = spouse
        return spouses["f" if sex == "m" else "m"]

    def couple(self, label: str, year: int) -> tuple[URIRef, URIRef]:
        """Add a married father and mother at `label` + ``F``/``M``."""
        father = self.person(label + "F", "m", year)
        mother = self.person(label + "M", "f", year)
        self.marry(father, mother)
        return father, mother

    def children(self, father: URIRef, mother: URIRef, kids: list[URIRef]) -> None:
        """Make `kids` the children of `father` and `mother`, and siblings."""
        for kid in kids:
            for parent, prop in ((father, WDT.P22), (mother, WDT.P25)):
                self.graph.add((kid, prop, parent))
                self.graph.add((parent, WDT.P40, kid))
        for a in kids:
            for b in kids:
                if a != b:
                    self.graph.add((a, WDT.P3373, b))

    def spouses(self, person: URIRef) -> list[URIRef]:
        """Everyone `person` is married to."""
        return list(self.graph.objects(person, WDT.P26))


def siblings(base: str, year: int) -> Iterator[tuple[str, str, int]]:
    """(position, letter, birth year) of the elder and younger brother and sister."""
    for letter in "BZ":
        for age, offset in (("e", -5), ("y", 5)):
            yield f"{base}{age}{letter}", letter, year + offset


def parents_siblings(family: Family, parent: URIRef, base: str) -> None:
    """Add a parent's parents, and their other children with spouses and children."""
    grandfather, grandmother = family.couple(base, 1900)
    kids = []
    for position, letter, year in siblings(base, 1930):
        sibling = family.person(position, SEX[letter], year)
        kids.append(sibling)
        spouse = family.wed(sibling, position, SEX[letter], year)
        # a cousin's age is relative to ego, the parent's sibling's is dropped
        cousins = [
            family.person(f"{base}{letter}{age}{child}", SEX[child], 1960 + offset)
            for child in "SD"
            for age, offset in (("e", -2), ("y", 2))
        ]
        family.children(
            *((sibling, spouse) if letter == "B" else (spouse, sibling)), cousins
        )
    family.children(grandfather, grandmother, [parent, *kids])


def build_family(ego_sex: str) -> tuple[Family, URIRef]:
    """Build the family around an ego of `ego_sex` (``m`` or ``f``)."""
    family = Family(ego_sex)
    ego = family.person("", ego_sex, 1960)
    partner = family.wed(ego, "", ego_sex, 1960)
    father, mother = family.couple("", 1930)
    parents_siblings(family, father, "F")
    parents_siblings(family, mother, "M")
    kids = []
    for position, letter, year in siblings("", 1960):
        sibling = family.person(position, SEX[letter], year)
        kids.append(sibling)
        # a sibling's spouse has no age slot, its child keeps the sibling's age
        spouse = family.wed(sibling, letter, SEX[letter], year)
        nephews = [family.person(position + c, SEX[c], 1990) for c in "SD"]
        family.children(
            *((sibling, spouse) if letter == "B" else (spouse, sibling)), nephews
        )
    family.children(father, mother, [ego, *kids])
    for spouse in family.spouses(ego):
        base = family.label[spouse]
        in_father, in_mother = family.couple(base, 1930)
        in_siblings = [
            family.person(base + letter, SEX[letter], 1960 + offset)
            for letter in "BZ"
            for offset in (-5, 5)
        ]
        family.children(in_father, in_mother, [spouse, *in_siblings])
    children = []
    for letter in "SD":
        child = family.person(letter, SEX[letter], 1985)
        children.append(child)
        spouse = family.wed(child, letter, SEX[letter], 1985)
        grandchildren = [family.person(letter + g, SEX[g], 2010) for g in "SD"]
        family.children(
            *((child, spouse) if letter == "S" else (spouse, child)), grandchildren
        )
    family.children(*((ego, partner) if ego_sex == "m" else (partner, ego)), children)
    return family, ego


def extent(path: str, families: list[tuple[Family, URIRef]]) -> frozenset[Atom] | str:
    """The positions `path` reaches from ego, or why it reaches none.

    Returns ``"empty"`` when it reaches nobody in the family (great-grandparents,
    step and god relations), ``"self"`` when it reaches ego, and ``"error"`` when
    rdflib cannot run it.
    """
    atoms: set[Atom] = set()
    for family, ego in families:
        query = (
            f"{PREFIXES}SELECT DISTINCT ?relative WHERE "
            f"{{ VALUES ?person {{ <{ego}> }} {path} }}"
        )
        try:
            results = list(family.graph.query(query))
        except Exception:  # noqa: BLE001  (rdflib raises several parse errors)
            return "error"
        for (relative,) in results:
            label = family.label.get(relative)
            if not label:
                return "self"
            atoms |= kinbank_atoms(family.ego_sex + label) or set()
    return frozenset(atoms) if atoms else "empty"


def fetch() -> None:
    """Download the kinship items with a P4316 path to `ITEMS`."""
    url = ENDPOINT + "?" + urllib.parse.urlencode({"query": ITEMS_QUERY})
    request = urllib.request.Request(
        url, headers={"Accept": "text/csv", "User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        rows = list(csv.DictReader(response.read().decode("utf8").splitlines()))
    with ITEMS.open("w", encoding="utf8") as out:
        out.write("qid\tlabel\tpath\tili\tconcepticon\n")
        for row in sorted(
            rows, key=lambda r: (int(r["item"].rsplit("Q", 1)[1]), r["path"])
        ):
            qid = row["item"].rsplit("/", 1)[1]
            fields = (qid, row["label"], row["path"], row["ili"], row["concepticon"])
            out.write("\t".join(f.replace("\t", " ") for f in fields) + "\n")
    logger.info("fetched %d paths", len(rows))


def main() -> None:
    """Write wikidata-candidates.tsv."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if "--fetch" in sys.argv[1:]:
        fetch()
    concepts = build.read_concepts()
    ours = build.positions(concepts)
    by_extent: dict[frozenset[Atom], list[str]] = {}
    for code, atoms in ours.items():
        by_extent.setdefault(atoms, []).append(code)
    families = [build_family("m"), build_family("f")]
    rows = []
    for item in build.read_tsv(ITEMS):
        found = extent(item["path"], families)
        if isinstance(found, str):
            match, concept, note = found, "", ""
        elif found in by_extent:
            match, concept, note = "exact", "|".join(by_extent[found]), ""
        else:
            within = [c for c, a in ours.items() if found < a]
            contains = [c for c, a in ours.items() if a < found]
            match, concept = "none", ""
            note = (
                f"{len(found)} positions; within "
                f"{min(within, key=lambda c: len(ours[c]), default='-')}; contains "
                f"{max(contains, key=lambda c: len(ours[c]), default='-')}"
            )
        dated = "P569" in item["path"]
        rows.append(
            (
                item["qid"],
                item["label"],
                match,
                concept,
                "dated" if dated else "",
                note,
                item["ili"],
                item["concepticon"],
            )
        )
    with OUTPUT.open("w", encoding="utf8") as out:
        out.write("qid\tlabel\tmatch\tconcept\tage_filter\tnote\tili\tconcepticon\n")
        for row in rows:
            out.write("\t".join(row) + "\n")
    logger.info("%s", dict(Counter(row[2] for row in rows)))


if __name__ == "__main__":
    main()
