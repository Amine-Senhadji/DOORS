"""The checker (ai/checker.py): no figure written by the model reaches the screen unless the engine gave it.

No test here calls a model or the network. The checker is pure code; the texts it reads are written by hand, with
the real figures of the engine for the demo route in its hardest single crisis (twelve months of unemployment at 27).
"""
from __future__ import annotations

import ast
import unicodedata
import unittest
from pathlib import Path

from ai import checker
from ai.checker import ATTEMPTS, BARE, UNITS, YEARS, Fact, Quote, check, facts_in, read, supervise
from engine import i18n
from engine.explore import doors_of, margins_of
from engine.simulate import load_scenario
from engine.tree import Tree

try:
    from fastapi.testclient import TestClient
    from api.main import app
    import test_english
except ImportError:  # pragma: no cover
    TestClient = None

ROOT = Path(__file__).resolve().parents[1]
ALEXIA = load_scenario(ROOT / "engine/scenarios/alexia.json")
STORY = [{"block": "job", "years": 5}, {"block": "master", "years": 2}, {"block": "job", "years": 3}]
WORLD = "chomage_long@27"
NBSP, NARROW = chr(0xA0), chr(0x202F)          # the spaces a model may put inside "43 123": no-break, narrow no-break


def figures(text: str, lang: str = "en") -> list[tuple[float, tuple[str, ...]]]:
    """What the checker reads in a text: each number with the unit classes its writing may mean, in order."""
    return [(figure.value, figure.units) for figure in read(text, lang).figures]


def refused(text: str, lang: str = "en") -> list[tuple[str, str]]:
    """What the checker refuses in a text whatever the facts are: the kind of refusal and the words refused."""
    return [(problem.kind, problem.text) for problem in read(text, lang).problems]


