#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["langcodes", "language_data", "unidecode"]
# ///
"""Read Omniglot's family-word pages into a table of words with concept codes.

Omniglot (Simon Ager, https://www.omniglot.com/language/kinship/) lists about 30
family words per language. Simon Ager gave permission to use its material under
CC BY-SA (2015), so the words go into the build (`build.add_omniglot`) as well as
the review files (``omniglot`` lines). The pages are saved by hand (the site
blocks automated access) to ``sources/omniglot/``; only the extracted table is
committed.

Each page is one table of an English label and the language's words. A cell
holds several words, each with qualifiers that narrow the label's concept:

- relative age: ``+``/``-`` (Chinese), ``(older)``, ``- younger``, ``elder male``
- sex: ``(m)``, ``(f)``, ``+m``, ``female``
- side: ``pt``/``mt`` (paternal, maternal; Chinese grandparents)
- a gloss: ``father's elder brother``, ``(brother's son)``
- register: ``frm``, ``inf``, ``vfrm``, kept as a note

A word gets the most specific of our concepts that its label and qualifiers
allow; ``match`` is ``exact`` when every qualifier was used and ``broader`` when
some were dropped to reach a concept. Then:

- a word listed under both sexes of a label (Indonesian *kakak* under "brother
  (older)" and "sister (older)") goes on the concept that covers both
  (``El:Sb``), which is what it means;
- a word under a plural label ("children", "grandparents") in a language that
  inflects for number is a plural form, not a lemma: ``plural``;
- a word in ``data/omniglot-curation.tsv`` is left out (``excluded``): an
  error, a typo, a joke or a phrase. Its ``feedback`` column holds the
  corrections to send to Omniglot.

Only ``exact`` rows are built. Writes ``data/candidates/omniglot-words.tsv``.

Usage: uv run scripts/omniglot_words.py
"""

from __future__ import annotations

import csv
import html
import logging
import re
from pathlib import Path

import build

logger = logging.getLogger(__name__)

