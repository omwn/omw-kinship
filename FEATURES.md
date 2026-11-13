# Kin-type features

Every concept is named by a kin-type code in the notation of Murdock (1970), as
[KinDiv](https://github.com/kbatsuren/KinDiv) (Khishigsuren et al. 2022) uses it: `Fa;Br;So` is "father's brother's son", `x;El:Ss` is "a man's
elder sister", and `Fa|Fa;Br` is "father or father's brother". This file gives
the meaning of the codes as an algebra over genealogical positions, then lists
every feature.

The positions are computed by `kindiv_atoms` in `scripts/kintype.py`; the English
definitions and phrases by `parse`, `define` and `phrase` in `scripts/build.py`.

## The algebra

### Positions

A code denotes a set of **positions**. A position is a path through the family
tree from a person, the **anchor**, to a relative:

    (s, ⟨k₁, …, kₙ⟩)

- `s` is the anchor's sex: `m` or `f`;
- each `kᵢ` is one of eight elementary links: **F**ather, **M**other,
  **B**rother, sister (**Z**), **S**on, **D**aughter, **H**usband, **W**ife.

The path is read outward from the anchor: ⟨F, B, S⟩ is the anchor's father's
brother's son.

At most one link in a path also carries a **relative age**, `e` (elder) or `y`
(younger). Its person is compared with **the nearest earlier person on the path
of the same generation**. Which link can carry it depends on the shape of the
path, writing P for a parent link, S for a sibling, C for a child and E for a
spouse:

| shape | example | the age is that of | compared with |
|---|---|---|---|
| S | `El:Br` | the sibling | the anchor |
| PS | `Fa;El:Br` | the parent's sibling | the parent |
| SC | `El:Br;Ch` | the sibling | the anchor |
| PSC | `Fa;Br;El:So` | the cousin | the anchor |
| PSE | `Fa;El:Br;Wi` | the parent's sibling | the parent |
| ES | `Sp;El:Br` | the spouse's sibling | the spouse |
| SE | `El:Ss;Hu` | the sibling | the anchor |

Other shapes (grandparents, parents-in-law, …) record no age. Where a shape has
an age slot and the code gives no age, the code covers both ages: `Br` denotes
the elder and the younger brother, and `Sp;Br` a spouse's elder and younger
brother.

### Terms

Each kin term denotes a set of links. A specific term denotes one link; a
general term denotes the choice of several:

    L(Fa) = {F}   L(Mo) = {M}   L(Pa) = {F, M}
    L(Br) = {B}   L(Ss) = {Z}   L(Sb) = {B, Z}
    L(So) = {S}   L(Da) = {D}   L(Ch) = {S, D}
    L(Hu) = {H}   L(Wi) = {W}   L(Sp) = {H, W}

### Operations

Codes are built with four operations. Their meaning is given by ⟦·⟧, the set of
positions a code denotes.

1. **Composition** (`;` between kin terms) extends the path by one link, choosing
   any link the term allows:

       ⟦t₁;…;tₙ⟧ = { (s, ⟨k₁,…,kₙ⟩) | s ∈ {m,f}, kᵢ ∈ L(tᵢ) }

   So `Fa;Br` is father's brother, and `Pa;Sb;Ch` covers all 2 × 2 × 2 = 8 kinds
   of first cousin: 32 positions once the anchor's sex and the cousin's age are
   counted.

2. **Anchor restriction** (`x;` or `o;` at the front) keeps the positions with a
   male or female anchor:

       ⟦x;c⟧ = { (m, p) ∈ ⟦c⟧ }      ⟦o;c⟧ = { (f, p) ∈ ⟦c⟧ }

   KinDiv's labels say "male/female speaking", but the feature restricts the
   anchor, not the speaker, so the build labels these concepts "(male anchor)" and
   "(female anchor)".

3. **Age restriction** (`El:` or `Yn:`) keeps the positions whose age slot is
   elder or younger. It is attached with `:` to the term whose person it
   describes, so `;` only ever separates links: `Fa;El:Br` is father's elder
   brother, `Fa;Br;El:So` a father's brother's son older than the anchor, and
   `El:Ss;Hu` an elder sister's husband. An age on a link with no age slot is an
   error. KinDiv writes the age as a term of its own (`Fa;El;Br`), with a
   cousin's at the front (`El;Fa;Br;So`); `from_kindiv` in `kintype.py`
   converts its codes when they are read.

4. **Union** (`|`) is set union, and it binds loosest of all:

       ⟦c | d⟧ = ⟦c⟧ ∪ ⟦d⟧

   Each part is read on its own, so `o;Br|x;Ss` is "a woman's brother or a man's
   sister": an opposite-sex sibling.

The full grammar of a code is

    code   := chain ( "|" chain )*
    chain  := [ anchor ";" ] link ( ";" link )*
    link   := [ age ":" ] term
    anchor := "x" | "o"
    age    := "El" | "Yn"
    term   := kin term | abbreviation

plus the six named nodes listed below, which stand on their own.

### Order and hypernymy

Codes are ordered by containment: c ⊑ d when ⟦c⟧ ⊆ ⟦d⟧. The hierarchy is this
order: `build.py` puts each concept below every concept whose positions strictly
contain its own, and its hypernyms are the smallest of these. The stated
relations (KinDiv's `relations` and `data/extra-relations.tsv`) are only needed
for `Rel` and `InL`. The tests check that every stated relation is a containment
and that no two concepts denote the same set.

The basic ways to get a broader code follow from the definitions:

- **drop a restriction**: `x;El:Br` ⊑ `El:Br` ⊑ `Br`;
- **generalize a term**: `Fa;Br;So` ⊑ `Pa;Br;So` ⊑ `Pa;Sb;So` ⊑ `Pa;Sb;Ch`;
- **add a disjunct**: `Fa` ⊑ `Fa|Fa;Br`.

Composition is monotone in each term, so these can be applied anywhere in a chain.

Two codes can have common hyponyms. `x;El:Br` "a man's elder brother" lies under
both `x;Br` "a man's brother" and `El:Br` "elder brother", because
⟦x;Br⟧ ∩ ⟦El:Br⟧ = ⟦x;El:Br⟧. This is why the hierarchy is a graph rather than a
tree: a concept can have several hypernyms, one for each feature that can be
generalized.

Some codes have the same meaning:

    Pa  = Fa|Mo           Sb = Br|Ss          Ch = So|Da         Sp = Hu|Wi
    Br  = El:Br | Yn:Br   Sb = x;Sb | o;Sb
    Pb  = Pa;Sb

Only one of each set of equivalent codes is used for a concept.

### Mapping to Kinbank

[Kinbank](https://github.com/kinbank/kinbank) (Passmore et al. 2023) writes positions as strings of letters, which map directly onto the same
model: ego sex `m`/`f` is the anchor, and `F M B Z S D H W` are the eight links.
`e` or `y` before a letter gives relative age. Kinbank's general letters `P`
(parent), `C` (child), `G` (sibling) and `E` (spouse) correspond to `Pa`, `Ch`,
`Sb` and `Sp`. A Kinbank term matches a concept when the positions it is listed
under equal ⟦c⟧ exactly (see the Kinbank section of the README). In Kinbank, an
age outside the slot is ignored: `mFeBS` is treated as `mFBS`. Kinbank's
in-law positions with an age (`mHeB`, `meZH`) fall in the slots of the ES and SE
shapes.

### What the algebra does not cover

- **`Rel` and `InL`** have no set of positions: any relative, and any relative by
  marriage, at any distance. Their place in the hierarchy is stated by hand.
- **Positions are genealogical only.** Step-relations, adoption, half-siblings,
  social or classificatory uses, and register (*dad* vs *father*) are not features.
  See `docs/open-questions.md`.

## Features

### Anchor

| feature | meaning | example |
|---|---|---|
| `x` | the anchor is male | `x;Ss` "a man's sister" |
| `o` | the anchor is female | `o;Br` "a woman's brother" |

### Relative age

| feature | meaning | example |
|---|---|---|
| `El` | elder: older than the nearest earlier person on the path of the same generation (see the table of age slots) | `Fa;El:Br` "father's elder brother" |
| `Yn` | younger | `Yn:Ss` "younger sister" |

### Specific kin terms

| feature | link | example |
|---|---|---|
| `Fa` | father | `Fa;Fa` "paternal grandfather" |
| `Mo` | mother | `Mo;Br` "mother's brother" |
| `Br` | brother | `Br;So` "brother's son" |
| `Ss` | sister | `Ss;Hu` "sister's husband" |
| `So` | son | `So;Wi` "son's wife" |
| `Da` | daughter | `Da;Hu` "daughter's husband" |
| `Hu` | husband | `Hu;Fa` "husband's father" |
| `Wi` | wife | `Fa;Br;Wi` "father's brother's wife" |

### General kin terms

| feature | links | example |
|---|---|---|
| `Pa` | parent: `Fa` or `Mo` | `Pa;Sb;Ch` "first cousin" |
| `Sb` | sibling: `Br` or `Ss` | `Sb;Ch` "sibling's child" |
| `Ch` | child: `So` or `Da` | `Ch;Ch` "grandchild" |
| `Sp` | spouse: `Hu` or `Wi` | `Sp;Pa` "parent-in-law" |

### Abbreviations

| feature | stands for | example |
|---|---|---|
| `Pb` | parent's sibling, `Pa;Sb` | `Pb` "uncle or aunt" (KinDiv's *auncle*) |

### Named nodes

These are atomic names for concepts that sit above the grid. The four that are
unions have a set of positions; `Rel` and `InL` do not.

| feature | meaning | positions |
|---|---|---|
| `Rel` | relative: by blood or marriage; the root of the hierarchy | — |
| `InL` | in-law: a relative by marriage | — |
| `Unc` | uncle by blood or marriage (English *uncle*) | `Pa;Br \| Pa;Ss;Hu` |
| `Aun` | aunt by blood or marriage (English *aunt*) | `Pa;Ss \| Pa;Br;Wi` |
| `BrL` | brother-in-law | `Sp;Br \| Ss;Hu` |
| `SsL` | sister-in-law | `Sp;Ss \| Br;Wi` |

### Operators

| operator | meaning | example |
|---|---|---|
| `;` | composition: the next link outward (after `x`/`o`, the first link) | `Mo;Ss;Da` "mother's sister's daughter" |
| `:` | a modifier of the link it is attached to | `Fa;El:Br` "father's elder brother" |
| `\|` | union of codes | `Fa\|Fa;Br` "father or father's brother" |

In ids, `;` becomes `-`, `:` becomes `.` and `|` becomes `_`, so `Fa|Fa;El:Br` is
the synset `omw-kin-Fa_Fa-El.Br`. The `dc:identifier` is the code as it is
(`Fa|Fa;El:Br`).

### KinDiv's codes

KinDiv writes some codes differently, and `data/kindiv-codes.tsv` maps them to
ours when its files are read. KinDiv uses `Pr` for parent at the end of
grandparent codes (`Fa;Pr`) and `Gr` for the first link of a grandparent or
grandchild code (`Gr;Mo`, `Gr;Da`); both meant the same as `Pa` (or `Ch` for a
grandchild), so we write `Fa;Pa`, `Pa;Mo` and `Ch;Da`. KinDiv also writes a
relative age as a term of its own, before the term it modifies (`Fa;El;Br`) or,
for a cousin, at the front (`El;Fa;Br;So`); `from_kindiv` attaches it to its
link instead (`Fa;El:Br`, `Fa;Br;El:So`).

## References

Khishigsuren, Temuulen, Gábor Bella, Khuyagbaatar Batsuren, Abed Alhakim
Freihat, Nandu Chandran Nair, Amarsanaa Ganbold, Hadi Khalilia, Yamini
Chandrashekar and Fausto Giunchiglia (2022). Using linguistic typology to
enrich multilingual lexicons: the case of lexical gaps in kinship. In
*Proceedings of the Thirteenth Language Resources and Evaluation Conference*,
Marseille, France. European Language Resources Association.

Murdock, George P. (1970). Kin term patterns and their distribution. *Ethnology*
9(2): 165–208.

Passmore, Sam, et al. (2023). Kinbank: a global database of kinship
terminology. *PLOS ONE* 18(5): e0283218.
<https://doi.org/10.1371/journal.pone.0283218>