class Reading(unittest.TestCase):
    """What the checker reads in a text, before any comparison with the facts."""

    def test_an_amount_is_read_the_same_however_its_thousands_are_written(self):
        for lang, written in (("en", "43'123 CHF"), ("en", "43’123 CHF"), ("en", "43 123 CHF"), ("en", f"43{NBSP}123 CHF"),
                              ("en", f"43{NARROW}123 CHF"), ("en", "43,123 CHF"), ("en", "CHF 43,123"), ("en", "CHF43'123"),
                              ("en", "43'123 francs"), ("fr", "43'123 CHF"), ("fr", f"43{NARROW}123 CHF"), ("fr", "43 123 francs suisses")):
            with self.subTest(lang=lang, written=written):
                self.assertEqual(figures(f"She borrows {written} in all.", lang), [(43123.0, ("chf",))])
        for lang, written in (("en", "43'123.47 CHF"), ("en", "43,123.47 CHF"), ("fr", "43 123,47 CHF"), ("fr", "43'123,47 CHF")):
            with self.subTest(lang=lang, written=written):
                self.assertEqual(figures(written, lang), [(43123.47, ("chf",))])
        self.assertEqual((figures("24.8 months and 0.2%"), figures("24,8 mois et 0,2 %", "fr")),
                         ([(24.8, ("months",)), (0.2, ("percent",))],) * 2)
        # In French a comma is a decimal mark: "43,123 CHF" is 43.123 francs, not 43'123.
        self.assertEqual(figures("43,123 CHF", "fr"), [(43.123, ("chf",))])
        # The full stop of a sentence and the comma of a list are not part of a number.
        self.assertEqual(figures("At 27. Then 12 months, 9 of them."), [(27.0, BARE), (12.0, ("months",)), (9.0, ("count",))])

    def test_the_sign_is_part_of_the_figure(self):
        for written in ("−5'145 CHF", "-5'145 CHF", "–5'145 CHF", "− 5'145 CHF", "CHF -5,145", "-CHF 5,145", "(−5'145 CHF)"):
            with self.subTest(written=written):
                self.assertEqual(figures(f"At 28 she has {written} set aside."), [(28.0, BARE), (-5145.0, ("chf",))])
        self.assertEqual(figures("−30 % puis +0,2 %", "fr"), [(-30.0, ("percent",)), (0.2, ("percent",))])
        # A hyphen between two numbers is a range, and a hyphen inside a word is not a sign.
        self.assertEqual(figures("ages 23-24, then 23–24"), [(23.0, BARE), (24.0, BARE)] * 2)
        self.assertEqual(figures("a 12-month spell, sub-30"), [(12.0, ("months",)), (30.0, BARE)])

    def test_each_figure_has_the_unit_class_its_writing_means(self):
        english = {"43'123 CHF": ("chf",), "30%": ("percent",), "30 %": ("percent",), "30 percent": ("percent",),
                   "1 percentage point": ("points",), "2 points": ("points",), "12 months": ("months",), "the last 24 months": ("months",),
                   "27 years": YEARS, "a 27-year-old": YEARS, "2 goals": ("count",), "2 other goals": ("count",), "3 tested worlds": ("count",),
                   "at 27": BARE, "age 27": BARE}
        french = {"43'123 CHF": ("chf",), "30 %": ("percent",), "30 pour cent": ("percent",), "1 point de pourcentage": ("points",),
                  "12 mois": ("months",), "les 24 derniers mois": ("months",), "27 ans": YEARS, "1 an": YEARS, "2 objectifs": ("count",),
                  "2 autres objectifs": ("count",), "à 27": BARE}
        for lang, cases in (("en", english), ("fr", french)):
            for written, units in cases.items():
                with self.subTest(lang=lang, written=written):
                    self.assertEqual([found for _, found in figures(written, lang)], [units])
        # The two numbers of a proportion are counts.
        for lang, written in (("en", "2 of 6"), ("en", "2 out of 6 goals"), ("en", "2 goals out of 6"), ("fr", "2 sur 6"), ("fr", "2 des 6 objectifs")):
            with self.subTest(lang=lang, written=written):
                self.assertEqual(figures(written, lang), [(2.0, ("count",)), (6.0, ("count",))])

    def test_numbers_in_words_are_read_up_to_ninety_nine_in_both_languages(self):
        english = {"twelve months": (12, ("months",)), "Twelve months": (12, ("months",)), "twenty-four months": (24, ("months",)),
                   "twenty four": (24, BARE), "eleven": (11, BARE), "nineteen": (19, BARE), "forty-five": (45, BARE), "ninety-nine": (99, BARE),
                   "zero goals": (0, ("count",)), "thirty percent": (30, ("percent",)), "a two-year master's": (2, YEARS)}
        french = {"douze mois": (12, ("months",)), "vingt-sept ans": (27, YEARS), "vingt et un mois": (21, ("months",)), "seize": (16, BARE),
                  "dix-sept": (17, BARE), "vingt-deux": (22, BARE), "soixante-dix": (70, BARE), "soixante et onze": (71, BARE),
                  "soixante-dix-sept": (77, BARE), "quatre-vingts": (80, BARE), "quatre-vingt-un": (81, BARE), "quatre-vingt-dix": (90, BARE),
                  "quatre-vingt-dix-neuf": (99, BARE), "septante": (70, BARE), "nonante-neuf": (99, BARE), "zéro objectif": (0, ("count",)),
                  "trente pour cent": (30, ("percent",))}
        for lang, cases in (("en", english), ("fr", french)):
            for written, (value, units) in cases.items():
                with self.subTest(lang=lang, written=written):
                    self.assertEqual(figures(written, lang), [(float(value), units)])
                    self.assertEqual(refused(written, lang), [])
        # Beyond ninety-nine the checker asks for digits. "Pour cent" is a unit, not the number one hundred.
        self.assertEqual(refused("one hundred percent"), [("unreadable", "hundred")])
        self.assertEqual((refused("cent francs", "fr"), refused("mille francs", "fr")), ([("unreadable", "cent")], [("unreadable", "mille")]))

    def test_one_and_un_are_figures_only_where_they_measure_something(self):
        """ "One", "a", "un" and "une" are also plain words: a length of time, a proportion or, in English, a count of goals."""
        for lang, written, expected in (
                ("en", "a year of unemployment", [(1.0, YEARS)]), ("en", "one month", [(1.0, ("months",))]), ("en", "one goal", [(1.0, ("count",))]),
                ("en", "one of the six goals", [(1.0, ("count",)), (6.0, ("count",))]), ("en", "one goal out of six", [(1.0, ("count",)), (6.0, ("count",))]),
                ("fr", "un an de chômage", [(1.0, YEARS)]), ("fr", "un mois", [(1.0, ("months",))]),
                ("fr", "un objectif sur six", [(1.0, ("count",)), (6.0, ("count",))]), ("fr", "une des six stations", [(1.0, ("count",)), (6.0, ("count",))]),
                ("fr", "une seule station sur six", [(1.0, ("count",)), (6.0, ("count",))]), ("fr", "l'un des objectifs", [(1.0, ("count",))])):
            with self.subTest(lang=lang, written=written):
                self.assertEqual(figures(written, lang), expected)
        for lang, written in (("en", "the one that hurts"), ("en", "one kind of crisis"), ("en", "a crisis and an answer"),
                              ("fr", "une crise et un trajet"), ("fr", "l'une des raisons")):
            with self.subTest(lang=lang, written=written):
                self.assertEqual(figures(written, lang), [])

    def test_an_ordinal_a_list_number_and_an_identifier_are_not_figures(self):
        for lang, written in (("en", "the second crisis"), ("en", "the twenty-first month"), ("fr", "la deuxième crise"),
                              ("fr", "le dix-huitième mois"), ("fr", "la seconde"), ("fr", "le premier objectif")):
            with self.subTest(lang=lang, written=written):
                self.assertEqual((figures(written, lang), refused(written, lang)), ([], []))
        # Written with a digit, an ordinal is a number like another, and it has to be a fact.
        self.assertEqual((figures("the 2nd crisis"), figures("la 2e crise", "fr"), figures("le 1er objectif", "fr")),
                         ([(2.0, BARE)], [(2.0, BARE)], [(1.0, BARE)]))
        self.assertEqual(figures("1. First point at 27\n2. Second point with 12 months"), [(27.0, BARE), (12.0, ("months",))])
        # Only a list numbered 1, 2, 3 is one: a number that happens to start a line is read.
        self.assertEqual(figures("She loses her job at\n27. Then 12 months pass."), [(27.0, BARE), (12.0, ("months",))])
        # The digits inside the name of a world are not figures: the name is checked as a whole.
        named = read("In krach@24+chomage_long@25 and in chomage_6_mois@22~150.", "en")
        self.assertEqual((named.figures, named.identifiers), ((), ("krach@24+chomage_long@25", "chomage_6_mois@22~150")))
        self.assertEqual(read("_emphasis_ and cash+investments", "en").identifiers, ())

    def test_what_cannot_be_read_safely_is_refused_and_never_skipped(self):
        for written in ("1'23", "1.234.567", "12mo", "1e5", "24h", "20s", "½", ".5"):
            with self.subTest(written=written):
                self.assertEqual((figures(f"It is {written} here."), refused(f"It is {written} here.")), ([], [("unreadable", written)]))
        self.assertEqual(refused("It falls by 5‰."), [("unreadable", "‰")])

    def test_what_a_model_might_write_instead_of_a_figure_of_the_engine(self):
        """Other ways of writing a number the engine did not give. Each is refused, with facts that hold every small number."""
        facts = [Fact.count(n, "a count") for n in range(0, 10)] + [Fact.chf(43123, "Peak borrowing"), Fact.chf(-5145, "Set aside at 28"),
                                                                     Fact.percent(-30, "Crash"), Fact.age(27, "Start"), Fact.count(20, "a count")]
        english = {"She borrows forty-three thousand CHF.": "unreadable", "A hundred and fifty percent.": "unreadable",
                   "A fourth of her savings is gone.": "ratio", "Two fifths of it.": "ratio", "By a factor of 3.": "ratio",
                   "It is multiplied by 3.": "ratio", "It is divided by 2.": "ratio", "Twenty times the amount.": "ratio",
                   "She borrows 43'123.": "figure", "She borrows 43.123 CHF.": "figure", "She borrows 4.3e4 CHF.": "unreadable",
                   "She borrows 43\n123 CHF.": "figure", "She borrows 43'OOO CHF.": "figure", "She borrows $43,123.": "figure",
                   "Between 40'000 and 45'000 CHF.": "figure", "She borrows minus 5'145 CHF.": "figure", "A 30% crash.": "figure",
                   "She borrows 43'123 CHF, give or take.": "approximation", "More or less 43'123 CHF.": "approximation",
                   "She is 27 and a half.": "ratio", "9'656 CHF plus 16'401 CHF make 26'057 CHF.": "figure"}
        french = {"Elle emprunte quarante-trois mille CHF.": "unreadable", "Cent cinquante pour cent.": "unreadable",
                  "Un cinquième de son épargne.": "ratio", "Un facteur 3.": "ratio", "C'est multiplié par 3.": "ratio",
                  "Vingt fois le montant.": "ratio", "Elle emprunte 43'123.": "figure", "Plus ou moins 43'123 CHF.": "approximation",
                  "Elle a 27 ans et demi.": "ratio", "Une baisse de 30 %.": "figure"}
        for lang, cases in (("en", english), ("fr", french)):
            for text, kind in cases.items():
                report = check(text, facts, lang=lang)
                with self.subTest(lang=lang, text=text):
                    self.assertIn(kind, [problem.kind for problem in report.problems])
        # Written as the engine gave them, the same figures pass. Full-width digits are digits.
        for lang, text in (("en", "She borrows 43'123 CHF, and at 27 a −30% month leaves her −5'145 CHF."), ("en", "She borrows ４３'１２３ CHF."),
                           ("en", "One in three goals holds."), ("fr", "Le cinquième objectif tient, à 27 ans, avec −5'145 CHF.")):
            with self.subTest(lang=lang, text=text):
                self.assertTrue(check(text, facts, lang=lang).ok)
        # What the checker does not read: Roman numerals.
        self.assertTrue(check("At age XXVIII she stops.", facts, lang="en").ok)