PAGES = build.ROOT / "sources" / "omniglot"
OUTPUT = build.CANDIDATES / "omniglot-words.tsv"
CURATION = build.DATA / "omniglot-curation.tsv"
#: labels whose words are plural forms where a language inflects for number
PLURAL_LABELS = {
    "children",
    "child(-ren)",
    "grandchildren",
    "grandparents",
    "parents",
    "nephews & nieces",
    "siblings",
    "relatives",
}
#: languages on our pages that inflect nouns for number
INFLECTING = {"cs", "de", "en", "es", "pl", "sk"}
#: the term covering both sexes of a term
BOTH = {
    "Br": "Sb",
    "Ss": "Sb",
    "Fa": "Pa",
    "Mo": "Pa",
    "So": "Ch",
    "Da": "Ch",
    "Hu": "Sp",
    "Wi": "Sp",
}
#: language named in the saved page's title -> our tag
LANGUAGES = {
    "Cantonese": "yue",
    "Czech": "cs",
    "English": "en",
    "German": "de",
    "Indonesian": "id",
    "Japanese": "ja",
    "Malay": "ms",
    "Mandarin": "cmn",
    "Polish": "pl",
    "Slovak": "sk",
    "Spanish": "es",
}
#: Omniglot's English labels -> our concept; labels missing here have none
LABELS = {
    "relative": "Rel",
    "relatives": "Rel",
    "kin, relatives": "Rel",
    "parents": "Pl;Pa",
    "father": "Fa",
    "mother": "Mo",
    "children": "Ch",
    "child(-ren)": "Ch",
    "son": "So",
    "daughter": "Da",
    "spouse": "Sp",
    "spouse, couple": "Sp",
    "husband": "Hu",
    "wife": "Wi",
    "siblings": "Sb",
    "sibling": "Sb",
    "siblings (brothers)": "Br",
    "siblings (sisters)": "Ss",
    "brother": "Br",
    "sister": "Ss",
    "older brother": "El:Br",
    "older sister": "El:Ss",
    "younger brother": "Yn:Br",
    "younger sister": "Yn:Ss",
    "youger sister": "Yn:Ss",
    "uncle": "Unc",
    "aunt": "Aun",
    "uncle (older than parent)": "Pa;El:Br",
    "uncle (younger than parent)": "Pa;Yn:Br",
    "aunt (older than parent)": "Pa;El:Ss",
    "aunt (younger than parent)": "Pa;Yn:Ss",
    "uncle-in-law (aunt's husband)": "Pa;Ss;Hu",
    "aunt-in-law (uncle's wife)": "Pa;Br;Wi",
    "cousin": "Pa;Sb;Ch",
    "cousin (paternal)": "Fa;Sb;Ch",
    "cousin (maternal)": "Mo;Sb;Ch",
    "nephew": "Sb;So",
    "niece": "Sb;Da",
    "nephew, niece": "Sb;Ch",
    "nephews & nieces": "Sb;Ch",
    "grandparents": "Pa;Pa",
    "grandfather": "Pa;Fa",
    "grandmother": "Pa;Mo",
    "grandchildren": "Ch;Ch",
    "grandchild": "Ch;Ch",
    "grandson": "Ch;So",
    "granddaughter": "Ch;Da",
    "father-in-law": "Sp;Fa",
    "mother-in-law": "Sp;Mo",
    "brother-in-law": "BrL",
    "brother-in-law stepbrother": "BrL",
    "sister-in-law": "SsL",
    "sister-in-law stepsister": "SsL",
    "son-in-law": "Da;Hu",
    "daughter-in-law": "So;Wi",
    "child-in-law": "Ch;Sp",
    "parent of one's child's spouse": "InL",
}
KIN = {
    "father": "Fa",
    "mother": "Mo",
    "parent": "Pa",
    "son": "So",
    "daughter": "Da",
    "child": "Ch",
    "brother": "Br",
    "sister": "Ss",
    "sibling": "Sb",
    "husband": "Hu",
    "wife": "Wi",
    "spouse": "Sp",
}
AGES = {
    "elder": "El",
    "older": "El",
    "eldest": "El",
    "younger": "Yn",
    "youngest": "Yn",
}
REGISTER = {"frm", "inf", "vfrm"}
ARTICLES = re.compile(r"^(?:el|la|los|las|der|die|das)\s+")
CJK = re.compile(r"[々぀-ヿ㐀-鿿豈-﫿]+")


def phrase_code(phrase: str) -> str:
    """The code for an English kin phrase, or '' if it is not one.

    >>> phrase_code("father's elder brother"), phrase_code("wife’s younger sister")
    ('Fa;El:Br', 'Wi;Yn:Ss')
    >>> phrase_code("brother's son"), phrase_code("spouse's sister's husband")
    ('Br;So', 'Sp;Ss;Hu')
    >>> phrase_code("general term")
    ''
    """
    parts = []
    for part in re.split(r"[’']s\s+", phrase.strip().lower()):
        words = part.split()
        if not words or words[-1] not in KIN:
            return ""
        if len(words) == 2 and words[0] in AGES:
            parts.append(f"{AGES[words[0]]}:{KIN[words[-1]]}")
        elif len(words) == 1:
            parts.append(KIN[words[-1]])
        else:
            return ""
    return ";".join(parts)


def with_age(code: str, age: str) -> list[str]:
    """Ways to add relative age to `code`: on each link, the last first.

    Only one of them names a concept: the one whose link has the age slot.

    >>> with_age("Br", "El"), with_age("Pa;Br", "Yn")
    (['El:Br'], ['Pa;Yn:Br', 'Yn:Pa;Br'])
    """
    terms = code.split(";")
    return [
        ";".join(f"{age}:{t}" if i == j else t for j, t in enumerate(terms))
        for i in reversed(range(len(terms)))
    ]


def with_sex(code: str, sex: str) -> str:
    """Narrow the last link of `code` to a sex (``m`` or ``f``) where it allows one.

    >>> with_sex("Pa;Sb;Ch", "m"), with_sex("Sb", "f"), with_sex("Fa", "f")
    ('Pa;Sb;So', 'Ss', 'Fa')
    """
    terms = code.split(";")
    narrow = {"Ch": {"m": "So", "f": "Da"}, "Sb": {"m": "Br", "f": "Ss"}}
    terms[-1] = narrow.get(terms[-1], {}).get(sex, terms[-1])
    return ";".join(terms)


