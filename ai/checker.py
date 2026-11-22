"""The checker: no figure written by the model reaches the screen unless the engine gave it.

Pure code: no model, no network, the standard library and the two-language helper of the engine.

A *fact* is a number the engine gave, as it was shown to the model: its value with its sign, its unit class
(an amount in CHF, a percentage, an age, a number of months, a count) and where it comes from. The checker reads
every number of a text, in digits or in words, in English and in French, and accepts the text only if each one is
a fact of the same unit class, copied exactly. A text is also refused when it rounds ("about 43'000"), abbreviates
("43k"), states a ratio ("double", "half"), names a world that was not tested, or uses a word this project never
writes. A refused text is never shown: the model gets the list of what was refused and two more tries; after that
the screen shows the engine's facts alone.

Two things go beyond the presence of a figure. A label or a sentence the engine gave as it is (a line of the
ledger, the source of an assumption) is accepted when it is copied word for word, even if it holds "1/12" or "half".
And for three quantities the role of the number is checked: a number of goals next to "keep" must be the number of
goals kept in this world, next to "lose" the number lost, and an amount next to "borrow" or "finance" must be the
peak borrowing. In a sentence that says "with no crisis", the same words call for the figures of the route with no
crisis.

What the checker does not do: beyond these three, it does not judge the words around the figures. A sentence may
put a true figure in a wrong reasoning ("her net worth is 43'123 CHF" when that amount is what she borrows). It
guarantees where each figure comes from, not what is said about it. It reads digits, and words up to ninety-nine;
it does not read Roman numerals.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from engine import i18n
from engine.i18n import say

UNITS = ("chf", "percent", "points", "age", "years", "months", "count", "number")
# What a number written with no unit may be: a count, an age ("at 27"), or a number the engine itself wrote with no
# unit ("12 are required").
BARE = ("count", "age", "number")
YEARS = ("age", "years")       # "27 years", "27 ans": an age or a length, the wording does not say which
# The quantities whose role in a sentence is checked: goals kept, goals lost, peak borrowing. The goals kept and the
# peak borrowing have a twin for the route with no crisis, checked in the sentences that say "with no crisis". With no
# crisis no goal is lost, by definition: that one has no twin.
ROLES = ("kept", "lost", "borrowed", "kept_calm", "borrowed_calm")
ATTEMPTS = 3                   # the first text, then two more tries at most
_CLOSE = 1e-9                  # two numbers closer than this are the same number


# ----------------------------------------------------------------------------------------------- what the engine gave
def _number(value: float) -> str:
    """A number as the screen writes it: 50'100, −5'145, 24.8 (24,8 in French)."""
    whole, _, rest = f"{abs(value):.6f}".partition(".")
    rest = rest.rstrip("0")
    text = f"{int(whole):,}".replace(",", "'") + (say(".", ",") + rest if rest else "")
    return ("−" if value < 0 and text.strip("0.,") else "") + text


@dataclass(frozen=True)
class Fact:
    """A number the engine gave, as it was shown to the model."""
    value: float
    unit: str                      # one of UNITS
    origin: str                    # where it comes from, in words for the reader
    world: str | None = None       # the world it belongs to, when it belongs to one
    role: str | None = None        # one of ROLES, for the three quantities whose place in a sentence is checked

    def __post_init__(self):
        if self.unit not in UNITS:
            raise ValueError(f"Unknown unit '{self.unit}'. Units: {list(UNITS)}")
        if self.role is not None and self.role not in ROLES:
            raise ValueError(f"Unknown role '{self.role}'. Roles: {list(ROLES)}")
        object.__setattr__(self, "value", float(self.value))

    @classmethod
    def chf(cls, value: float, origin: str, world: str | None = None, role: str | None = None) -> "Fact":
        """An amount, rounded to the franc as the screen writes it."""
        return cls(float(round(value)), "chf", origin, world, role)

    @classmethod
    def percent(cls, value: float, origin: str, world: str | None = None) -> "Fact":
        """A percentage, in percent: 30 for 30%, not 0.3."""
        return cls(value, "percent", origin, world)

    @classmethod
    def points(cls, value: float, origin: str, world: str | None = None) -> "Fact":
        return cls(value, "points", origin, world)

    @classmethod
    def age(cls, value: float, origin: str, world: str | None = None) -> "Fact":
        return cls(value, "age", origin, world)

    @classmethod
    def years(cls, value: float, origin: str, world: str | None = None) -> "Fact":
        """A length in years. An age is `Fact.age`."""
        return cls(value, "years", origin, world)

    @classmethod
    def months(cls, value: float, origin: str, world: str | None = None) -> "Fact":
        return cls(value, "months", origin, world)

    @classmethod
    def count(cls, value: float, origin: str, world: str | None = None, role: str | None = None) -> "Fact":
        return cls(value, "count", origin, world, role)

    @classmethod
    def number(cls, value: float, origin: str, world: str | None = None) -> "Fact":
        """A number the engine wrote with no unit. It can be copied with no unit, and given none afterwards."""
        return cls(value, "number", origin, world)

    def written(self) -> str:
        """The fact as the model is shown it, in the current language. The checker reads this form back."""
        n, one, several = _number(self.value), abs(self.value) == 1, abs(self.value) >= 2
        if self.unit == "chf":
            return f"{n} CHF"
        if self.unit == "percent":
            return say(f"{n}%", f"{n} %")
        if self.unit == "points":
            return say(f"{n} point{'' if one else 's'}", f"{n} point{'s' if several else ''}")
        if self.unit == "months":
            return say(f"{n} month{'' if one else 's'}", f"{n} mois")
        if self.unit == "years":
            return say(f"{n} year{'' if one else 's'}", f"{n} an{'s' if several else ''}")
        if self.unit == "age":
            return say(f"age {n}", f"{n} ans")
        return n


@dataclass(frozen=True)
class Quote:
    """A label or a sentence the engine gave as it is: a line of the ledger, the source of an assumption. Copied word
    for word, it is accepted whole, even where it holds what the checker refuses elsewhere ("1/12", "half")."""
    text: str
    origin: str                    # where it comes from, in words for the reader
    world: str | None = None

    def __post_init__(self):
        if not re.search(r"[^\W\d_]", self.text):
            raise ValueError("A quote is a label or a sentence: a number alone is a fact, not a quote.")


# ------------------------------------------------------------------------------------------------- what a text says
@dataclass(frozen=True)
class Figure:
    """A number found in a text."""
    text: str                      # as written, with its sign and its unit: "−5'145 CHF"
    value: float                   # the value read, with its sign
    units: tuple[str, ...]         # the unit classes this writing may mean
    start: int
    end: int


@dataclass(frozen=True)
class Problem:
    kind: str                      # banned, ratio, approximation, abbreviation, unreadable, identifier, figure, role, empty
    text: str                      # the words refused
    message: str                   # why, for the model and for the reader


@dataclass(frozen=True)
class Reading:
    figures: tuple[Figure, ...]
    problems: tuple[Problem, ...]
    identifiers: tuple[str, ...]   # the identifiers written in the text: world ids such as krach@24+chomage_long@25


# Words this project never writes, in both languages, and the words that state a likelihood.
_BANNED = re.compile(r"\bchances?\b|\w*probabilit\w*|\w*probabl\w*|\w*likel\w*|\bodds\b|\brisk\w*|\w*risqu\w*|\bbest\b"
                     r"|\w*meilleur\w*|\w*recomm[ae]nd\w*|\badvi[cs]\w*|\w*conseil\w*|\bguarant\w*|\w*garanti\w*", re.IGNORECASE)
# A ratio is a figure the engine did not give: "double", "half", "a third", "la moitié".
_RATIO = re.compile(r"\bdoubl\w*|\btripl\w*|\bquadrupl\w*|\btwice\b|\bthrice\b|\bhal(?:f|ves|ved|ving|ve)\b"
                    r"|\b(?:two|three|four|five|ten|\d+)-?fold\b|\b(?:a|one|two|\d+)[ -]thirds?\b|\bthirds?\s+of\b"
                    r"|\b(?:a|one|three|\d+)[ -]quarters?\b|\bquarters?\s+of\b|\bmoitié\w*|\bdemie?s?\b|\bdemi-\w+"
                    r"|\b(?:un|deux|trois|le|les|du|des|au|aux|\d+)\s+(?:tiers|quarts?)\b"
                    r"|\b(?:an?|one|two|three|four|\d+)[ -](?:fourth|fifth|sixth|seventh|eighth|ninth|tenth|hundredth)s?\s+of\b"
                    r"|\b(?:two|three|four|\d+)[ -](?:fourths|fifths|sixths|sevenths|eighths|ninths|tenths)\b"
                    r"|\b(?:un|deux|trois|quatre|\d+)\s+(?:cinqui|sixi|septi|huiti|neuvi|dixi|centi)[èe]mes?\s+d[eu']"
                    r"|\bfactor of\b|\bfacteur\b|\bmultipli\w*|\bdivided by\b|\bdivisée?s? par\b|\bfois\s+(?:plus|moins)\b"
                    r"|\btimes\s+(?:as|more|less|higher|lower|bigger|smaller)\b", re.IGNORECASE)
# "3 times", "trois fois", "2x", "×2", "1/3": a ratio written with a number. The number is taken whole, and the
# letter "x" only counts when it is stuck to it.
_WHOLE = r"\d+(?:[ '’.,]\d+)*"
_MULTIPLE = re.compile(rf"(?<![\w.,'’@~])(?:{_WHOLE}|two|three|four|five|six|seven|eight|nine|ten|deux|trois|quatre|cinq|sept|huit"
                       rf"|neuf|dix)\s+(?:times|fois)\b|(?<![\w.,'’@~]){_WHOLE}(?:[x×]| ×)(?!\w)|(?<![\w@~+])(?:x|× ?){_WHOLE}(?![\w@~])"
                       rf"|(?<![\w.,'’/@~]){_WHOLE} ?/ ?{_WHOLE}(?![\w/])", re.IGNORECASE)
# A quantity that is not a number: "dozens", "une dizaine", "rounded".
_VAGUE = re.compile(r"\bdozens?\b|\ba couple of\b|\bhundreds\b|\bthousands\b|\bmillions\b|\btens of\b|\bmilliers?\b"
                    r"|\b(?:diz|douz|quinz|vingt|trent|quarant|cinquant|soixant|cent)aines?\b|\brounded\b|\brounding\b|\barrondi\w*",
                    re.IGNORECASE)
# What announces an approximation just before a number, or just after it.
_ABOUT_BEFORE = re.compile(r"(?:\babout|\baround|\bapprox(?:imately|\.)?|\broughly|\bnearly|\balmost|\bcirca|\bca\.|\bsome|\bclose to"
                           r"|\benviron|\bpresque|\bpr[èe]s d[e']|\bà peu pr[èe]s|\bapproximativement|\bautour d[e']|\bquelque"
                           r"|\bdans les|\bplus ou moins|\bplus or minus|\bmore or less|\bgive or take|~|≈|±)\s*$", re.IGNORECASE)
_ABOUT_AFTER = re.compile(r"\s*(?:or so\b|environ\b|approximately\b|approx\b|roughly\b|à peu pr[èe]s\b|-?ish\b|,? give or take\b"
                          r"|,? more or less\b|,? plus ou moins\b)", re.IGNORECASE)
# A number cut short: "43k", "43 thousand", "1.2 million", "43 mille".
_SHORT = re.compile(r"(?:k|m|mio|mia|mrd|bn)(?:chf)?(?![^\W\d_])| (?:k|mio|mia|mrd|bn)(?![^\W\d_])"
                    r"| ?(?:thousands?|millions?|billions?|mille|milliers?|milliards?)\b", re.IGNORECASE)
# A large number in words: the checker reads words up to ninety-nine and asks for digits beyond.
_LARGE = {"en": re.compile(r"\b(?:hundred|thousand|million|billion)\b", re.IGNORECASE),
          "fr": re.compile(r"(?<!pour )(?<!pour-)\b(?:cents?|mille|millions?|milliards?)\b", re.IGNORECASE)}
# An identifier: a word made like code (krach@24+chomage_long@25, chomage_6_mois). Its digits are not figures.
_IDENTIFIER = re.compile(r"(?<![\w@~+])[^\W\d]\w*(?:[@~]\d+)*(?:\+[^\W\d]\w*(?:[@~]\d+)*)*(?![\w@~])")
_LIST_MARKER = re.compile(r"(?m)^[ ]*\d+[.)](?=\s)")
# An ordinal states an order, not a quantity: "the second crisis", "la deuxième crise".
_ORDINAL = {"en": re.compile(r"(?<![\w-])(?:[\w-]*-)?(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth"
                             r"|\w+teenth|\w+tieth)(?!\w)", re.IGNORECASE),
            "fr": re.compile(r"(?<![\w-])(?:premi(?:er|ère)s?|seconde?s?|[\w-]*i[èe]mes?)(?!\w)", re.IGNORECASE)}
_ORDINAL_SUFFIX = {"en": re.compile(r"(?:st|nd|rd|th)(?![^\W\d_])", re.IGNORECASE),
                   "fr": re.compile(r"(?:ères?|ers?|èmes?|emes?|ndes?|nds?|re|e)(?![^\W\d_])", re.IGNORECASE)}

_GROUPED = r"\d{1,3}(?:[ '’]\d{3})+(?!\d)(?:[.,]\d+)?"          # 43'123, 43 123, 43'123.47
_DIGITS = {"en": re.compile(rf"{_GROUPED}|\d{{1,3}}(?:,\d{{3}})+(?!\d)(?:\.\d+)?|\d+(?:[.,]\d+)?"),      # and 43,123 in English
           "fr": re.compile(rf"{_GROUPED}|\d+(?:[.,]\d+)?")}

# What follows a number and says what it counts. One adjective may stand between the two: "the last 24 months".
_BETWEEN = {"en": r"(?:(?:consecutive|straight|full|whole|long|more|extra|additional|further|other|tested|first|last|next|previous|single)[ -])?",
            "fr": r"(?:(?:derni(?:er|ère)s?|premi(?:er|ère)s?|prochaine?s?|autres?|longs?|longues?|pleine?s?|enti(?:er|ère)s?|petite?s?|seule?s?)[ -])?"}
_AFTER = {
    "en": re.compile(r"[ -]?(?:(?P<chf>CHF\b|Swiss francs?\b|francs?\b)|(?P<pp>percentage points?\b)|(?P<percent>%|percent\b|per cent\b|pct\b)"
                     rf"|{_BETWEEN['en']}(?:(?P<months>months?\b)|(?P<years>years?(?:[- ]old)?\b|yrs?\b)|(?P<points>points?\b|pts?\b)"
                     r"|(?P<count>(?:goals?|stations?|doors?|worlds?|crises|crisis|junctions?|branch(?:es)?|routes?|calls?|tests?"
                     r"|evaluations?|attempts?|spells?|shocks?|periods?)\b)))", re.IGNORECASE),
    "fr": re.compile(r"[ -]?(?:(?P<chf>CHF\b|francs?(?: suisses?)?\b)|(?P<pp>points? de pourcentage\b)|(?P<percent>%|pour[- ]cent\b|pourcent\b)"
                     rf"|{_BETWEEN['fr']}(?:(?P<months>mois\b)|(?P<years>ans?\b|années?\b)|(?P<points>points?\b)"
                     r"|(?P<count>(?:objectifs?|stations?|portes?|mondes?|crises?|gares?|branches?|trajets?|appels?|tests?"
                     r"|évaluations?|tentatives?|périodes?|chocs?)\b)))", re.IGNORECASE),
}
_UNITS_OF = {"chf": ("chf",), "pp": ("points",), "percent": ("percent",), "months": ("months",), "years": YEARS, "points": ("points",),
             "count": ("count",)}
_TIMES_AFTER = re.compile(r" (?:times|fois)\b", re.IGNORECASE)          # "twenty times": a ratio, whatever the number
# "2 of 6", "2 out of 6", "2 sur 6", "2 des 6": both numbers are counts.
_OF_AFTER = re.compile(r" (?:out of|of|sur|des|d'entre)\b", re.IGNORECASE)
_THE = {"en": "the|her|its|your|my|their|these|those", "fr": "les|ses|ces|tes|mes|vos|nos|leurs"}          # what may stand before a number of goals: "the 6", "your 6", "tes 6"
_OF_BEFORE = re.compile(rf"\b(?:out of|of|sur|des|d'entre|de)\s+(?:(?:{_THE['en']}|{_THE['fr']})\s+)?$", re.IGNORECASE)
_CHF_BEFORE = re.compile(r"\bCHF ?$", re.IGNORECASE)


def _words(lang: str) -> dict[str, int]:
    """The numbers from zero to ninety-nine as each language writes them, words separated by one space."""
    if lang == "en":
        units = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
                 "seventeen eighteen nineteen").split()
        out = {word: value for value, word in enumerate(units)}
        for ten, word in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split(), start=2):
            out[word] = 10 * ten
            out.update({f"{word} {units[unit]}": 10 * ten + unit for unit in range(1, 10)})
        return out
    units = "zéro un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze seize".split()
    units += ["dix sept", "dix huit", "dix neuf"]
    out = {word: value for value, word in enumerate(units)} | {"zero": 0, "une": 1}
    tens = {"vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60,
            "septante": 70, "huitante": 80, "octante": 80, "nonante": 90}                      # the last four are Swiss and Belgian
    for word, value in tens.items():
        out[word] = value
        out.update({f"{word} et un": value + 1, f"{word} et une": value + 1, f"{word} un": value + 1})
        out.update({f"{word} {units[unit]}": value + unit for unit in range(2, 10)})
    out.update({f"soixante {units[unit]}": 60 + unit for unit in range(10, 20)} | {"soixante et onze": 71})
    out.update({"quatre vingt": 80, "quatre vingts": 80} | {f"quatre vingt {units[unit]}": 80 + unit for unit in range(1, 20)})
    return out


_NUMBER_WORDS = {lang: _words(lang) for lang in ("en", "fr")}
_WORD_FORMS = {lang: re.compile(r"(?<![\w-])(?:" + "|".join(r"[\s-]+".join(map(re.escape, form.split()))
                                                              for form in sorted(words, key=len, reverse=True)) + r")(?!\w)", re.IGNORECASE)
               for lang, words in _NUMBER_WORDS.items()}
# "one", "a", "un" and "une" are also plain words. They are read as the figure 1 only where they measure something:
# a length of time ("a year", "un mois"), the first term of a proportion ("one of the six goals", "un objectif sur
# six") or, in English, a count of goals ("one goal").
_ALONE = {"en": {"one"}, "fr": {"un", "une"}}
_GOALS = {"en": r"(?:goals?|stations?|doors?|worlds?|crises|crisis|junctions?|branch(?:es)?)",
          "fr": r"(?:objectifs?|stations?|portes?|mondes?|crises?|gares?|branches?)"}
_FEW = {"en": r"(?:\d|(?:two|three|four|five|six|seven|eight|nine|ten)\b)", "fr": r"(?:\d|(?:deux|trois|quatre|cinq|six|sept|huit|neuf|dix)\b)"}
_ONE = {"en": re.compile(rf"(?<![\w-])(?:one|an?)(?=[ -](?:(?:full|whole|more|extra|additional|further|long) )?(?:year|month)s?\b)"
                         rf"|(?<![\w-])one(?= (?:{_GOALS['en']} )?(?:out of|of|in) (?:(?:{_THE['en']}) )?(?:{_FEW['en']}|{_GOALS['en']}\b))"
                         rf"|(?<![\w-])one(?= {_GOALS['en']}\b)", re.IGNORECASE),
        "fr": re.compile(rf"(?<![\w-])une?(?=[ -](?:(?:seule?|longue?|petite?) )?(?:an|mois|année)\b)"
                         rf"|(?<![\w-])une?(?= (?:seule? )?(?:{_GOALS['fr']} )?sur (?:(?:{_THE['fr']}) )?{_FEW['fr']})"
                         rf"|(?<![\w-])une?(?= (?:des|d'entre|de) (?:(?:{_THE['fr']}) )?(?:{_FEW['fr']} )?{_GOALS['fr']}\b)", re.IGNORECASE)}


# The three quantities whose role is checked. A number of goals next to "keep" must be the number of goals kept in
# this world; next to "lose", the number lost; an amount next to "borrow" or "finance", the peak borrowing.
_ROLE_WORDS = {
    "kept": re.compile(r"\bkeep(?:s|ing)?\b|\bkept\b|\bhold(?:s|ing)?\b|\bheld\b"
                       r"|\bgard(?:e[sz]?|ent|é(?:e|s|es)?|er|ai[st]|aient|era(?:it)?|ant)\b|\btien(?:s|t|nent)\b|\btenu(?:e|s|es)?\b", re.IGNORECASE),
    "lost": re.compile(r"\blos(?:e|es|ing)\b|\blost\b|\bperd(?:s|ent|u(?:e|s|es)?|re|ai[st]|aient|ra(?:it)?|ant)?\b", re.IGNORECASE),
    "borrowed": re.compile(r"\bborrow\w*|\bemprunt\w*|\bfinanc(?:e[sd]?|ing|ent|é(?:e|s|es)?|er|ements?)\b", re.IGNORECASE),
}
# "2 goals", "2 of the 6 goals", "2 des 6 objectifs": what makes a count a number of goals.
_GOALS_AFTER = {"en": re.compile(rf"(?: (?:out of|of)(?: (?:{_THE['en']}))?(?: \w+)?)?(?: (?:other|more|tested|single))? (?:goals?|stations?|doors?)\b",
                                 re.IGNORECASE),
                "fr": re.compile(rf"(?: (?:des|sur|de|d'entre)(?: (?:{_THE['fr']}))?(?: \w+)?)?(?: (?:autres?|seule?s?))? (?:objectifs?|stations?|portes?)\b",
                                 re.IGNORECASE)}
# "of the 6", "sur 6", "de ses 3": the whole a part is taken from. It is never the number kept or lost.
_PART_OF = _OF_BEFORE
# A sentence that says "with no crisis" speaks of the route with no crisis: the number next to "keep" is then the number
# of goals kept with no crisis, not the number kept in the world the text explains.
_NO_CRISIS = re.compile(r"\b(?:with no|without(?: a| any)?)\s+(?:crisis|crises|shocks?)\b|\bsans\s+(?:aucune?\s+)?(?:crises?|chocs?)\b"
                        r"|\breference world\b|\bmonde de r[ée]f[ée]rence\b", re.IGNORECASE)
_SENTENCE_END = re.compile(r"[;!?\n]|\.(?=\s+[^\W\d_a-zà-ÿ]|\s*$)")
# What ends a clause: a number and a word on either side of it do not belong together. "max." does not end one.
_BREAK = re.compile(r"[;!?\n(),]|\s[–—-]\s|\.(?=\s+[^\W\d_a-zà-ÿ]|\s*$)")
_SMALL = frozenset("only just exactly still all her the its your my a are is were was be been being have has had will would "
                   "que qu seulement encore toujours exactement ses les tes mes sont est ont été sera seront plus en ne n".split())
# The words that may stand between a number and the word that names it, when the number comes first: "2 goals are lost".
_LINK = {"kept": frozenset("are is were was be been being have has had still she that which sont est ont a été encore toujours elle qu que".split()),
         "borrowed": frozenset("to of in are is were was be been à a de d en sont est été".split())}
_LINK["lost"] = _LINK["kept"]
# After "keep" or "lose", "a goal", "no goal", "un objectif", "aucun objectif" state a number of goals: 1 or 0.
_ROLE_ONE = {
    "en": re.compile(r"\b(?:keep(?:s|ing)?|kept|hold(?:s|ing)?|held|los(?:e|es|ing)|lost)\s+(?:(?:only|just|exactly)\s+)?(an?|no|none)"
                     rf"(?=\s+(?:of\s+(?:{_THE['en']})\s+(?:\w+\s+)?)?(?:(?:single|other)\s+)?(?:goals?|stations?|doors?)\b|\s*(?:[.,;!?)]|$))",
                     re.IGNORECASE),
    "fr": re.compile(r"\b(?:gard\w*|perd\w*|tien(?:s|t|nent)|tenu\w*)\s+(?:(?:que|seulement|encore)\s+|qu['’])?(une?|aucune?)"
                     rf"(?=\s+(?:seule?\s+)?(?:de\s+(?:{_THE['fr']})\s+|des\s+)?(?:\w+\s+)?(?:objectifs?|stations?|portes?)\b|\s*(?:[.,;!?)]|$))",
                     re.IGNORECASE)}


def _flat(text: str) -> str:
    """The text with every kind of space written as a plain space. Same length: positions do not move."""
    return text.translate(dict.fromkeys(map(ord, "\u00a0\u202f\u2009\u2007\t"), " "))


def _sign(text: str, start: int) -> tuple[int, int]:
    """The sign written just before a number, and where it starts. "23-24" is a range and "sub-30" a word: no sign there."""
    at = start - 1
    if at >= 1 and text[at] == " " and text[at - 1] == "−":         # a true minus sign, then a space: "− 30 %"
        at -= 1
    if at < 0 or text[at] not in "-−–+":
        return 1, start
    before = text[at - 1] if at > 0 else " "
    if before.isalnum() or before in "'’%)]":
        return 1, start
    return (1 if text[at] == "+" else -1), at


def _value(token: str, lang: str) -> float:
    token = re.sub(r"[ '’]", "", token)
    if lang == "en" and re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", token):
        token = token.replace(",", "")
    return float(token.replace(",", "."))


def _refusal(kind: str, words: str) -> str:
    """Why these words are refused whatever the facts are."""
    if kind == "ratio":
        return say(f"“{words}” is a ratio: the engine gave no such figure. Use the engine's own figures.",
                   f"« {words} » est un rapport : le moteur n'a pas donné ce chiffre. Reprends les chiffres du moteur.")
    if kind == "approximation":
        return say(f"“{words}” is an approximation: write the engine's figure exactly, or leave it out.",
                   f"« {words} » est une approximation : écris le chiffre du moteur exactement, ou enlève-le.")
    if kind == "abbreviation":
        return say(f"“{words}” is abbreviated: write the figure in full, as the engine gave it.",
                   f"« {words} » est abrégé : écris le chiffre en entier, tel que le moteur l'a donné.")
    if kind == "banned":
        return say(f"“{words}” is a word this project never writes.", f"« {words} » est un mot que ce projet n'écrit jamais.")
    return say(f"“{words}” cannot be read as an exact figure: write it in digits, as the engine gave it.",
               f"« {words} » ne se lit pas comme un chiffre exact : écris-le en chiffres, tel que le moteur l'a donné.")


def read(text: str, lang: str | None = None) -> Reading:
    """Every number of a text, in digits or in words, with the unit classes its writing may mean; the identifiers
    written in it; and what cannot be accepted whatever the facts are (a ratio, an approximation, a banned word)."""
    lang = lang or i18n.current()
    with i18n.use(lang):
        return _read(text, lang)


def _read(text: str, lang: str) -> Reading:
    flat = _flat(text)
    left = list(flat)                       # what is still to read: every part already understood is blanked out
    figures: list[Figure] = []
    problems: list[Problem] = []
    identifiers: list[str] = []

    def blank(start: int, end: int) -> None:
        left[start:end] = "\x00" * (end - start)

    def refuse(kind: str, words: str) -> None:
        words = words.strip()
        if not any(problem.kind == kind and problem.text == words for problem in problems):
            problems.append(Problem(kind, words, _refusal(kind, words)))

    def add(start: int, end: int, value: float, signed: bool = True) -> None:
        """A number read between `start` and `end`: its sign, its unit, and whether it is announced as approximate."""
        sign, first = _sign(flat, start) if signed else (1, start)
        units, last = BARE, end
        unit = _AFTER[lang].match(flat, end)
        if unit:
            units = _UNITS_OF[unit.lastgroup]
            last = end if unit.lastgroup == "count" else unit.end()
        elif _OF_AFTER.match(flat, end):
            units = ("count",)
        money = _CHF_BEFORE.search(flat, 0, first)
        if money and units == BARE:                                 # "CHF 43,123", "−CHF 5,145"
            units = ("chf",)
            if sign == 1 and signed:
                sign = _sign(flat, money.start())[0]
            first = _sign(flat, money.start())[1]
        elif units == BARE and _OF_BEFORE.search(flat, 0, first):
            units = ("count",)
        before, after = _ABOUT_BEFORE.search(flat, max(0, first - 28), first), _ABOUT_AFTER.match(flat, last)
        if before or after:
            refuse("approximation", flat[before.start() if before else first:after.end() if after else last])
        times = _TIMES_AFTER.match(flat, last)
        if times:
            refuse("ratio", flat[first:times.end()])
        figures.append(Figure(flat[first:last], sign * value, units, first, last))
        blank(first, last)

    # 1. What is not a figure: the numbers of a numbered list ("1.", "2."), and the digits inside an identifier.
    # 2. A ratio, with a number ("3 times", "2x", "1/3") or in a word ("double", "two-thirds"): read before the
    # numbers, so that its own number is not read a second time. "x2" is a ratio, not an identifier.
    def ratios(pattern: re.Pattern) -> None:
        for found in pattern.finditer("".join(left)):
            refuse("ratio", flat[found.start():found.end()])
            blank(*found.span())

    markers = list(_LIST_MARKER.finditer(flat))
    if [int(marker.group(0).strip(" .)")) for marker in markers] == list(range(1, len(markers) + 1)):
        for marker in markers:                                           # 1., 2., 3.: a list. "27." at the start of a line is not one
            blank(*marker.span())
    ratios(_MULTIPLE)
    for found in _IDENTIFIER.finditer("".join(left)):
        token = found.group(0)
        if re.search(r"[_@~\d]", token.strip("_")) and not re.fullmatch(r"CHF\d+", token, re.IGNORECASE):
            identifiers.append(token)
            blank(*found.span())
    ratios(_RATIO)

    # 3. The numbers written in digits. Nothing made of digits is skipped: what cannot be read safely is refused.
    scan, at = "".join(left), 0
    while at < len(scan):
        found = _DIGITS[lang].match(scan, at) if re.match(r"\d", scan[at]) else None
        if not found:
            at += 1
            continue
        end, tail = found.end(), flat[found.end():]
        if at and scan[at - 1] in ".," and (at == 1 or not scan[at - 2].isalnum()):     # ".5": no whole part, no safe reading
            refuse("unreadable", flat[at - 1:end])
        elif re.match(r"[.,'’]?\d", scan[end:end + 2]):                  # "1'23", "1.234.567": no safe reading either
            end += re.match(r"(?:[.,'’]?\d)+", scan[end:]).end()
            refuse("unreadable", flat[at:end])
        elif _AFTER[lang].match(flat, end):                              # "30%", "12-month", "43'123 CHF"
            add(at, end, _value(found.group(0), lang))
        elif _SHORT.match(tail):                                         # "43k", "43 thousand"
            end += _SHORT.match(tail).end()
            refuse("abbreviation", flat[_sign(flat, at)[1]:end])
        elif _ORDINAL_SUFFIX[lang].match(tail):                          # "2nd", "2e": a number like another
            end += _ORDINAL_SUFFIX[lang].match(tail).end()
            figures.append(Figure(flat[at:end], _value(found.group(0), lang), BARE, at, end))
        elif re.match(r"[^\W\d_]", tail):                                # "12mo", "1e5": letters stuck to the digits
            end += re.match(r"\w*", tail).end()
            refuse("unreadable", flat[at:end])
        else:
            add(at, end, _value(found.group(0), lang))
        blank(at, end)
        at = end
    for char in sorted(set(flat)):
        if char.isnumeric() and not re.match(r"\d", char) or char in "‰‱":      # "½", "²", "①", and per mille
            refuse("unreadable", char)

    # 4. The numbers written in words, up to ninety-nine. An ordinal is not a figure.
    for found in _ORDINAL[lang].finditer("".join(left)):
        blank(*found.span())
    for found in _WORD_FORMS[lang].finditer("".join(left)):
        form = " ".join(re.split(r"[\s-]+", found.group(0).lower()))
        if form not in _ALONE[lang]:
            add(found.start(), found.end(), float(_NUMBER_WORDS[lang][form]), signed=False)
    for found in _ONE[lang].finditer(flat):                               # what follows it is read in the text as written
        if "\x00" not in left[found.start():found.end()]:
            add(found.start(), found.end(), 1.0, signed=False)
    for found in _ROLE_ONE[lang].finditer(flat):                          # "keeps a goal", "ne garde aucun objectif"
        start, end = found.span(1)
        if "\x00" not in left[start:end]:
            add(start, end, 0.0 if found.group(1).lower() in ("no", "none", "aucun", "aucune") else 1.0, signed=False)
    for found in _LARGE[lang].finditer("".join(left)):
        refuse("unreadable", found.group(0))

    # 5. What no fact can make right: a vague quantity, a word this project never writes.
    for found in _VAGUE.finditer("".join(left)):
        refuse("approximation", found.group(0))
    for found in _BANNED.finditer(flat):
        refuse("banned", found.group(0))
    figures.sort(key=lambda figure: figure.start)
    return Reading(tuple(figures), tuple(problems), tuple(identifiers))


def facts_in(text: str, origin: str, world: str | None = None, lang: str | None = None) -> list[Fact]:
    """Every number of a sentence that is itself a source: a note of the ledger, the name of a world, or what Alexia
    typed. A number is registered as it is written, so it can be copied and not turned into something else: "12 months"
    stays a number of months, and a number written with no unit ("12 are required") can only be copied with no unit."""
    return [Fact(figure.value, unit, origin, world) for figure in read(text, lang).figures
            for unit in (("number",) if figure.units == BARE else figure.units)]


# ------------------------------------------------------------------------------------------------------ the verdict
@dataclass(frozen=True)
class Verified:
    """A figure of the text, and where the engine gave it."""
    text: str
    value: float
    unit: str
    origins: tuple[str, ...]


def rejected_label() -> str:
    return say("AI explanation rejected by the checker", "Explication de l'IA rejetée par le contrôleur")


@dataclass(frozen=True)
class Report:
    figures: tuple[Verified, ...]      # the figures of the text that the engine gave
    problems: tuple[Problem, ...]      # what was refused; empty when the text is accepted
    identifiers: tuple[str, ...]       # the worlds named in the text

    @property
    def ok(self) -> bool:
        return not self.problems

    def label(self) -> str:
        """What the screen writes next to the text: how many figures were verified, or that the text was rejected."""
        if not self.ok:
            return rejected_label()
        n = len(self.figures)
        if n == 0:
            return say("✓ No figure to verify", "✓ Aucun chiffre à vérifier")
        return say(f"✓ {n} figure{'' if n == 1 else 's'} verified", f"✓ {n} chiffre{'' if n == 1 else 's'} vérifié{'' if n == 1 else 's'}")

    def feedback(self) -> str:
        """What the model is told after a refusal: the rule, then each thing refused."""
        if self.ok:
            return ""
        rule = say("The checker refused this text. Copy every figure exactly as the engine gave it, with its sign and its unit. "
                   "No rounding, no ratio, no figure of your own.",
                   "Le contrôleur a refusé ce texte. Recopie chaque chiffre tel que le moteur l'a donné, avec son signe et son unité. "
                   "Ni arrondi, ni rapport, ni chiffre de ton cru.")
        return "\n".join([rule] + [f"- {problem.message}" for problem in self.problems])

    def as_dict(self) -> dict:
        """For the screen: the count, then each figure with where the engine gave it. Of a refused text, only the kinds
        of refusal: its words are not shown."""
        figures = [{"text": f.text, "value": f.value, "unit": f.unit, "origins": list(f.origins)} for f in self.figures] if self.ok else []
        return {"ok": self.ok, "label": self.label(), "verified": len(figures), "figures": figures,
                "refused": sorted({problem.kind for problem in self.problems})}


def _same(a: float, b: float) -> bool:
    return abs(a - b) < _CLOSE


def _hint(figure: Figure, facts: list[Fact], elsewhere: list[Fact]) -> str:
    """What to add to a refusal when a fact comes close: the same number with another sign, in another world, with
    another unit, or rounded."""
    mine = [fact for fact in facts if fact.unit in figure.units]
    for fact in mine:
        if figure.value and _same(fact.value, -figure.value):
            return say(f" The engine gave {fact.written()}: keep its sign.", f" Le moteur a donné {fact.written()} : garde son signe.")
    for fact in elsewhere:
        if fact.unit in figure.units and _same(fact.value, figure.value):
            where = fact.world or fact.origin
            return say(f" It is a figure of another world ({where}), not of this one.", f" C'est un chiffre d'un autre monde ({where}), pas de celui-ci.")
    for fact in facts:
        if fact.unit not in figure.units and _same(fact.value, figure.value):
            return say(f" The engine gave {fact.written()} ({fact.origin}): the same number, with another unit.",
                       f" Le moteur a donné {fact.written()} ({fact.origin}) : le même nombre, avec une autre unité.")
    for fact in mine:
        rounded = abs(fact.value) >= 10 and any(_same(round(fact.value, -k), figure.value) for k in range(1, 6))
        if rounded or 0 < abs(fact.value - figure.value) <= 0.02 * abs(fact.value):
            return say(f" It looks like a rounding of {fact.written()}: copy it exactly.", f" On dirait un arrondi de {fact.written()} : recopie-le exactement.")
    return ""


def _copied(flat: str, quotes: list[Quote]) -> list[tuple[int, int, Quote]]:
    """Where a text copies a quote word for word. The kind of space, the kind of apostrophe and capital letters do not
    count, and the final full stop of the quote may be left out. A changed word makes it an ordinary text again."""
    found: list[tuple[int, int, Quote]] = []
    for quote in sorted(quotes, key=lambda quote: -len(quote.text)):
        words = _flat(quote.text).replace("’", "'").strip().rstrip(".").strip()
        pattern = r"(?<!\w)" + re.escape(words).replace("\\ ", r"\s+").replace("'", "['’]") + r"(?!\w|[.,'’]\d)"
        for match in re.finditer(pattern, flat, re.IGNORECASE):
            if not any(match.start() < end and start < match.end() for start, end, _ in found):
                found.append((match.start(), match.end(), quote))
    return sorted(found, key=lambda place: place[0])


def _misplaced(flat: str, figures: tuple[Figure, ...], facts: list[Fact], lang: str) -> tuple[dict[int, Problem], dict[int, str]]:
    """For the three quantities with a role: the number standing next to the word that names the quantity has to be that
    quantity. Next to: in the same clause, three words away at most. When two words could claim the same number, the
    nearest takes it. In a sentence that says "with no crisis", the quantity is the one of the route with no crisis.
    Returns the refusals, and the roles confirmed, both by position of the figure."""
    wanted = {role: [fact for fact in facts if fact.role == role] for role in ROLES}
    breaks = [found.start() for found in _BREAK.finditer(flat)]
    ends = [found.start() for found in _SENTENCE_END.finditer(flat)]
    sentence = lambda position: sum(end < position for end in ends)
    calm = {sentence(found.start()) for found in _NO_CRISIS.finditer(flat)}
    pairs = []
    for name in _ROLE_WORDS:
        for word in _ROLE_WORDS[name].finditer(flat):
            role = f"{name}_calm" if sentence(word.start()) in calm else name
            if not wanted.get(role):                    # no fact carries this role: nothing can be said of the place of a number
                continue
            for index, figure in enumerate(figures):
                end, counted = figure.end, True
                if name == "borrowed":
                    if figure.units != ("chf",):
                        continue
                else:
                    if "count" not in figure.units or _PART_OF.search(flat, 0, figure.start):
                        continue
                    goals = _GOALS_AFTER[lang].match(flat, figure.end)
                    end, counted = (goals.end(), True) if goals else (figure.end, False)
                if end <= word.start():
                    low, high, first = end, word.start(), True                 # the number comes first: "2 goals are lost"
                elif word.end() <= figure.start:
                    low, high, first = word.end(), figure.start, False          # the word comes first: "she loses 2 goals"
                else:
                    continue
                between = flat[low:high]
                words = [w.lower() for w in re.findall(r"[^\W\d_]+", between)]
                if any(low <= at < high for at in breaks) or len(words) > 3 or first and any(w not in _LINK[name] for w in words):
                    continue
                if not counted and any(w not in _SMALL for w in words):         # a bare number counts goals only right next to the verb
                    continue
                if name == "borrowed" and first and {"to", "à"} & set(words) and re.match(r"\s+[^\W\d_]", flat[word.end():]):
                    continue                                                    # "73'940 CHF to finance her master's": a purpose
                pairs.append((len(words), len(between), role, word.start(), word.group(0), index))
    named, claimed, out = set(), {}, {}
    for _, _, role, at, said, index in sorted(pairs):
        if (role, at) in named or index in claimed:
            continue
        named.add((role, at))
        claimed[index] = role
        figure, fact = figures[index], wanted[role][0]
        if not any(_same(fact.value, figure.value) for fact in wanted[role]):
            what = {"kept": say("the number of goals kept in this world is", "le nombre d'objectifs gardés dans ce monde est"),
                    "lost": say("the number of goals lost in this world is", "le nombre d'objectifs perdus dans ce monde est"),
                    "borrowed": say("the peak borrowing of this world is", "l'emprunt maximal de ce monde est"),
                    "kept_calm": say("the number of goals kept with no crisis is", "le nombre d'objectifs gardés sans crise est"),
                    "borrowed_calm": say("the peak borrowing with no crisis is", "l'emprunt maximal sans crise est")}[role]
            where = say(" in a sentence about the route with no crisis", " dans une phrase qui parle du trajet sans crise") if role.endswith("_calm") else ""
            # The usual slip: the figure of the route with no crisis, written in the sentence about this world.
            aside = "" if role.endswith("_calm") or not any(_same(twin.value, figure.value) for twin in wanted.get(f"{role}_calm", ())) else say(
                " To give the figure of the route with no crisis, write it in a sentence of its own that says “with no crisis”.",
                " Pour donner le chiffre du trajet sans crise, écris-le dans une phrase à part qui dit « sans crise ».")
            out[index] = Problem("role", figure.text, say(f"“{figure.text}” stands next to “{said}”{where}: {what} {fact.written()}.{aside}",
                                                          f"« {figure.text} » est à côté de « {said} »{where} : {what} {fact.written()}.{aside}"))
    return out, claimed


def check(text: str, facts: Iterable[Fact | Quote], identifiers: Iterable[str] = (), elsewhere: Iterable[Fact | Quote] = (),
          lang: str | None = None) -> Report:
    """Compares a text with what it may use: facts, and quotes (sentences of the engine it may copy word for word).
    `identifiers`: the worlds it may name. `elsewhere`: the facts of the other worlds, used only to say "this figure
    belongs to another world". `lang`: the language of the text."""
    given, identifiers, lang = list(facts), list(identifiers), lang or i18n.current()
    facts, quotes = [item for item in given if isinstance(item, Fact)], [item for item in given if isinstance(item, Quote)]
    elsewhere = [item for item in elsewhere if isinstance(item, Fact)]
    with i18n.use(lang):
        # A sentence of the engine copied word for word is set apart: its figures are the engine's, and what it says is
        # not read again. The rest of the text is read as usual.
        flat = _flat(text)
        copied = _copied(flat, quotes)
        rest = list(flat)
        for start, end, _ in copied:
            rest[start:end] = "\x00" * (end - start)
        reading = _read("".join(rest), lang)
        problems = list(reading.problems)
        placed: list[tuple[int, Verified]] = []
        for start, end, quote in copied:
            inside = _read(flat[start:end], lang)
            placed += [(start + figure.start, Verified(figure.text, figure.value, figure.units[0], (quote.origin,))) for figure in inside.figures]
            problems += [problem for problem in inside.problems if problem.kind == "banned" and problem not in problems]
        if not text.strip():
            problems.append(Problem("empty", "", say("The text is empty.", "Le texte est vide.")))
        # A world may be named whole, by one of its crises, or with its two crises in the other order.
        whole = lambda identifier: "+".join(sorted(identifier.split("+")))
        allowed = {whole(identifier) for identifier in identifiers} | {part for identifier in identifiers for part in identifier.split("+")}
        for identifier in reading.identifiers:
            if whole(identifier) not in allowed:
                problems.append(Problem("identifier", identifier, say(f"“{identifier}” is not one of the worlds tested here.",
                                                                       f"« {identifier} » n'est pas un des mondes testés ici.")))
        misplaced, roles = _misplaced("".join(rest), reading.figures, facts, lang)
        for index, figure in enumerate(reading.figures):
            found = [fact for fact in facts if fact.unit in figure.units and _same(fact.value, figure.value)]
            if index in roles:                           # "keeps 1 goal": the 1 comes from the goals kept, not from another count of 1
                found = [fact for fact in found if fact.role == roles[index]] or found
            if index in misplaced:                       # the right kind of number, or not, in the wrong place
                problems.append(misplaced[index])
            elif found:
                placed.append((figure.start, Verified(figure.text, figure.value, found[0].unit, tuple(dict.fromkeys(fact.origin for fact in found)))))
            else:
                message = say(f"“{figure.text}” is not a figure the engine gave for this text.",
                              f"« {figure.text} » n'est pas un chiffre que le moteur a donné pour ce texte.")
                problems.append(Problem("figure", figure.text, message + _hint(figure, facts, elsewhere)))
        return Report(tuple(verified for _, verified in sorted(placed, key=lambda place: place[0])), tuple(problems), reading.identifiers)