class Refusals(unittest.TestCase):
    """What no fact can make right: a rounding, an abbreviation, a ratio, a word this project never writes."""

    def kinds(self, text: str, lang: str = "en") -> list[str]:
        return sorted({kind for kind, _ in refused(text, lang)})

    def test_a_rounding_is_refused(self):
        for lang, written in (("en", "about 43'000 CHF"), ("en", "nearly 12 months"), ("en", "around 27"), ("en", "some 9 months"),
                              ("en", "roughly 43'123 CHF"), ("en", "approximately 12 months"), ("en", "43'123 CHF or so"), ("en", "~27"),
                              ("en", "≈ 43'000 CHF"), ("en", "dozens of worlds"), ("en", "a couple of months"), ("en", "hundreds of francs"),
                              ("en", "43'000 CHF, rounded"), ("fr", "environ 43'000 CHF"), ("fr", "près de 12 mois"), ("fr", "presque 27 ans"),
                              ("fr", "autour de 27 ans"), ("fr", "quelque 9 mois"), ("fr", "43'123 CHF environ"), ("fr", "à peu près 12 mois"),
                              ("fr", "une dizaine de mondes"), ("fr", "une centaine de francs"), ("fr", "43'000 CHF, arrondi")):
            with self.subTest(lang=lang, written=written):
                self.assertEqual(self.kinds(f"It is {written}.", lang), ["approximation"])
        self.assertEqual(refused("She borrows about 43'000 CHF."), [("approximation", "about 43'000 CHF")])
        # A bound is not an approximation: the engine itself writes "up to" and "less than".
        for lang, written in (("en", "up to 43'123 CHF"), ("en", "more than 12 months"), ("en", "less than 50'100 CHF"), ("en", "at least 2 goals"),
                              ("fr", "jusqu'à 43'123 CHF"), ("fr", "moins de 50'100 CHF"), ("fr", "au moins 2 objectifs"), ("fr", "plus de 12 mois")):
            with self.subTest(lang=lang, written=written):
                self.assertEqual(refused(written, lang), [])

    def test_an_abbreviation_is_refused(self):
        for lang, written in (("en", "43k"), ("en", "43 k CHF"), ("en", "CHF 43K"), ("en", "1.2M"), ("en", "43 thousand"), ("en", "2 million CHF"),
                              ("fr", "43k"), ("fr", "43 mille CHF"), ("fr", "2 millions")):
            with self.subTest(lang=lang, written=written):
                self.assertEqual((self.kinds(written, lang), figures(written, lang)), (["abbreviation"], []))

    def test_a_ratio_is_refused(self):
        for lang, written in (("en", "her borrowing doubles"), ("en", "it triples"), ("en", "half of it"), ("en", "twice"), ("en", "3 times"),
                              ("en", "three times as much"), ("en", "2x"), ("en", "x2"), ("en", "×2"), ("en", "× 1'234"), ("en", "1'234 ×"),
                              ("en", "1/3"), ("en", "1'000 / 3"), ("en", "a third of it"), ("en", "two-thirds"),
                              ("en", "three quarters"), ("en", "tenfold"), ("fr", "son emprunt double"), ("fr", "la moitié"), ("fr", "deux fois plus"),
                              ("fr", "trois fois"), ("fr", "2 fois"), ("fr", "un tiers"), ("fr", "les trois quarts"), ("fr", "une fois et demie")):
            with self.subTest(lang=lang, written=written):
                self.assertEqual((self.kinds(written, lang), figures(written, lang)), (["ratio"], []),
                                 "A ratio is refused, and its own number is not read a second time")
        for lang, written in (("en", "at times, sometimes"), ("en", "the two tiers of the route"), ("fr", "une fois, à la fois, cette fois")):
            self.assertEqual(refused(written, lang), [])
        # The letter "x" is a multiplication only when it is stuck to the number.
        self.assertEqual((refused("x 27 and 27 x"), figures("x 27 and 27 x")), ([], [(27.0, BARE), (27.0, BARE)]))

    def test_the_words_this_project_never_writes_are_refused_in_both_languages(self):
        english = ("best", "risk", "risky", "recommend", "advise", "advice", "guaranteed", "chance", "chances")
        french = ("meilleur", "meilleure", "risque", "risqué", "recommande", "conseille", "conseil", "déconseillé", "garanti", "garantie", "chance")
        likelihood = ("likely", "unlikely", "probably", "probability", "odds", "probable", "probablement", "probabilité")
        for word in english + french + likelihood:
            for lang in ("en", "fr"):                # whichever language the text is said to be in
                with self.subTest(word=word, lang=lang):
                    self.assertEqual(refused(f"It is {word} here.", lang), [("banned", word)])
        self.assertEqual(refused("At a brisk pace she bestows nothing on the chancellor."), [])