def with_side(code: str, side: str) -> str:
    """Put the first link of `code` on the father's or mother's side.

    >>> with_side("Pa;Fa", "pt"), with_side("Pa;Mo", "mt"), with_side("Br", "pt")
    ('Fa;Fa', 'Mo;Mo', 'Br')
    """
    terms = code.split(";")
    if terms[0] == "Pa":
        terms[0] = "Fa" if side == "pt" else "Mo"
    return ";".join(terms)


def qualifiers(text: str) -> dict[str, str]:
    """Read age, sex, side, register and a gloss from a word's qualifiers.

    >>> qualifiers("+m") == {"age": "El", "sex": "m"}
    True
    >>> qualifiers("pt-frm") == {"side": "pt", "register": "frm"}
    True
    >>> qualifiers("- inf") == {"register": "inf"}
    True
    >>> qualifiers("father's elder brother")["gloss"]
    'Fa;El:Br'
    """
    found: dict[str, str] = {}
    text = text.strip()
    # a final + or - is relative age (Chinese); elsewhere - is a separator
    if match := re.search(r"(?:^|\s)([+-])(m|f)?$", text):
        found["age"] = "El" if match.group(1) == "+" else "Yn"
        if match.group(2):
            found["sex"] = match.group(2)
    for chunk in re.split(r"[()\-,]|\s{2,}", text):
        chunk = chunk.strip().lower()
        if not chunk:
            continue
        if code := phrase_code(chunk):
            found["gloss"] = code
            continue
        for word in chunk.split():
            if word in REGISTER:
                found["register"] = word
            elif word in ("pt", "mt"):
                found["side"] = word
            elif word in AGES:
                found["age"] = AGES[word]
            elif word in ("m", "male"):
                found["sex"] = "m"
            elif word in ("f", "female"):
                found["sex"] = "f"
    return found


def candidates(label_code: str, found: dict[str, str]) -> list[tuple[str, str]]:
    """Codes to try for a word, most specific first, each with its match kind.

    A gloss names the word's meaning, so it is the only exact candidate when
    there is one; the label's code is then broader. Dropping the relative age
    gives a broader code too.

    >>> candidates("BrL", {"gloss": "El:Ss;Hu"})
    [('El:Ss;Hu', 'exact'), ('Ss;Hu', 'broader'), ('BrL', 'broader')]
    >>> candidates("Br", {"age": "El"})[:2]
    [('El:Br', 'exact'), ('Br', 'broader')]
    """
    code = label_code
    if "side" in found:
        code = with_side(code, found["side"])
    if "sex" in found:
        code = with_sex(code, found["sex"])
    if "gloss" in found:
        exact = [found["gloss"]]
        labelled = [code]
    elif "age" in found and ":" not in code:
        exact = with_age(code, found["age"])
        labelled = []
    else:
        exact = [code]
        labelled = []
    ageless = [re.sub(r"(?:El|Yn):", "", c) for c in exact]
    broader = [
        *ageless,
        *labelled,
        code,
        with_sex(label_code, found.get("sex", "")),
        label_code,
    ]
    broader = [c for c in dict.fromkeys(broader) if c not in exact]
    return [(c, "exact") for c in exact] + [(c, "broader") for c in broader]


def cell_lines(cell: str) -> list[list[str]]:
    """A cell's lines, grouped: blank lines separate groups where the cell has them."""
    text = html.unescape(re.sub(r"(?i)<br\s*/?>", "\n", cell))
    lines = [re.sub(r"<[^>]+>", "", line).strip() for line in text.split("\n")]
    if "" not in lines[1:-1]:
        return [[line] for line in lines if line]
    groups, group = [], []
    for line in lines:
        if line:
            group.append(line)
        elif group:
            groups.append(group)
            group = []
    return [*groups, group] if group else groups