# ------------------------------------------------------------------------------------------ refusal, and trying again
@dataclass(frozen=True)
class Outcome:
    """What becomes of one text after the checker: accepted with its report, or rejected after every attempt.
    A refused text is never kept here: only the reports of the attempts are."""
    text: str | None                   # the accepted text; None when every attempt was refused
    report: Report | None              # the report of the accepted text
    attempts: tuple[Report, ...]       # one report per attempt, in order

    @property
    def accepted(self) -> bool:
        return self.text is not None

    def label(self) -> str:
        return self.report.label() if self.accepted else rejected_label()

    def as_dict(self) -> dict:
        """For the screen: the accepted text with its verified figures, or nothing but the label of the rejection.
        `refusals`: for each refused attempt, the kinds of refusal. The words of a refused text are not kept."""
        shown = self.report.as_dict() if self.accepted else {"label": rejected_label(), "verified": 0, "figures": []}
        return {"accepted": self.accepted, "text": self.text, "label": shown["label"], "verified": shown["verified"],
                "figures": shown["figures"], "attempts": len(self.attempts),
                "refusals": [sorted({problem.kind for problem in report.problems}) for report in self.attempts if not report.ok]}


def supervise(write: Callable[[dict[str, str] | None], Mapping[str, str]], facts: Mapping[str, Iterable[Fact | Quote]],
              common: Iterable[Fact | Quote] = (), identifiers: Iterable[str] = (), lang: str | None = None,
              attempts: int = ATTEMPTS) -> dict[str, Outcome]:
    """Asks for one text per key (one per world), checks each against the facts of its own key, and asks again for the
    refused ones only, with what was refused: `attempts` times in all. `write(feedback)` returns the texts; `feedback`
    is None the first time, then maps each refused key to what the checker said. `common`: the facts every text may use.
    A text accepted once is kept; a text still refused at the end comes out as None, and the caller shows the engine's
    facts alone."""
    facts = {key: list(mine) for key, mine in facts.items()}
    common, identifiers, lang = list(common), list(identifiers), lang or i18n.current()
    reports: dict[str, list[Report]] = {key: [] for key in facts}
    accepted: dict[str, str] = {}
    feedback = None
    for _ in range(attempts):
        texts = write(feedback)
        feedback = {}
        for key in facts:
            if key in accepted:
                continue
            others = [fact for other, theirs in facts.items() if other != key for fact in theirs]
            text = texts.get(key)
            report = check(text if isinstance(text, str) else "", facts[key] + common, identifiers, others, lang)
            reports[key].append(report)
            if report.ok:
                accepted[key] = text
            else:
                with i18n.use(lang):                    # what the model is told is written in the language of its text
                    feedback[key] = report.feedback()
        if not feedback:
            break
    return {key: Outcome(accepted.get(key), reports[key][-1] if key in accepted else None, tuple(reports[key])) for key in facts}