class Checking(unittest.TestCase):
    """A text against the facts of its world: the real figures of the engine for the demo route, twelve months of
    unemployment at 27."""

    @classmethod
    def setUpClass(cls):
        tree = Tree(ALEXIA)
        th, age0 = tree.theta(None), tree.age0
        hit, calm = tree.trip(STORY, WORLD, None)[0], tree.trip(STORY, "reference", None)[0]
        kept, before = doors_of(hit, th, age0), doors_of(calm, th, age0)
        margins = margins_of(hit, th, age0)
        notes = [flow.label for month in hit.months for flow in month.flows if flow.label.startswith("Pas d'indemnité de chômage")]
        cls.note, cls.months_without = notes[0], len(notes)
        cls.engine = {"kept": sum(kept.values()), "total": len(kept), "lost": sum(before[k] and not kept[k] for k in kept), "calm": sum(before.values()),
                      "peak": hit.peak_financing_chf, "worth": hit.net_worth_end_chf, "aside": margins["reconversion"][0],
                      "asked": margins["reconversion"][1]}
        # What the tests below write by hand is what the engine gives today.
        assert (cls.engine["kept"], cls.engine["total"], cls.engine["lost"], cls.engine["calm"], cls.months_without) == (1, 6, 2, 3, 9)
        assert [round(cls.engine[key]) for key in ("peak", "worth", "aside", "asked")] == [43123, 48033, -5145, 39366]

    def facts(self, lang: str) -> list[Fact]:
        e = self.engine
        with i18n.use(lang):
            return [Fact.count(e["kept"], "Goals kept", WORLD, "kept"), Fact.count(e["total"], "Goals in all"),
                    Fact.count(e["lost"], "Goals lost", WORLD, "lost"), Fact.count(e["calm"], "Goals kept with no shock"),
                    Fact.chf(e["peak"], "Peak borrowing", WORLD, "borrowed"), Fact.chf(e["worth"], "Net worth at 30", WORLD),
                    Fact.chf(e["aside"], "Career change: set aside at 28", WORLD), Fact.chf(e["asked"], "Career change: amount asked"),
                    Fact.age(27, "Start of the crisis", WORLD), Fact.age(28, "Career change: age"), Fact.months(12, "Length of the crisis", WORLD),
                    Fact.months(self.months_without, "Months with no benefit", WORLD),
                    *facts_in(i18n.ledger(self.note), "Note of the ledger", WORLD)]

    ENGLISH = ("Twelve months of unemployment at 27 leave her with no benefit for 9 months: 0 months contributed out of 24, 12 are required. "
               "She borrows up to 43'123 CHF and keeps 1 goal of 6. At 28 she has −5'145 CHF set aside where Career change asks for "
               "39'366 CHF (chomage_long@27).")
    FRENCH = ("Douze mois de chômage à 27 ans la laissent sans indemnité pendant 9 mois : 0 mois cotisés sur 24, il en faut 12. "
              "Elle emprunte jusqu'à 43'123 CHF et garde 1 objectif sur 6. À 28 ans, elle a −5'145 CHF de côté alors que « Reconversion » "
              "demande 39'366 CHF (chomage_long@27).")

    def test_a_text_made_of_the_figures_of_the_engine_passes_and_says_where_each_comes_from(self):
        for lang, text, label in (("en", self.ENGLISH, "✓ 12 figures verified"), ("fr", self.FRENCH, "✓ 12 chiffres vérifiés")):
            report = check(text, self.facts(lang), identifiers=[WORLD], lang=lang)
            with self.subTest(lang=lang), i18n.use(lang):
                self.assertTrue(report.ok, report.feedback())
                self.assertEqual((report.label(), len(report.figures), report.problems, report.identifiers), (label, 12, (), (WORLD,)))
                origins = {figure.text: figure.origins for figure in report.figures}
                self.assertEqual(origins["43'123 CHF"], ("Peak borrowing",))
                self.assertEqual(origins["−5'145 CHF"], ("Career change: set aside at 28",))
                self.assertEqual(origins["39'366 CHF"], ("Career change: amount asked",))
                self.assertEqual((origins["24"], origins["12"]), (("Note of the ledger",),) * 2)
                shown = report.as_dict()
                self.assertEqual((shown["ok"], shown["label"], shown["verified"], shown["refused"]), (True, label, 12, []))
                self.assertEqual(shown["figures"][6], {"text": "43'123 CHF", "value": 43123.0, "unit": "chf", "origins": ["Peak borrowing"]})
        with i18n.use("en"):
            self.assertEqual((check("She keeps 1 goal.", self.facts("en"), lang="en").label(), check("Nothing holds.", [], lang="en").label()),
                             ("✓ 1 figure verified", "✓ No figure to verify"))
        with i18n.use("fr"):
            self.assertEqual((check("Elle garde 1 objectif.", self.facts("fr"), lang="fr").label(), check("Rien ne tient.", [], lang="fr").label()),
                             ("✓ 1 chiffre vérifié", "✓ Aucun chiffre à vérifier"))

    def test_any_figure_changed_fails(self):
        """One sentence per fact, written as the model is shown it. Every fact moved a little makes the text fail,
        and the refusal names that figure and no other."""
        for lang in ("en", "fr"):
            facts = self.facts(lang)
            with i18n.use(lang):
                sentence = lambda written: " ; ".join(fact.written() if written is None or fact is not written[0] else written[1] for fact in facts)
                self.assertTrue(check(sentence(None), facts, lang=lang).ok)
                changed = 0
                for fact in facts:
                    for step in (1, -1, 7, 100, 1000):
                        moved = Fact(fact.value + step, fact.unit, fact.origin, fact.world)
                        if any(other.unit in (YEARS if moved.unit in YEARS else BARE if moved.unit in BARE else (moved.unit,))
                               and other.value == moved.value for other in facts):
                            continue                       # by coincidence another fact has this value: not a change
                        report = check(sentence((fact, moved.written())), facts, lang=lang)
                        with self.subTest(lang=lang, fact=fact.written(), moved=moved.written()):
                            self.assertEqual([problem.kind for problem in report.problems], ["figure"])
                            self.assertIn(checker._number(moved.value).lstrip("−"), report.problems[0].text)
                            self.assertEqual(report.as_dict()["figures"], [], "No figure of a refused text is shown as verified")
                        changed += 1
                self.assertGreater(changed, 50)

    def test_a_figure_keeps_its_unit_its_sign_and_its_exact_value(self):
        facts = self.facts("en")
        cases = {"At 27 CHF she stops.": "The engine gave age 27 (Start of the crisis): the same number, with another unit.",
                 "It lasts 12 years.": "The engine gave 12 months (Length of the crisis): the same number, with another unit.",
                 "She borrows 43'123 months.": "The engine gave 43'123 CHF (Peak borrowing): the same number, with another unit.",
                 "She keeps 6 months.": "The engine gave 6 (Goals in all): the same number, with another unit.",
                 "At 28 she has 5'145 CHF set aside.": "The engine gave −5'145 CHF: keep its sign.",
                 "Her debt peaks at −43'123 CHF.": "The engine gave 43'123 CHF: keep its sign.",
                 "Her debt peaks at 43'000 CHF.": "It looks like a rounding of 43'123 CHF: copy it exactly.",
                 "Her debt peaks at 43'100 CHF.": "It looks like a rounding of 43'123 CHF: copy it exactly.",
                 "Her debt peaks at 43'123.47 CHF.": "It looks like a rounding of 43'123 CHF: copy it exactly.",
                 "Her debt peaks at 43.123 CHF.": "", "There are 4 goals.": "", "She is 26.": ""}
        for text, hint in cases.items():
            report = check(text, facts, lang="en")
            with self.subTest(text=text):
                self.assertEqual([problem.kind for problem in report.problems], ["figure"])
                self.assertTrue(report.problems[0].message.startswith("“"))
                self.assertIn("is not a figure the engine gave for this text." + (" " + hint if hint else ""), report.problems[0].message)
                self.assertEqual(report.problems[0].message.endswith("for this text."), not hint)
        french = check("À 28 ans, elle a 5'145 CHF de côté pendant 12 ans.", self.facts("fr"), lang="fr")
        self.assertEqual([problem.message for problem in french.problems],
                         ["« 5'145 CHF » n'est pas un chiffre que le moteur a donné pour ce texte. Le moteur a donné −5'145 CHF : garde son signe.",
                          "« 12 ans » n'est pas un chiffre que le moteur a donné pour ce texte. Le moteur a donné 12 mois (Length of the crisis) : "
                          "le même nombre, avec une autre unité."])
        # A number the engine wrote with no unit ("12 are required") is copied with no unit, and given none afterwards.
        note = facts_in("No unemployment benefit: 0 months contributed out of 24, 12 are required", "Note of the ledger", lang="en")
        self.assertEqual([(fact.value, fact.unit) for fact in note], [(0.0, "months"), (24.0, "count"), (12.0, "number")])
        self.assertEqual([check(text, note, lang="en").ok for text in ("12 are required.", "out of 24", "12 months are required.", "12 years", "24 months")],
                         [True, True, False, False, False])

    def test_a_figure_of_another_world_is_refused_and_the_refusal_names_that_world(self):
        other = [Fact.chf(87092.68, "Net worth at 30", "krach@24"), Fact.count(2, "Goals kept", "krach@24")]
        report = check("She ends with 87'093 CHF.", self.facts("en"), elsewhere=other, lang="en")
        self.assertEqual([problem.message for problem in report.problems],
                         ["“87'093 CHF” is not a figure the engine gave for this text. It is a figure of another world (krach@24), not of this one."])
        # The figures of the other worlds only explain a refusal: they never make a text pass.
        self.assertTrue(check("She ends with 48'033 CHF.", self.facts("en"), elsewhere=other, lang="en").ok)
        self.assertFalse(check("She ends with 87'093 CHF.", [], elsewhere=other, lang="en").ok)

    def test_a_world_that_was_not_tested_cannot_be_named(self):
        for named, accepted in (("chomage_long@27", True), ("krach@24", False), ("chomage_long@26", False), ("chomage_long", False)):
            report = check(f"In {named} she keeps 1 goal of 6.", self.facts("en"), identifiers=[WORLD], lang="en")
            with self.subTest(named=named):
                self.assertEqual(report.ok, accepted)
                self.assertEqual([(problem.kind, problem.text) for problem in report.problems], [] if accepted else [("identifier", named)])
        # A world with two crises may be named whole, with its crises in either order, or by one of its crises.
        pair = ["krach@24+chomage_long@25"]
        for named, accepted in (("krach@24+chomage_long@25", True), ("chomage_long@25+krach@24", True), ("krach@24", True), ("chomage_long@25", True),
                                ("krach@25", False), ("krach@24+chomage_long@26", False), ("chomage_6_mois", False)):
            with self.subTest(named=named):
                self.assertEqual(check(f"See {named}.", [], identifiers=pair, lang="en").ok, accepted)
        self.assertEqual(check("See krach@25.", [], identifiers=pair, lang="fr").problems[0].message, "« krach@25 » n'est pas un des mondes testés ici.")

    def test_every_written_form_of_a_fact_is_read_back_in_both_languages(self):
        """What the model is shown is what the checker reads: a fact copied as it is written always passes."""
        for lang in ("en", "fr"):
            for unit in UNITS:
                for value in (0, 1, 2, 12, 27, 100, 1000, 43123, 1234567, -1, -5145, 24.8, 0.2, -30.5):
                    fact = Fact(value, unit, "somewhere")
                    with i18n.use(lang):
                        report = check(f"Then {fact.written()} is given.", [fact], lang=lang)
                    with self.subTest(lang=lang, unit=unit, value=value):
                        self.assertTrue(report.ok, report.feedback())
                        self.assertEqual([(figure.value, figure.unit) for figure in report.figures], [(float(value), unit)])
        with i18n.use("en"):
            self.assertEqual([Fact.chf(43123.47, "o").written(), Fact.chf(-5145.24, "o").written(), Fact.percent(-30, "o").written(),
                              Fact.months(1, "o").written(), Fact.years(2, "o").written(), Fact.age(27, "o").written(), Fact.count(6, "o").written()],
                             ["43'123 CHF", "−5'145 CHF", "−30%", "1 month", "2 years", "age 27", "6"])
        with i18n.use("fr"):
            self.assertEqual([Fact.chf(43123.47, "o").written(), Fact.percent(0.2, "o").written(), Fact.months(24.8, "o").written(),
                              Fact.years(1, "o").written(), Fact.age(27, "o").written()],
                             ["43'123 CHF", "0,2 %", "24,8 mois", "1 an", "27 ans"])
        with self.assertRaises(ValueError):
            Fact(1, "apples", "nowhere")

    def test_the_number_next_to_keep_lose_or_borrow_has_to_be_that_quantity(self):
        """For three quantities the role of the number is checked, not only its presence. In this world Alexia keeps 1 goal,
        loses 2 and borrows up to 43'123 CHF. Each number below is a figure of the engine for this world: what is refused
        is where it stands."""
        refused_en = {
            "She keeps 2 goals of 6.": ["“2” stands next to “keeps”: the number of goals kept in this world is 1."],
            "She loses 1 goal and keeps 2.": ["“1” stands next to “loses”: the number of goals lost in this world is 2.",
                                              "“2” stands next to “keeps”: the number of goals kept in this world is 1."],
            "She keeps only 2.": ["“2” stands next to “keeps”: the number of goals kept in this world is 1."],
            "She keeps all 6.": ["“6” stands next to “keeps”: the number of goals kept in this world is 1."],
            "She kept 3 goals.": ["“3” stands next to “kept”: the number of goals kept in this world is 1."],
            "2 goals are kept.": ["“2” stands next to “kept”: the number of goals kept in this world is 1."],
            "She keeps no goal.": ["“no” stands next to “keeps”: the number of goals kept in this world is 1."],
            "She keeps none of the 6 goals.": ["“none” stands next to “keeps”: the number of goals kept in this world is 1."],
            "You keep none of your 6 goals.": ["“none” stands next to “keep”: the number of goals kept in this world is 1."],
            "You keep 2 of your 6 goals.": ["“2” stands next to “keep”: the number of goals kept in this world is 1."],
            "She loses a goal.": ["“a” stands next to “loses”: the number of goals lost in this world is 2."],
            "She has lost 1 goal.": ["“1” stands next to “lost”: the number of goals lost in this world is 2."],
            "She borrows up to 48'033 CHF.": ["“48'033 CHF” stands next to “borrows”: the peak borrowing of this world is 43'123 CHF."],
            "Peak borrowing: 48'033 CHF.": ["“48'033 CHF” stands next to “borrowing”: the peak borrowing of this world is 43'123 CHF."],
            "Up to 48'033 CHF to finance.": ["“48'033 CHF” stands next to “finance”: the peak borrowing of this world is 43'123 CHF."],
            "48'033 CHF borrowed.": ["“48'033 CHF” stands next to “borrowed”: the peak borrowing of this world is 43'123 CHF."],
            "Financing max. 48'033 CHF.": ["“48'033 CHF” stands next to “Financing”: the peak borrowing of this world is 43'123 CHF."],
            "She borrows about 43'000 CHF.": ["“about 43'000 CHF” is an approximation: write the engine's figure exactly, or leave it out.",
                                              "“43'000 CHF” stands next to “borrows”: the peak borrowing of this world is 43'123 CHF."]}
        refused_fr = {
            "Elle garde 2 objectifs sur 6.": ["« 2 » est à côté de « garde » : le nombre d'objectifs gardés dans ce monde est 1."],
            "Elle garde deux objectifs.": ["« deux » est à côté de « garde » : le nombre d'objectifs gardés dans ce monde est 1."],
            "Elle ne garde aucun objectif.": ["« aucun » est à côté de « garde » : le nombre d'objectifs gardés dans ce monde est 1."],
            "Elle n'en garde aucun.": ["« aucun » est à côté de « garde » : le nombre d'objectifs gardés dans ce monde est 1."],
            "Tu ne gardes aucun de tes 6 objectifs.": ["« aucun » est à côté de « gardes » : le nombre d'objectifs gardés dans ce monde est 1."],
            "Tu gardes 2 de tes 6 objectifs.": ["« 2 » est à côté de « gardes » : le nombre d'objectifs gardés dans ce monde est 1."],
            "Elle perd un objectif.": ["« un » est à côté de « perd » : le nombre d'objectifs perdus dans ce monde est 2."],
            "1 objectif est perdu.": ["« 1 » est à côté de « perdu » : le nombre d'objectifs perdus dans ce monde est 2."],
            "Elle emprunte jusqu'à 48'033 CHF.": ["« 48'033 CHF » est à côté de « emprunte » : l'emprunt maximal de ce monde est 43'123 CHF."],
            "Un emprunt maximal de 48'033 CHF.": ["« 48'033 CHF » est à côté de « emprunt » : l'emprunt maximal de ce monde est 43'123 CHF."],
            "Jusqu'à 48'033 CHF à financer.": ["« 48'033 CHF » est à côté de « financer » : l'emprunt maximal de ce monde est 43'123 CHF."],
            "financement max. 48'033 CHF": ["« 48'033 CHF » est à côté de « financement » : l'emprunt maximal de ce monde est 43'123 CHF."]}
        for lang, cases in (("en", refused_en), ("fr", refused_fr)):
            for text, messages in cases.items():
                report = check(text, self.facts(lang), lang=lang)
                with self.subTest(lang=lang, text=text):
                    self.assertEqual([problem.message for problem in report.problems], messages)
                    self.assertEqual({problem.kind for problem in report.problems} - {"approximation"}, {"role"})
        # The same quantities in their place, and the same words with no claim on a number.
        accepted = {"en": ("She keeps 1 goal of 6.", "She keeps 1 goal of 6 and loses 2.", "She loses 2 goals and keeps 1.", "2 goals are lost, 1 is kept.",
                           "1 goal kept and 2 lost.", "Only 1 of the 6 goals is kept.", "2 of the 6 goals are lost.", "She keeps a goal.",
                           "She keeps one goal.", "She loses 2 goals and keeps the rest.", "Of the 3 goals she kept with no shock, she loses 2.",
                           "She loses her job at 27 and keeps working until 28.", "She keeps her job for 12 months.", "She loses 12 months of income.",
                           "She borrows up to 43'123 CHF.", "Peak borrowing: 43'123 CHF.", "Up to 43'123 CHF to finance.",
                           "She borrows 43'123 CHF and ends with 48'033 CHF.", "She ends with 48'033 CHF after borrowing.",
                           "She needs 39'366 CHF to finance her career change.", "To finance her career change, she needs 39'366 CHF.",
                           "Her financial position at 28: −5'145 CHF.", "You keep 1 of your 6 goals and lose 2 of them.",
                           "Of your 3 goals you keep one, and you lose 2 goals."),
                    "fr": ("Elle garde 1 objectif sur 6 et en perd 2.", "Elle ne garde qu'un objectif.", "Elle garde un objectif.",
                           "Elle perd 2 objectifs et en garde 1.", "2 objectifs sont perdus, 1 est gardé.", "Elle perd son emploi à 27 ans.",
                           "Elle perd 12 mois de salaire.", "Elle emprunte jusqu'à 43'123 CHF.", "financement max. 43'123 CHF",
                           "Il lui faut 39'366 CHF pour financer sa reconversion.", "Tu gardes 1 de tes 6 objectifs et tu en perds 2.",
                           "Tu ne gardes qu'un de tes 6 objectifs.")}
        for lang, texts in accepted.items():
            for text in texts:
                with self.subTest(lang=lang, text=text):
                    report = check(text, self.facts(lang), lang=lang)
                    self.assertTrue(report.ok, report.feedback())
        # Without a fact that carries the role, nothing can be said about the place of a number: the text passes on presence.
        plain = [Fact.count(1, "Goals kept", WORLD), Fact.count(2, "Goals lost", WORLD)]
        self.assertTrue(check("She keeps 2 goals.", plain, lang="en").ok)
        with self.assertRaises(ValueError):
            Fact.count(1, "Goals kept", WORLD, "held")

    def test_a_sentence_of_the_engine_copied_word_for_word_is_accepted_whole(self):
        """A label or a sentence the engine gave as it is may hold what the checker refuses elsewhere: a twelfth, a half."""
        tax = Quote("Income tax for the previous year (1/12)", "Line of the ledger", WORLD)
        source = Quote("[to be verified] admin.ch, LPP. Half paid by the employer", "Source of an assumption")
        note = Quote("No unemployment benefit: 0 months contributed out of 24, 12 are required", "Note of the ledger", WORLD)
        given = self.facts("en") + [tax, source, note]
        for text in ("The ledger shows “Income tax for the previous year (1/12)” every month.",
                     "Every month the ledger shows income tax for the previous year (1/12).",
                     f"The ledger shows Income{NBSP}tax for the previous year (1/12).",
                     "Its source: [to be verified] admin.ch, LPP. Half paid by the employer.",
                     "At 27 the ledger says: no unemployment benefit: 0 months contributed out of 24, 12 are required."):
            with self.subTest(text=text):
                self.assertTrue(check(text, given, lang="en").ok, check(text, given, lang="en").feedback())
        # The figures of a copied sentence are the engine's: they are counted, with the sentence as their origin.
        report = check("At 27 the ledger says: no unemployment benefit: 0 months contributed out of 24, 12 are required.", [Fact.age(27, "Start"), note], lang="en")
        self.assertEqual([(figure.text, figure.origins) for figure in report.figures],
                         [("27", ("Start",)), ("0 months", ("Note of the ledger",)), ("24", ("Note of the ledger",)), ("12", ("Note of the ledger",))])
        # One word changed, or one part left out, and it is an ordinary text again.
        for text, kind in (("The ledger shows income tax for last year (1/12).", "ratio"), ("Half paid by the employer.", "ratio"),
                           ("Income tax for the previous year (1/12) and a third of it.", "ratio"),
                           ("Income tax for the previous year (1/120).", "ratio")):
            with self.subTest(text=text):
                self.assertEqual([problem.kind for problem in check(text, given, lang="en").problems], [kind])
        # Without the quote among the facts, the same words are refused.
        self.assertEqual([problem.kind for problem in check("Income tax for the previous year (1/12).", self.facts("en"), lang="en").problems], ["ratio"])
        french = [Quote("Impôt de l'année précédente (1/12)", "Ligne du registre"), Quote("[à vérifier] admin.ch, LPP. Moitié employeur", "Source")]
        self.assertTrue(check("Le registre montre « Impôt de l’année précédente (1/12) » chaque mois.", french, lang="fr").ok)
        self.assertFalse(check("Moitié employeur.", french, lang="fr").ok)
        # A word this project never writes stays refused, even in a quote; and a number alone is not a quote.
        self.assertEqual([problem.kind for problem in check("The best line of the ledger.", [Quote("The best line of the ledger", "nowhere")], lang="en").problems],
                         ["banned"])
        with self.assertRaises(ValueError):
            Quote("1/12", "nowhere")

    def test_the_limit_that_remains_a_true_figure_in_a_wrong_sentence_passes(self):
        """What the checker does not do. Outside the three quantities whose role is checked, it does not judge the words
        around a figure. 43'123 CHF is what Alexia borrows at most in this world, not her net worth: the sentence is
        false, and it passes. So does a false count next to a verb the checker does not know."""
        for text in ("At 28 her net worth is 43'123 CHF.", "She holds 2 goals of 6.", "At 27 she has −5'145 CHF set aside."):
            with self.subTest(text=text):
                self.assertTrue(check(text, self.facts("en"), lang="en").ok)

    @unittest.skipIf(TestClient is None, "FastAPI is not installed")
    def test_every_sentence_the_engine_computes_can_be_copied_as_it_is(self):
        """Nothing the engine writes in its results is refused by the checker's own rules, and a sentence copied as it is
        passes once its figures are the facts. One line of the ledger is the exception: a twelfth is a ratio."""
        client, worlds = TestClient(app), ["reference", "krach", WORLD, "krach@24+chomage_long@25", "chomage_long@23+chomage_long@24"]
        known = {"en": {"Income tax for the previous year (1/12)"}, "fr": {"Impôt de l'année précédente (1/12)"}}
        for lang in ("en", "fr"):
            post = lambda route, **body: client.post(f"/{route}?lang={lang}", json=body).json()
            answers = [client.get(f"/worlds?lang={lang}&mondes={','.join(worlds).replace('+', '%2B')}").json(), client.get(f"/limits?lang={lang}").json(),
                       post("path", path=STORY, world_id=WORLD, mondes=worlds), post("node", path=STORY, gare_month=72, mondes=worlds),
                       post("pathways", path=STORY), post("adaptive", path=STORY), post("policies"), post("folk-rule")]
            sentences = sorted(set(test_english.strings(answers)))
            read_in_all = 0
            for sentence in sentences:
                reading = read(sentence, lang)
                read_in_all += len(reading.figures)
                with self.subTest(lang=lang, sentence=sentence[:80]):
                    if sentence in known[lang]:
                        self.assertEqual([(problem.kind, problem.text) for problem in reading.problems], [("ratio", "1/12")])
                        self.assertTrue(check(sentence, [Quote(sentence, "Line of the ledger")], lang=lang).ok, "Given as a quote, it is accepted")
                    else:
                        self.assertEqual(reading.problems, ())
                        self.assertTrue(check(sentence, facts_in(sentence, "the engine", lang=lang), identifiers=reading.identifiers, lang=lang).ok)
            self.assertGreater(len(sentences), 80)
            self.assertGreater(read_in_all, 60)
            # The labels and the sources of the assumptions state halves, twelfths and roundings. Read as ordinary text,
            # four of them are refused; given as quotes and copied word for word, every one of them is accepted.
            sources = sorted(set(test_english.strings(client.get(f"/assumptions?lang={lang}").json())))
            self.assertEqual(sum(bool(read(source, lang).problems) for source in sources), 4)
            for source in sources:
                with self.subTest(lang=lang, source=source[:80]):
                    self.assertTrue(check(f"« {source} »", [Quote(source, "Source of an assumption")], lang=lang).ok)


