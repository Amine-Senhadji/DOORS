"""L'anglais par défaut, le français en option : mêmes chiffres, deux écritures.

Les autres fichiers de tests gardent leurs phrases attendues en français. Celui-ci vérifie que tout ce que la page
montre existe aussi en anglais, que l'anglais ne laisse passer aucun mot français, et que la langue ne change
aucun chiffre.
"""
from __future__ import annotations

import ast
import html
import re
import string
import unittest
from dataclasses import fields
from pathlib import Path

from engine import english, i18n
from engine import worlds as W
from engine.assumptions import ASSUMPTIONS
from engine.blocks import BLOCKS, NOT_YET, REFUSED_CITIES, destinations
from engine.contract import World
from engine.explore import DOORS
from engine.policy import NAMES_EN, POLICIES
from engine.simulate import load_scenario
from engine.tree import Tree

try:
    from fastapi.testclient import TestClient
    from api.main import app
    import test_web
except ImportError:  # pragma: no cover
    TestClient = None

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
ALEXIA = load_scenario(ROOT / "engine/scenarios/alexia.json")
STORY = [{"block": "job", "years": 5}, {"block": "master", "years": 2}, {"block": "job", "years": 3}]
LINES = [STORY, [{"block": "master", "years": 2}, {"block": "job", "years": 8}], [{"block": "job", "years": 10}],
         [{"block": "job_abroad", "years": 10}], [{"block": "master", "years": 1}, {"block": "job", "years": 9}]]
# Ce qui trahit une phrase restée en français : une lettre accentuée, ou un petit mot que l'anglais n'a pas.
FRENCH = re.compile(r"[àâçéèêëîïôöùûüœ«»]|\b(le|la|les|des|une|est|pas|pour|dans|avec|qui|que|ans|mois|année|années|épargne|trajet|gare|"
                    r"monde|mondes|porte|portes|seuil|règle|côté|ton|tu|elle|il|ou|et)\b", re.IGNORECASE)
# Les mots que l'interface n'écrit jamais, en anglais. « advice » n'apparaît que pour dire que ce n'en est pas.
BANNED = re.compile(r"chance|probabilit|risk|best|recommend|advis|guarantee", re.IGNORECASE)


def keys_of(file: Path) -> list[tuple[int, str]]:
    """Les clés d'un fichier de textes, dans l'ordre, avec leur retrait : sa structure."""
    out = []
    for line in file.read_text(encoding="utf-8").splitlines():
        found = re.match(r"^( +)([A-Za-z_]\w*):", line)
        if found and not line.strip().startswith("//"):
            out.append((len(found.group(1)), found.group(2)))
    return out


def strings(value) -> list[str]:
    """Toutes les phrases d'une réponse : les chaînes qui contiennent un espace. Les identifiants n'en ont pas."""
    if isinstance(value, str):
        return [value] if " " in value.strip() else []
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in strings(v)]
    return []


# Les champs qui portent un texte écrit dans la langue de la demande. Tout le reste est un chiffre ou un identifiant.
WRITTEN = {"name", "label", "title", "detail", "text", "description", "rule", "reason", "unit", "source", "sentence", "horizon",
           "variable_label", "branch_label", "note", "question", "limits"}


