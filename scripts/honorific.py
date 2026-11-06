"""Guess the honorific values of Japanese kin terms from their form.

The values are omw-pronoun's (FEATURES.md, "Formality and politeness"), on two
axes: the referent axis (``Hon`` honorific, ``Pol`` polite, ``Fam`` familiar,
``NHon`` non-honorific) and the addressee axis (``Fml`` formal, ``Infml``
informal, ``Hum`` humble, which entails ``Fml``). Kin terms carry them on their
senses, not their codes: お父さん and 父 are both ``Fa``.

Most of a Japanese kin term's value follows from its title suffix or prefix:

- -様/さま, -殿: ``Hon;Fml``; -上, -君, -者人: ``Hon;Arch``; -御: ``Hon``
- -さん, -はん: ``Pol`` (said of one's own family and of others', so no addressee value)
- -ちゃん, -くん: ``Fam;Infml``; -貴: ``Infml``
- 令-, 尊-, 賢-: ``Hon;Fml`` (someone else's family); 愚-, 家-, 拙-, 豚-:
  ``Fml;Hum`` (one's own)
- お-/御-/ご- on a bare stem: ``Pol``
- a katakana loanword (ファーザー): unmarked
- a bare term for a senior relative (父, 兄, 祖母): ``Fml;Hum``, the in-group
  form used to an outsider; a bare term for anyone else (弟, 息子, 妻):
  unmarked

`OVERRIDES` lists words whose value does not follow from their form. Every value
is a guess for a reviewer to confirm.
"""

from __future__ import annotations

from collections.abc import Iterable

from kintype import Atom

#: title suffixes, longest first, and the values they give
SUFFIXES = [
    ("っつぁん", "Infml", "-っつぁん"),
    ("っつあん", "Infml", "-っつあん"),
    ("っさん", "Infml", "-っさん"),
    ("さま", "Hon;Fml", "-さま"),
    ("様", "Hon;Fml", "-様"),
    ("殿", "Hon;Fml", "-殿"),
    ("ちゃん", "Fam;Infml", "-ちゃん"),
    ("チャン", "Fam;Infml", "-ちゃん"),
    ("くん", "Fam;Infml", "-くん"),
    ("さん", "Pol", "-さん"),
    ("はん", "Pol", "-はん"),
    ("者人", "Hon;Arch", "-者人"),
    ("じゃ人", "Hon;Arch", "-じゃ人"),
    ("上", "Hon;Arch", "-上"),
    ("君", "Hon;Arch", "-君"),
    ("御", "Hon", "-御"),
    ("貴", "Infml", "-貴"),
]
#: Sino-Japanese prefixes for someone else's family and for one's own
PREFIXES = [
    ("令", "Hon;Fml", "令-"),
    ("御令", "Hon;Fml", "令-"),
    ("尊", "Hon;Fml", "尊-"),
    ("賢", "Hon;Fml", "賢-"),
    ("愚", "Fml;Hum", "愚-"),
    ("家", "Fml;Hum", "家-"),
    ("拙", "Fml;Hum", "拙-"),
    ("豚", "Fml;Hum", "豚-"),
]
#: words whose value does not follow from their form
OVERRIDES = {
    "おやじ": ("Infml", "lexical"),
    "親父": ("Infml", "lexical"),
    "おふくろ": ("Infml", "lexical"),
    "お袋": ("Infml", "lexical"),
    "御袋": ("Infml", "lexical"),
    "じじ": ("Infml", "lexical"),
    "パパ": ("Infml", "lexical"),
    "ママ": ("Infml", "lexical"),
    "ねえ": ("Infml", "lexical"),
    "兄い": ("Infml", "lexical"),
    "おっ母": ("Infml", "lexical"),
    "嚊": ("Infml", "lexical"),
    "宿六": ("NHon;Infml", "lexical"),
    "椿堂": ("Hon;Fml", "lexical: someone else's father"),
    "ばば": ("Infml", "lexical"),
    "細君": ("Fml;Hum", "lexical: one's own wife"),
    "妻君": ("Fml;Hum", "lexical: one's own wife"),
    "家内": ("Fml;Hum", "lexical: one's own wife"),
}
#: kana stems that begin with お but are not お- plus a stem
NOT_PREFIXED = ("おじ", "おば", "おい", "おと", "おや", "おっと", "おとうと")
KANJI = range(0x4E00, 0xA000)
KATAKANA = range(0x30A0, 0x3100)


def honorific_prefix(word: str) -> str:
    """The honorific prefix お, 御 or ご that `word` starts with, or ''.

    >>> honorific_prefix("お祖父"), honorific_prefix("御袋"), honorific_prefix("ご主人")
    ('お', '御', 'ご')
    >>> honorific_prefix("おじ"), honorific_prefix("おとうと")
    ('', '')
    """
    if word[:1] in ("御", "ご") and len(word) > 1:
        return word[0]
    if word.startswith("お") and len(word) > 1:
        if ord(word[1]) in KANJI:
            return "お"
        if not word.startswith(NOT_PREFIXED):
            return "お"
    return ""


def generation(atom: Atom) -> int:
    """The generations from the anchor to an atom's relative: +1 per parent link."""
    _, links = atom
    return sum({"F": 1, "M": 1, "S": -1, "D": -1}.get(letter, 0) for _, letter in links)


def senior(atoms: Iterable[Atom]) -> bool:
    """True if every position is senior to the anchor: older generation, or elder.

    >>> senior([("m", (("", "F"),))]), senior([("m", (("e", "B"),))])
    (True, True)
    >>> senior([("m", (("y", "B"),))]), senior([("m", (("", "W"),))])
    (False, False)
    >>> senior([("m", (("e", "B"), ("", "S")))]), senior([])
    (False, False)
    """
    atoms = list(atoms)
    return bool(atoms) and all(
        generation(a) > 0 or (generation(a) == 0 and any(age == "e" for age, _ in a[1]))
        for a in atoms
    )


def guess(word: str, atoms: Iterable[Atom]) -> tuple[str, str]:
    """The honorific values of the Japanese kin term `word`, and why.

    `atoms` are the positions of its concept. The value is ``""`` for an
    unmarked word.

    >>> fa = [("m", (("", "F"),))]
    >>> guess("お父様", fa), guess("お父さん", fa), guess("父ちゃん", fa)
    (('Hon;Fml', '-様'), ('Pol', '-さん'), ('Fam;Infml', '-ちゃん'))
    >>> guess("父", fa), guess("父上", fa), guess("親父", fa)
    (('Fml;Hum', 'bare, senior'), ('Hon;Arch', '-上'), ('Infml', 'lexical'))
    >>> guess("弟", [("m", (("y", "B"),))]), guess("令息", [("m", (("", "S"),))])
    (('', 'bare, junior'), ('Hon;Fml', '令-'))
    >>> guess("御祖父", [("m", (("", "F"), ("", "F")))]), guess("ファーザー", fa)
    (('Pol', 'お-/御-'), ('', 'loanword'))
    """
    if word in OVERRIDES:
        return OVERRIDES[word]
    for suffix, value, why in SUFFIXES:
        if word.endswith(suffix) and len(word) > len(suffix):
            return value, why
    for prefix, value, why in PREFIXES:
        if word.startswith(prefix) and len(word) > len(prefix):
            return value, why
    if all(ord(c) in KATAKANA for c in word):
        return "", "loanword"
    if honorific_prefix(word):
        return "Pol", "お-/御-"
    if senior(atoms):
        return "Fml;Hum", "bare, senior"
    return "", "bare, junior"