class TryingAgain(unittest.TestCase):
    """A refused text is never shown. The model is told what was refused and gets two more tries; then the screen shows
    the facts of the engine alone."""
    FACTS = [Fact.chf(43123.47, "Peak borrowing", WORLD), Fact.count(1, "Goals kept", WORLD)]
    OTHER = [Fact.chf(87092.68, "Net worth at 30", "krach@24"), Fact.count(2, "Goals kept", "krach@24")]
    COMMON = [Fact.count(6, "Goals in all")]

    def scripted(self, *answers: dict):
        """A model that gives these answers in turn, and remembers what it was told each time."""
        told = []

        def write(feedback):
            told.append(feedback)
            return answers[min(len(told), len(answers)) - 1]
        return write, told

    def test_a_refused_text_is_asked_again_with_what_was_refused_and_accepted_once_right(self):
        write, told = self.scripted({WORLD: "She borrows about 43'000 CHF."}, {WORLD: "She borrows up to 43'123 CHF and keeps 1 goal of 6."})
        outcome = supervise(write, {WORLD: self.FACTS}, common=self.COMMON, lang="en")[WORLD]
        self.assertEqual((outcome.accepted, outcome.text, len(outcome.attempts)), (True, "She borrows up to 43'123 CHF and keeps 1 goal of 6.", 2))
        self.assertEqual((told[0], list(told[1])), (None, [WORLD]))
        self.assertEqual(told[1][WORLD].splitlines(),
                         ["The checker refused this text. Copy every figure exactly as the engine gave it, with its sign and its unit. "
                          "No rounding, no ratio, no figure of your own.",
                          "- “about 43'000 CHF” is an approximation: write the engine's figure exactly, or leave it out.",
                          "- “43'000 CHF” is not a figure the engine gave for this text. It looks like a rounding of 43'123 CHF: copy it exactly."])
        with i18n.use("en"):
            shown = outcome.as_dict()
        self.assertEqual((shown["accepted"], shown["label"], shown["verified"], shown["attempts"], shown["refusals"]),
                         (True, "✓ 3 figures verified", 3, 2, [["approximation", "figure"]]))
        self.assertEqual(sorted(shown), ["accepted", "attempts", "figures", "label", "refusals", "text", "verified"])
        # Of the refused text, only the kinds of refusal are kept: none of its words reaches the screen.
        self.assertNotIn("43'000", str(shown))

    def test_three_refusals_give_no_text_at_all(self):
        write, told = self.scripted({WORLD: "She borrows about 43'000 CHF."}, {WORLD: "She borrows 43k."}, {WORLD: "Her borrowing doubles."})
        outcome = supervise(write, {WORLD: self.FACTS}, lang="en")[WORLD]
        self.assertEqual((ATTEMPTS, len(told), len(outcome.attempts)), (3, 3, 3))
        self.assertEqual((outcome.accepted, outcome.text, outcome.report), (False, None, None))
        for lang, label in (("en", "AI explanation rejected by the checker"), ("fr", "Explication de l'IA rejetée par le contrôleur")):
            with i18n.use(lang):
                shown = outcome.as_dict()
                self.assertEqual((outcome.label(), shown["label"], shown["accepted"], shown["text"], shown["figures"], shown["verified"],
                                  shown["attempts"]), (label, label, False, None, [], 0, 3))
        self.assertEqual(shown["refusals"], [["approximation", "figure"], ["abbreviation"], ["ratio"]])
        for words in ("43'000", "43k", "doubles"):
            self.assertNotIn(words, str(shown))
        # The number of tries is the caller's to lower, never an open loop.
        write, told = self.scripted({WORLD: "She borrows 43k."})
        self.assertFalse(supervise(write, {WORLD: self.FACTS}, lang="en", attempts=1)[WORLD].accepted)
        self.assertEqual(len(told), 1)

    def test_each_text_is_checked_against_its_own_world_and_only_the_refused_ones_are_asked_again(self):
        facts = {WORLD: self.FACTS, "krach@24": self.OTHER}
        write, told = self.scripted({WORLD: "She borrows up to 43'123 CHF.", "krach@24": "She borrows up to 43'123 CHF and keeps 2 goals of 6."},
                                    {WORLD: "She borrows 99'999 CHF.", "krach@24": "She ends with 87'093 CHF and keeps 2 goals of 6."})
        outcomes = supervise(write, facts, common=self.COMMON, identifiers=list(facts), lang="en")
        self.assertEqual({key: (outcome.accepted, len(outcome.attempts)) for key, outcome in outcomes.items()}, {WORLD: (True, 1), "krach@24": (True, 2)})
        # The second answer was only asked for the refused world, and what it says of the other one is ignored.
        self.assertEqual(list(told[1]), ["krach@24"])
        self.assertIn("It is a figure of another world (chomage_long@27), not of this one.", told[1]["krach@24"])
        self.assertEqual(outcomes[WORLD].text, "She borrows up to 43'123 CHF.")
        self.assertEqual(outcomes["krach@24"].text, "She ends with 87'093 CHF and keeps 2 goals of 6.")
        self.assertEqual(len(told), 2, "Once every text is accepted, the model is not asked again")

    def test_a_missing_text_is_a_refusal(self):
        write, told = self.scripted({})
        outcome = supervise(write, {WORLD: self.FACTS}, lang="en")[WORLD]
        self.assertEqual((outcome.accepted, len(told)), (False, 3))
        self.assertEqual([[problem.kind for problem in report.problems] for report in outcome.attempts], [["empty"]] * 3)
        self.assertEqual(told[1][WORLD].splitlines()[1], "- The text is empty.")
        write, _ = self.scripted({WORLD: 43123})                 # not a text at all
        self.assertFalse(supervise(write, {WORLD: self.FACTS}, lang="en")[WORLD].accepted)