def cjk_words(lines: list[str]) -> list[tuple[str, str, str]]:
    """(word, romanization, qualifiers) from the lines of a CJK cell.

    A line with no CJK word is a gloss for the words since the last gloss.

    >>> cjk_words(["伯伯 (bóbo) father's elder brother"])
    [('伯伯', 'bóbo', "father's elder brother")]
    >>> cjk_words(["哥哥 (gòhgō) / 大佬 (daailóu) +", "弟弟 (dàihdái) -"])
    [('哥哥', 'gòhgō', '+'), ('大佬', 'daailóu', '+'), ('弟弟', 'dàihdái', '-')]
    >>> cjk_words(["阿伯 (a baak)", "father's elder brother", "姑丈 (gùjéung)"])
    [('阿伯', 'a baak', "father's elder brother"), ('姑丈', 'gùjéung', '')]
    >>> cjk_words(["亲戚 [親戚] (qīnqi)"])
    [('亲戚', 'qīnqi', '[親戚]')]
    """
    words: list[list[str]] = []
    pending = 0  # words[pending:] still wait for a gloss line
    for line in lines:
        if not CJK.search(re.sub(r"\[[^\]]*\]", "", line)):
            for word in words[pending:]:
                word[2] = f"{word[2]} {line}".strip()
            pending = len(words)
            continue
        rest = re.findall(r"\[[^\]]*\]", line)
        line = re.sub(r"\[[^\]]*\]", "", line)
        found, position = [], 0
        for match in CJK.finditer(line):
            roman = re.match(r"\s*\(([^)]*)\)", line[match.end() :])
            found.append([match.group(), roman.group(1) if roman else ""])
            rest.append(line[position : match.start()])
            position = match.end() + (roman.end() if roman else 0)
        rest.append(line[position:])
        note = re.sub(r"\s+", " ", " ".join(r.replace("/", " ") for r in rest)).strip()
        words += [[w, r, note] for w, r in found]
    return [(w, r, n) for w, r, n in words]


def latin_words(line: str) -> list[tuple[str, str, str]]:
    """(word, '', qualifiers) from a line of a cell in a Latin-script language.

    A parenthesis inside a ``;`` list, or before the end of a ``,`` list, belongs
    to the word before it; one at the end of a ``,`` list belongs to all.

    >>> latin_words("abang, bang, kak (older)")
    [('abang', '', '(older)'), ('bang', '', '(older)'), ('kak', '', '(older)')]
    >>> latin_words("der Schwager; Schwippschwager (spouse's sister's husband)")
    [('Schwager', '', ''), ('Schwippschwager', '', "(spouse's sister's husband)")]
    >>> latin_words("father, pater (frm), dad")
    [('father', '', ''), ('pater', '', '(frm)'), ('dad', '', '')]
    >>> latin_words("ibu saudara frm")
    [('ibu saudara', '', 'frm')]
    """
    out = []
    for segment in re.split(r"\s+/\s+", line):
        separator = ";" if ";" in segment else ","
        items = [i.strip() for i in segment.split(separator) if i.strip()]
        shared = ""
        if separator == "," and len(items) > 1 and "(" not in " ".join(items[:-1]):
            last = re.match(r"(.*?)\s*(\([^)]*\)(?:\s*\([^)]*\))*)\s*$", items[-1])
            if last:
                items[-1], shared = last.group(1), last.group(2)
        for item in items:
            notes = re.findall(r"\s*(\([^)]*\))", item)
            word = re.sub(r"\s*\([^)]*\)", "", item).strip()
            bare = word.split()
            while bare and bare[-1].strip("-") in REGISTER:
                notes.append(bare.pop().strip("-"))
            word = ARTICLES.sub("", " ".join(bare)).strip("*").strip()
            note = " ".join([*notes, shared]).strip()
            for form in word.split("/"):
                if form.strip():
                    out.append((form.strip(), "", note))
    return out