def numbers(value, key: str | None = None):
    """Une réponse sans ses textes : ce qui doit être identique dans les deux langues."""
    if key in WRITTEN and (isinstance(value, str) or key in ("rule", "limits") and not isinstance(value, dict)):
        return None
    if isinstance(value, dict):
        return {k: numbers(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [numbers(v, key) for v in value]
    return value


class BothLanguagesExist(unittest.TestCase):
    def test_the_two_text_files_of_the_page_have_the_same_keys(self):
        english_keys, french_keys = keys_of(WEB / "texts.en.js"), keys_of(WEB / "texts.fr.js")
        self.assertGreater(len(english_keys), 220)
        self.assertEqual(english_keys, french_keys)

    def test_every_sentence_of_the_engine_is_written_in_both_languages(self):
        calls = 0
        for file in sorted((ROOT / "engine").glob("*.py")) + [ROOT / "api/main.py"]:
            for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "say":
                    calls += 1
                    self.assertEqual((len(node.args), len(node.keywords)), (2, 0), f"{file.name}:{node.lineno}")
                    for arg in node.args:
                        self.assertNotEqual(ast.unparse(arg).strip("f'\""), "", f"{file.name}:{node.lineno}")
        self.assertGreater(calls, 90)

    def test_every_fixed_label_of_the_engine_has_its_english(self):
        self.assertEqual(set(english.ASSUMPTIONS), {a.key for a in ASSUMPTIONS})
        self.assertLessEqual({a.unit for a in ASSUMPTIONS} - {"CHF", "%", "CHF/EUR"}, set(english.UNITS))
        self.assertEqual(set(english.DOORS), {d.key for d in DOORS})
        self.assertEqual(set(english.WORLDS), {w.id for w in W.WORLDS + W.EXTRA})
        self.assertEqual(set(english.WORLD_FIELDS), {f.name for f in fields(World)})
        self.assertEqual(set(english.BLOCKS), set(BLOCKS) | {"recherche"})
        self.assertEqual((set(english.NOT_YET), set(english.REFUSED_CITIES)), (set(NOT_YET), set(REFUSED_CITIES)))
        self.assertEqual(set(NAMES_EN), {p.id for p in POLICIES})
        # Une règle de porte nomme les mêmes hypothèses dans les deux langues.
        named = lambda text: sorted(field for _, field, _, _ in string.Formatter().parse(text) if field)
        for door in DOORS:
            self.assertEqual(named(english.DOORS[door.key][1]), named(door.rule), door.key)
        # Une unité en pour cent reste une unité en pour cent : le tiroir s'en sert pour l'afficher.
        for french, written in english.UNITS.items():
            self.assertEqual(french.startswith("%"), written.startswith("%"))

    def test_every_line_of_the_ledger_shown_by_the_page_has_its_english(self):
        tree, labels = Tree(ALEXIA), set()
        worlds = list(W.WORLD_IDS) + ["chomage_long", "chomage_long@27", "prudent"]
        for path in LINES:
            for w in worlds:
                labels |= {f.label for m in tree.trip(path, w, None)[0].months for f in m.flows}
        for gare in tree.gares:
            for branch in destinations(STORY, gare, tree.h, tree.age0):
                if branch["available"]:
                    for w in ("reference", "chomage_long@27", "perte_job_etudiant"):
                        labels |= {f.label for m in tree.fork(STORY, gare, branch["path"], w, None, None).months for f in m.flows}
        labels |= {f.label for m in tree.observed(STORY, 72, 40000.0, STORY, "reference", None, keep=False)[0].months for f in m.flows}
        labels |= {f.label for m in tree.with_cushion(STORY, 60, 6690.0, "reference", None).months for f in m.flows}
        self.assertGreater(len(labels), 20)
        with i18n.use("en"):
            for label in sorted(labels):
                with self.subTest(label=label):
                    written = i18n.ledger(label)
                    self.assertIsNone(FRENCH.search(written), written)
            # Les libellés composés : la phrase est traduite, les chiffres sont gardés.
            self.assertEqual(i18n.ledger("Pas d'indemnité de chômage : 0 mois cotisés sur 24, il en faut 12"),
                             "No unemployment benefit: 0 months contributed out of 24, 12 are required")
            self.assertEqual(i18n.ledger("Intérêts : Hypothèque"), "Interest: Mortgage")
            self.assertEqual(i18n.ledger("Déménagement (etranger)"), "Move (abroad)")
            self.assertEqual(i18n.ledger("Achat impossible : fonds propres insuffisants (12'000 CHF disponibles ; 110'000 CHF nécessaires "
                                         "hors 2e pilier, frais et réserve compris)"),
                             "Purchase not possible: own funds too low (12'000 CHF available; 110'000 CHF needed outside the 2nd pillar, "
                             "costs and reserve included)")
        with i18n.use("fr"):
            self.assertEqual(i18n.ledger("Loyer"), "Loyer")

    def test_the_banned_words_appear_nowhere_in_english(self):
        page = (WEB / "texts.en.js").read_text(encoding="utf-8")
        self.assertIsNone(BANNED.search(page))
        self.assertEqual(re.findall(r"[^.]*\badvice\b[^.]*\.", page), [" Not a forecast, not advice."] * 2)
        written = [(ROOT / "engine/english.py").read_text(encoding="utf-8")]
        for file in sorted((ROOT / "engine").glob("*.py")) + [ROOT / "api/main.py"]:
            for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "say":
                    written.append(ast.unparse(node.args[0]))
        for text in written:
            self.assertIsNone(re.search(r"chance|probabilit|risk|\bbest\b|recommend|advi[cs]|guarantee", text, re.IGNORECASE), text[:120])


@unittest.skipIf(TestClient is None, "FastAPI non installé")
class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(app)

    def ask(self, lang: str) -> dict:
        """Ce que la page demande pour l'histoire de la démo, dans une langue."""
        q, c = f"?lang={lang}", self.c
        post = lambda route, **body: c.post(f"/{route}{q}", json=body).json()
        return {
            "worlds": c.get(f"/worlds{q}").json(), "assumptions": c.get(f"/assumptions{q}").json(),
            "checks": c.get(f"/checks{q}").json(), "limits": c.get(f"/limits{q}").json(),
            "kit": {k: v for k, v in c.post(f"/checks/starter-kit{q}").json().items() if k not in ("duration_s", "ran_at")},
            "path": post("path", path=STORY, world_id="krach"), "departure": post("node", path=[], gare_month=0),
            "node": post("node", path=STORY, gare_month=72), "seen": post("node", path=STORY, gare_month=72,
                                                                       observation={"gare_month": 72, "value_chf": 40000}),
            "pathways": post("pathways", path=STORY), "adaptive": post("adaptive", path=STORY),
            "policies": post("policies"), "folk": post("folk-rule"),
            "simulate": post("simulate", line_id="master", world_id="chomage_6_mois"),
            "refusals": [post("node", path=[{"block": "phd", "years": 10}], gare_month=0), post("path", path=STORY, world_id="krach@40"),
                         post("path", path=STORY, world_id="covid_2020"), post("adaptive", path=[{"block": "job", "years": 10}]),
                         post("policies", path=[{"block": "job", "years": 10}]), post("node", path=STORY, gare_month=7),
                         post("path", path=STORY, mondes={"tirage": 100}), c.get(f"/scenario/nobody{q}").json()],
        }

    def test_no_french_is_left_in_what_the_routes_answer_in_english(self):
        answers = self.ask("en")
        sentences = strings(answers)
        self.assertGreater(len(sentences), 600)
        for sentence in sentences:
            with self.subTest(sentence=sentence[:80]):
                self.assertIsNone(FRENCH.search(sentence), sentence)
        self.assertEqual(answers["limits"]["source"], "docs/LIMITS.md")
        self.assertEqual(len(answers["limits"]["limits"]), len(self.c.get("/limits?lang=fr").json()["limits"]))
        self.assertTrue(all("detail" in refusal for refusal in answers["refusals"]))

    def test_the_language_changes_no_figure(self):
        english_answers, french_answers = self.ask("en"), self.ask("fr")
        for name in english_answers:
            with self.subTest(route=name):
                if name not in ("refusals", "limits"):
                    self.assertEqual(numbers(english_answers[name]), numbers(french_answers[name]))
        self.assertNotEqual(strings(english_answers["policies"]), strings(french_answers["policies"]))
        self.assertEqual(french_answers["folk"]["sentence"],
                         "« 3 mois d'épargne de précaution suffisent » : vrai dans 8 des 8 mondes testés pour Alexia salariée à 25 ans, "
                         "dans 0 des 8 pour Alexia qui commence son master au même âge. Il lui faudrait 24,8 mois de dépenses de côté "
                         "(55'200 CHF), pas 3.")
        self.assertEqual(english_answers["folk"]["sentence"],
                         "“3 months of emergency savings are enough”: true in 8 of the 8 tested worlds for Alexia employed at 25, "
                         "in 0 of the 8 for Alexia starting her master's at the same age. She would need 24.8 months of expenses set aside "
                         "(55'200 CHF), not 3.")

    def test_the_language_of_a_request_is_the_one_in_its_address_and_english_is_the_default(self):
        name = lambda query: self.c.post(f"/policies{query}", json={}).json()["policies"][0]["name"]
        self.assertEqual((name("?lang=en"), name("?lang=fr")), ("Fixed plan", "Plan figé"))
        before = i18n.current()
        try:
            i18n.set_default("en")
            self.assertEqual((name(""), name("?lang=de"), name("?lang=fr")), ("Fixed plan", "Fixed plan", "Plan figé"))
            i18n.set_default("fr")
            self.assertEqual((name(""), name("?lang=en")), ("Plan figé", "Fixed plan"))
        finally:
            i18n.set_default(before)
        with self.assertRaises(ValueError):
            i18n.set_default("de")


@unittest.skipIf(TestClient is None or test_web.CHROME is None, "Chrome non installé")
class PageInChrome(unittest.TestCase):
    """La page s'ouvre en anglais ; ?lang=fr la passe en français. Les chiffres affichés sont ceux de l'API dans les deux cas."""

    def page(self, query: str = "") -> tuple[str, str]:
        dom = test_web.dom_of(f"/{query}")
        self.assertIn('data-ready="1"', dom, dom[-600:])
        return dom, re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", dom)))

    def test_the_page_opens_in_english_with_a_link_to_french(self):
        dom, text = self.page()
        self.assertRegex(dom, r'<html lang="en"')
        self.assertRegex(dom, r'<a class="language" id="language" href="/\?lang=fr"[^>]*>Français</a>')
        for sentence in ("Alexia, 20, Lausanne, 8'000 CHF set aside", "Scenarios under assumptions, fictional data. Not a forecast, not advice.",
                         "Your route", "Service updates", "Reference world", "Market crash", "Job in Lausanne 5 years, then master's 2 years, then job in Lausanne",
                         "3 stations open out of 6 · Reference world", "Never go into the red", "Career change", "Policies", "Fixed plan or policy",
                         "Three bands: three worlds, not frequencies", "Worst tested world", "Assumptions & evidence", "Last useful transfer"):
            self.assertIn(sentence, text)

    def test_the_screens_of_the_demo_show_no_french_in_english(self):
        for query in ("", "?monde=krach@24&gare=72", "?gare=72&epargne=40000&plan=1", "?station=reconversion&monde=krach", "?politiques=1",
                      "?politiques=fragile", "?regle=1", "?tiroir=registre&mois=62&monde=perte_job_etudiant", "?tiroir=hypotheses"):
            dom, text = self.page(query)
            with self.subTest(page=query):
                shown = text.replace("Français", "")                      # le lien vers l'autre langue porte son nom
                found = FRENCH.search(shown)
                self.assertIsNone(found, shown[max(0, (found.start() if found else 0) - 60):(found.end() if found else 0) + 60])

    def test_the_english_page_shows_the_figures_and_sentences_of_the_api(self):
        c = TestClient(app)
        table = c.post("/policies?lang=en", json={}).json()
        dom, text = self.page("?politiques=1")
        for row in table["policies"]:
            self.assertIn(row["name"], text)
            if row["rule"]:
                self.assertIn(row["rule"]["text"], text)
        long = table["cells"]["equilibre"]["chomage_long"]
        self.assertIn(f"{long['doors_open']} goals out of 6 Master's stopped at 26 Peak borrowing {test_web.swiss(long['peak_financing_chf'])} "
                      f"Regret {test_web.swiss(long['regret_chf'])} the rule applies", text)
        self.assertIn("Long unemployment at 24 (12 months)", text)
        sign = next(r for r in c.post("/pathways?lang=en", json={"path": STORY}).json()["by_world"]["krach"]["doors"] if r["key"] == "reconversion")
        _, text = self.page("?gare=72&monde=krach")
        self.assertIn(f"Signpost {sign['signpost']['text']}", text)
        self.assertIn("Junction · age 26", text)
        _, text = self.page("?regle=1")
        self.assertIn(c.post("/folk-rule?lang=en", json={}).json()["sentence"], text)

    def test_french_is_one_parameter_away_and_keeps_the_rest_of_the_address(self):
        dom, text = self.page("?monde=krach&gare=72&lang=fr")
        self.assertRegex(dom, r'<html lang="fr"')
        self.assertRegex(dom, r'<a class="language" id="language" href="/\?monde=krach&amp;gare=72"[^>]*>English</a>')
        self.assertIn("Gare de correspondance · 26 ans", text)
        self.assertIn("Ton trajet", text)
        dom, _ = self.page("?monde=krach&gare=72")
        self.assertRegex(dom, r'<a class="language" id="language" href="/\?monde=krach&amp;gare=72&amp;lang=fr"')


if __name__ == "__main__":
    unittest.main()