class TheModule(unittest.TestCase):
    """The checker is pure code, written in both languages, with nothing hidden in its source."""
    FILES = sorted((ROOT / "ai").glob("*.py"))

    def test_the_checker_imports_no_model_and_no_network(self):
        allowed = {"__future__", "re", "dataclasses", "typing", "engine", "engine.i18n"}
        imported = set()
        for node in ast.walk(ast.parse((ROOT / "ai/checker.py").read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module)
        self.assertEqual(imported - allowed, set())
        self.assertIn("engine.i18n", imported)

    def test_every_sentence_of_the_ai_layer_is_written_in_both_languages(self):
        calls = 0
        for file in self.FILES:
            for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "say":
                    calls += 1
                    self.assertEqual((len(node.args), len(node.keywords)), (2, 0), f"{file.name}:{node.lineno}")
                    english = ast.unparse(node.args[0])
                    self.assertNotEqual(english.strip("f'\""), "", f"{file.name}:{node.lineno}")
                    self.assertNotEqual(ast.unparse(node.args[1]).strip("f'\""), "", f"{file.name}:{node.lineno}")
                    # What the checker says is held to the rule it enforces: no word this project never writes.
                    self.assertEqual([problem for problem in read(english, "en").problems if problem.kind == "banned"], [], english)
                    if TestClient is not None:
                        self.assertIsNone(test_english.FRENCH.search(english), english)
        self.assertGreater(calls, 20)

    def test_no_invisible_character_hides_in_the_source(self):
        """A no-break space inside a pattern cannot be seen in a review: such characters are written as escapes."""
        for file in self.FILES:
            source = file.read_text(encoding="utf-8")
            hidden = sorted({unicodedata.name(char, hex(ord(char))) for char in source
                             if unicodedata.category(char) in ("Zs", "Cf", "Cc", "Zl", "Zp") and char not in " \n"})
            self.assertEqual(hidden, [], file.name)


if __name__ == "__main__":
    unittest.main()