def read_page(path: Path) -> list[tuple[str, str, str, str]]:
    """(label, word, romanization, qualifiers) for every word on a saved page."""
    page = path.read_text(encoding="utf8")
    table = re.search(r"(?s)<table.*?</table>", page).group()
    rows = []
    for tr in re.findall(r"(?s)<tr.*?</tr>", table):
        cells = re.findall(r"(?s)<t[dh][^>]*>(.*?)</t[dh]>", tr)
        for label_cell, cell in zip(cells[::2], cells[1::2]):
            label = " ".join(
                line for group in cell_lines(label_cell) for line in group
            ).lower()
            groups = cell_lines(cell)
            lines = [line for group in groups for line in group]
            if CJK.search(" ".join(lines)):
                words = cjk_words(lines)
            else:
                words = [w for line in lines for w in latin_words(line)]
            rows += [(label, *w) for w in words]
    return rows


def merged(code: str, other: str) -> str:
    """The code covering both `code` and `other` if they differ only in one
    term's sex or relative age, else ''.

    >>> merged("El:Br", "El:Ss"), merged("Sp;Fa", "Sp;Mo"), merged("Br", "Fa")
    ('El:Sb', 'Sp;Pa', '')
    >>> merged("Pa;El:Br", "Pa;Yn:Br")
    'Pa;Br'
    """
    a, b = code.split(";"), other.split(";")
    if len(a) != len(b):
        return ""
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if len(diff) != 1:
        return ""
    i = diff[0]
    *mods_a, term_a = a[i].split(":")
    *mods_b, term_b = b[i].split(":")
    if term_a == term_b and {*mods_a, *mods_b} == {"El", "Yn"}:
        a[i] = term_a
        return ";".join(a)
    if mods_a != mods_b or term_a == term_b or BOTH.get(term_a) != BOTH.get(term_b):
        return ""
    a[i] = ":".join([*mods_a, BOTH[term_a]]) if term_a in BOTH else ""
    return ";".join(a) if a[i] else ""


def merge_sexes(rows: list[list[str]], concepts: dict) -> None:
    """Put a word listed under both sexes of a concept on the one covering both."""
    by_word: dict[tuple[str, str], list[list[str]]] = {}
    for row in rows:
        if row[6] == "exact":
            by_word.setdefault((row[0], row[3]), []).append(row)
    for group in by_word.values():
        for one in group:
            for two in group:
                both = merged(one[5], two[5])
                if both and both in concepts:
                    labels = f"(under {one[2]} and {two[2]})"
                    for row in (one, two):
                        row[5], row[7] = both, f"{row[7]} {labels}".strip()


def main() -> None:
    """Write omniglot-words.tsv."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    concepts = build.read_concepts()
    out = []
    skipped: dict[str, int] = {}
    for path in sorted(PAGES.glob("*.html")):
        name = next((n for n in LANGUAGES if n in path.name), None)
        if not name:
            logger.warning("no language for %s", path.name)
            continue
        for label, word, roman, note in read_page(path):
            if label in ("", "family") or label.startswith(name.lower()):
                continue
            label_code = LABELS.get(label)
            if not label_code:
                skipped[label] = skipped.get(label, 0) + 1
                continue
            found = qualifiers(note)
            code, kind = next(
                ((c, k) for c, k in candidates(label_code, found) if c in concepts),
                ("", ""),
            )
            tag = LANGUAGES[name]
            if kind == "exact" and tag in INFLECTING and label in PLURAL_LABELS:
                kind = "plural"
            out.append([tag, name, label, word, roman, code, kind, note])
    merge_sexes(out, concepts)
    excluded = {
        (row["tag"], row["word"], row["code"]) for row in build.read_tsv(CURATION)
    }
    for row in out:
        if (row[0], row[3], row[5]) in excluded:
            row[6] = "excluded"
    columns = ["tag", "language", "label", "word", "romanization", "code", "match"]
    with OUTPUT.open("w", encoding="utf8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow([*columns, "note"])
        writer.writerows(out)
    logger.info(
        "wrote %d words (%d languages); labels with no concept: %s",
        len(out),
        len({r[0] for r in out}),
        ", ".join(f"{k} ({v})" for k, v in sorted(skipped.items())),
    )


if __name__ == "__main__":
    main()
