"""Les crises combinées : deux crises dans le même monde (« krach@24+chomage_long@25 »).

Le monde combiné est construit champ par champ et mois par mois, sur l'écart de chaque crise au monde de référence
(engine/worlds.py), puis simulé par le moteur comme n'importe quel monde : aucun résultat n'est additionné.
Un monde à une seule crise ne passe par aucune ligne de ce code : les autres fichiers de tests, inchangés, le prouvent.
"""
from __future__ import annotations

from engine import i18n

i18n.set_default("fr")      # ces tests attendent les phrases du moteur en français ; l'anglais est vérifié plus bas, demande par demande

import html
import itertools
import json
import re
import unittest
from dataclasses import asdict, fields
from pathlib import Path

from engine import worlds as W
from engine.blocks import blocks_to_ops
from engine.contract import World
from engine.explore import doors_of
from engine.simulate import load_scenario, reference_world, run, run_ops, theta_for

try:
    from fastapi.testclient import TestClient
    from api.main import app
    import test_english
    import test_tree
    import test_web
except ImportError:  # pragma: no cover
    TestClient = None

ROOT = Path(__file__).resolve().parents[1]
ALEXIA = load_scenario(ROOT / "engine/scenarios/alexia.json")
TH = theta_for(ALEXIA)
H, AGE0 = ALEXIA.horizon_months, ALEXIA.profile.age
STORY = [{"block": "job", "years": 5}, {"block": "master", "years": 2}, {"block": "job", "years": 3}]     # l'histoire de la démo
WORK = [{"block": "job", "years": 10}]                                                                    # « emploi seul »
BERLIN = [{"block": "job_abroad", "years": 10}]
KINDS = ("krach", "chomage_6_mois", "perte_job_etudiant", "inflation", "crise_immobiliere", "franc_faible", "chomage_long")
EXAMPLE = "krach@24+chomage_long@25"
REFERENCE = reference_world(TH, H)


def world(world_id: str) -> list[World]:
    return W.build(TH, world_id, H, AGE0)


def canonical(world_id) -> str:
    return W.canonical(world_id, TH, H, AGE0)


def live(path: list[dict], world_id: str):
    """Le moteur, sans passer par l'arbre ni par une route : le trajet simulé depuis le départ, dans ce monde."""
    return run_ops(ALEXIA.profile, blocks_to_ops(path, TH, H), H, TH, world(world_id))


def lost(path: list[dict], world_id: str) -> list[str]:
    """Les objectifs que ce monde fait perdre : tenus sans choc, perdus ici."""
    calm, here = doors_of(live(path, "reference"), TH, AGE0), doors_of(live(path, world_id), TH, AGE0)
    return [key for key in here if calm[key] and not here[key]]


def months_of(result) -> list[dict]:
    return asdict(result)["months"]


class TheWorld(unittest.TestCase):
    """Ce qu'est un monde à deux crises, mois par mois, avant toute simulation."""

    def test_two_crises_that_never_meet_are_each_itself_where_it_acts_and_the_reference_elsewhere(self):
        """Tous les couples de types, à six âges : là où une seule crise s'écarte du monde de référence, le monde combiné
        est cette crise, à l'identique ; là où aucune ne s'écarte, c'est le monde de référence ; là où les deux
        s'écartent sur le même champ, la somme des écarts pour un nombre, « oui » pour un champ oui ou non."""
        alone = {f"{kind}@{age}": world(f"{kind}@{age}") for kind in KINDS for age in (21, 23, 24, 25, 27, 29)}
        names = [field.name for field in fields(World)]
        apart = meeting = 0
        for first, second in itertools.permutations(alone, 2):
            a, b, both = alone[first], alone[second], world(f"{first}+{second}")
            self.assertEqual(len(both), H)
            meet = False
            for t in range(H):
                if a[t] == REFERENCE[t]:
                    self.assertEqual(both[t], b[t], (first, second, t))
                elif b[t] == REFERENCE[t]:
                    self.assertEqual(both[t], a[t], (first, second, t))
                else:
                    for name in names:
                        usual, x, y, got = (getattr(w[t], name) for w in (REFERENCE, a, b, both))
                        if x != usual and y != usual:
                            meet = True
                            self.assertEqual(got, (not usual) if isinstance(usual, bool) else usual + (x - usual) + (y - usual),
                                             (first, second, t, name))
                        else:
                            self.assertEqual(got, y if x == usual else x, (first, second, t, name))
            apart, meeting = apart + (not meet), meeting + meet
        # 7 types × 6 âges : 42 crises, et tous leurs couples dans les deux ordres.
        self.assertEqual(apart + meeting, 42 * 41)
        self.assertGreater(apart, 1500, "La plupart des couples ne se rencontrent sur aucun champ")
        self.assertGreater(meeting, 50, "Et certains se rencontrent : la règle d'addition est vraiment mise à l'épreuve")

    def test_the_example_is_a_crash_at_24_then_twelve_months_of_unemployment_at_25(self):
        both, crash, long = world(EXAMPLE), world("krach@24"), world("chomage_long@25")
        different = [t for t in range(H) if both[t] != REFERENCE[t]]
        self.assertEqual(different, [48] + list(range(60, 72)))
        self.assertEqual((both[48], both[48].market_return_monthly), (crash[48], -0.3))
        self.assertEqual([both[t] for t in range(60, 72)], [long[t] for t in range(60, 72)])
        self.assertTrue(all(both[t].job_lost for t in range(60, 72)))
        self.assertEqual(W.shock_start(TH, EXAMPLE, H, AGE0), 48)

    def test_where_two_crises_meet_numbers_add_their_gaps_and_a_yes_stays_a_yes(self):
        # Deux crises immobilières qui se chevauchent pendant un an : la baisse des prix y est deux fois l'écart d'une seule.
        housing, single = world("crise_immobiliere@24+crise_immobiliere@25"), world("crise_immobiliere@24")
        usual, fall = REFERENCE[48].house_return_monthly, single[48].house_return_monthly
        self.assertLess(fall, usual)
        for t in range(H):
            expected = fall if 48 <= t < 60 or 72 <= t < 84 else usual + 2 * (fall - usual) if 60 <= t < 72 else usual
            self.assertEqual(housing[t].house_return_monthly, expected, t)
        # Deux poussées d'inflation : les niveaux de prix s'ajoutent, 6 % puis encore 6 %.
        prices = world("inflation@21+inflation@23")
        self.assertEqual((prices[36].cost_index, round(prices[-1].cost_index, 9)), (1.06, 1.12))
        # Deux pertes d'emploi qui se chevauchent n'en font qu'une : douze mois sans emploi, pas dix-huit.
        jobs = world("chomage_6_mois@24+chomage_long@24")
        self.assertEqual([t for t in range(H) if jobs[t].job_lost], list(range(48, 60)))
        # Chaque crise garde sa gravité : un krach une fois et demie plus fort, un chômage deux fois plus court.
        dosed = world("krach@24~150+chomage_long@25~50")
        self.assertEqual(dosed[48], world("krach@24~150")[48])
        self.assertEqual([t for t in range(H) if dosed[t].job_lost], list(range(60, 66)))

    def test_the_order_of_the_two_crises_does_not_matter(self):
        """La forme canonique range les crises par âge de début, puis par type, et écrit toujours leur âge."""
        for written, expected in ((EXAMPLE, EXAMPLE), ("chomage_long@25+krach@24", EXAMPLE), ("  chomage_long@25 +  krach@24 ", EXAMPLE),
                                  ("chomage_long+krach", "krach@23+chomage_long@24"), ("krach@24+chomage_long", "chomage_long@24+krach@24"),
                                  ("chomage_long@24+chomage_long@23", "chomage_long@23+chomage_long@24"),
                                  ("chomage_long@25~50+krach@24~150", "krach@24~150+chomage_long@25~50")):
            with self.subTest(written=written):
                self.assertEqual(canonical(written), expected)
                self.assertEqual(canonical(expected), expected, "Une forme canonique est sa propre forme canonique")
                self.assertEqual(world(written), world(expected))
        for first, second in itertools.combinations([f"{kind}@{age}" for kind in KINDS for age in (22, 26)], 2):
            self.assertEqual(world(f"{first}+{second}"), world(f"{second}+{first}"), (first, second))
            self.assertEqual(canonical(f"{first}+{second}"), canonical(f"{second}+{first}"))
        # Demandé deux fois sous deux écritures, un monde n'est testé qu'une fois.
        self.assertEqual(W.asked(["reference", EXAMPLE, "chomage_long@25+krach@24", "krach"], TH, H, AGE0), ("reference", EXAMPLE, "krach"))
        self.assertEqual(W.asked([EXAMPLE]), (EXAMPLE,))

    def test_the_same_kind_of_crisis_is_allowed_twice_at_two_different_ages(self):
        """Deux périodes de chômage dans une vie : c'est permis, et c'est souvent le monde le plus dur."""
        twice = world("chomage_long@23+chomage_long@24")
        self.assertEqual([t for t in range(H) if twice[t].job_lost], list(range(36, 60)))
        self.assertEqual(canonical("krach@22+krach@26"), "krach@22+krach@26")

    def test_what_is_refused_says_why(self):
        for refused, error, why in (
                ("krach@24+chomage_long@25+inflation", ValueError, "au plus 2 crises"),
                ("reference+krach", ValueError, "« Monde de référence » est un monde entier, pas une crise"),
                ("krach+prudent", ValueError, "« Monde prudent » est un monde entier, pas une crise"),
                ("krach+krach@23", ValueError, "deux fois la même crise au même âge"),          # 23 ans est l'âge d'origine du krach
                ("krach@24+krach@24~150", ValueError, "ce serait une gravité, pas deux crises"),
                ("krach@24+", ValueError, "il en manque une"), ("+krach@24", ValueError, "il en manque une"),
                ("krach@40+chomage_long", ValueError, "de 21 à 29 ans"), ("krach@24~500+chomage_long", ValueError, "de 25 à 300 %"),
                ("krach@vingt+chomage_long", ValueError, "nombre entier d'années"), ("krach@24+covid_2020", KeyError, "pas encore disponible")):
            with self.subTest(refused=refused):
                for ask in (canonical, world, lambda w: W.asked([w], TH, H, AGE0), lambda w: W.describe(TH, H, AGE0, [w])):
                    with self.assertRaisesRegex(error, why):
                        ask(refused)
        # Un type, un âge et une gravité se lisent une crise à la fois : ces fonctions refusent un monde combiné, clairement.
        for one_crisis_only in (W.split, W.gravity, W.named, lambda w: W.default_age(TH, w, H, AGE0)):
            with self.assertRaisesRegex(ValueError, "combine plusieurs crises"):
                one_crisis_only(EXAMPLE)
        with self.assertRaises(KeyError):
            W.asked(["krach@24+covid_2020"])

    def test_a_combined_world_is_described_like_the_others_with_each_of_its_crises(self):
        described = W.describe(TH, H, AGE0, ["reference", "krach@24", "chomage_long@25+krach@24"])
        self.assertEqual([w["id"] for w in described], ["reference", "krach@24", EXAMPLE])
        self.assertTrue(all("crises" not in w for w in described[:2]), "Un monde à une seule crise est décrit comme avant")
        both = described[2]
        self.assertEqual((both["name"], both["type"], both["age"], both["default_age"], both["adjustable"], both["gravity"], both["catalog_id"]),
                         ("Krach des marchés à 24 ans + chômage long à 25 ans", EXAMPLE, 24, None, False, None, None))
        self.assertTrue(both["description"].startswith("Deux crises dans le même monde. Les placements chutent brutalement"))
        self.assertEqual([(c["id"], c["type"], c["name"], c["age"], c["gravity"], c["from_month"], c["to_month"]) for c in both["crises"]],
                         [("krach@24", "krach", "Krach des marchés à 24 ans", 24, 100, 48, 49),
                          ("chomage_long@25", "chomage_long", "Chômage long à 25 ans", 25, 100, 60, 72)])
        self.assertEqual([(p["field"], p["from_month"], p["to_month"], p["months"], p["value"]) for p in both["parameters"]],
                         [("market_return_monthly", 48, 49, 1, -0.3), ("job_lost", 60, 72, 12, True)])
        # Une ligne de paramètre par période : avant la rencontre, pendant, après.
        housing = W.describe(TH, H, AGE0, ["crise_immobiliere@25+crise_immobiliere@24"])[0]
        self.assertEqual(housing["name"], "Crise immobilière à 24 ans + crise immobilière à 25 ans")
        self.assertEqual(housing["description"], "Deux crises dans le même monde. Le prix des logements baisse pendant deux ans.")
        self.assertEqual([(p["from_month"], p["to_month"]) for p in housing["parameters"]], [(48, 60), (60, 72), (72, 84)])
        fall = [p["value"] - p["reference"] for p in housing["parameters"]]
        self.assertAlmostEqual(fall[1], 2 * fall[0], places=12)
        self.assertEqual(fall[2], fall[0])
        # La gravité d'une crise se lit dans son nom ; les crises d'un monde à une seule crise se lisent de la même façon.
        self.assertEqual(W.describe(TH, H, AGE0, ["krach@24~150+chomage_long@25"])[0]["name"],
                         "Krach des marchés à 24 ans, gravité 150 % + chômage long à 25 ans")
        self.assertEqual([c["id"] for c in W.crises(TH, "krach", H, AGE0)], ["krach@23"])
        self.assertEqual((W.crises(TH, "reference", H, AGE0), W.crises(TH, "prudent", H, AGE0)), ([], []))
        with i18n.use("en"):
            english = W.describe(TH, H, AGE0, [EXAMPLE, "krach@24~150+chomage_long@25"])
            self.assertEqual([w["name"] for w in english], ["Market crash at 24 + long unemployment at 25",
                                                            "Market crash at 24, severity 150% + long unemployment at 25"])
            self.assertTrue(english[0]["description"].startswith("Two crises in the same world. Investments fall sharply"))


class TheResults(unittest.TestCase):
    """Ce que le moteur calcule dans un monde à deux crises. Il simule ce monde : il n'additionne pas deux résultats."""

    def test_before_the_second_crisis_every_month_is_the_one_of_the_first_crisis_alone(self):
        for path, both in ((STORY, EXAMPLE), (WORK, EXAMPLE), (WORK, "chomage_long@23+chomage_long@24"), (STORY, "chomage_long@23+chomage_long@24"),
                           (BERLIN, "franc_faible@22+chomage_long@26"), (WORK, "inflation@21+krach@27"), (STORY, "perte_job_etudiant@25+krach@28")):
            first, second = W.crises(TH, both, H, AGE0)
            with self.subTest(path=path[0]["block"], world=both):
                together, alone = months_of(live(path, both)), months_of(live(path, first["id"]))
                self.assertEqual(together[:second["from_month"]], alone[:second["from_month"]])
                # Et le monde combiné n'est pas la première crise seule : la seconde y est bien.
                self.assertNotEqual(world(both), world(first["id"]))

    def test_on_the_work_only_route_the_example_costs_the_sum_of_its_two_crises_to_the_cent(self):
        """« krach@24+chomage_long@25 », emploi seul : le krach ne touche que les placements, le chômage que les revenus de
        l'année suivante. Les deux écarts de patrimoine s'ajoutent, au centime."""
        calm, crash, long, both = (live(WORK, w) for w in ("reference", "krach@24", "chomage_long@25", EXAMPLE))
        self.assertEqual([round(r.net_worth_end_chf, 2) for r in (calm, crash, long, both)], [175904.25, 166247.76, 159503.13, 149846.64])
        gap = lambda r: r.net_worth_end_chf - calm.net_worth_end_chf
        self.assertEqual((round(gap(crash), 2), round(gap(long), 2)), (-9656.49, -16401.12))
        self.assertEqual(round(gap(both), 2), round(gap(crash) + gap(long), 2))
        self.assertEqual(round(gap(both), 2), -26057.61)
        self.assertEqual([sum(doors_of(r, TH, AGE0).values()) for r in (calm, crash, long, both)], [6, 5, 5, 5])
        self.assertEqual((lost(WORK, "krach@24"), lost(WORK, "chomage_long@25"), lost(WORK, EXAMPLE)), (["logement"],) * 3)

    def test_a_crisis_that_does_not_touch_the_route_leaves_the_other_one_unchanged(self):
        """Dans l'histoire de la démo, Alexia est en master à 25 ans : douze mois de chômage ne la touchent pas.
        Le monde à deux crises donne alors, mois par mois et ligne par ligne, le trajet du krach seul."""
        both, crash, long, calm = (live(STORY, w) for w in (EXAMPLE, "krach@24", "chomage_long@25", "reference"))
        self.assertEqual(months_of(long), months_of(calm))
        self.assertEqual(months_of(both), months_of(crash))
        self.assertEqual((round(both.net_worth_end_chf, 2), round(both.peak_financing_chf, 2), sum(doors_of(both, TH, AGE0).values())),
                         (87092.68, 14233.94, 2))
        self.assertEqual(lost(STORY, EXAMPLE), ["reconversion"])

    def test_the_same_two_crises_in_the_other_order_no_longer_add_up(self):
        """Le contre-exemple. Chômage long à 24 ans, puis krach à 25 ans, emploi seul : après un an de chômage, Alexia a moins
        de placements quand le krach arrive, et il lui coûte moins. Le monde combiné coûte 2'500 CHF de moins que la somme
        des deux crises prises seules : le moteur simule ce monde, il n'additionne pas deux résultats."""
        calm = live(WORK, "reference").net_worth_end_chf
        long, crash, both = (live(WORK, w).net_worth_end_chf - calm for w in ("chomage_long@24", "krach@25", "chomage_long@24+krach@25"))
        self.assertEqual((round(long, 2), round(crash, 2), round(both, 2)), (-15111.56, -12156.72, -24768.05))
        self.assertEqual((round(long + crash, 2), round(both - (long + crash), 2)), (-27268.27, 2500.23))
        # Le krach de 25 ans coûte plus que celui de 24 ans, pris seuls : il y a un an de placements en plus à perdre.
        self.assertLess(crash, live(WORK, "krach@24").net_worth_end_chf - calm)

    def test_two_long_unemployment_spells_in_a_row_cost_far_more_than_twice_one(self):
        """L'autre contre-exemple, et le monde le plus dur trouvé à gravité normale. Deux chômages longs à la suite, à 23 et
        24 ans : la seconde année, Alexia n'a plus assez cotisé pour être indemnisée. Seule, chaque crise fait perdre un
        objectif ; ensemble, quatre sur le trajet « emploi seul », trois dans l'histoire de la démo."""
        twice = "chomage_long@23+chomage_long@24"
        calm = live(WORK, "reference").net_worth_end_chf
        first, second, both = (live(WORK, w) for w in ("chomage_long@23", "chomage_long@24", twice))
        gap = lambda r: round(r.net_worth_end_chf - calm, 2)
        self.assertEqual((gap(first), gap(second), gap(both)), (-15001.97, -15111.56, -64427.29))
        self.assertEqual((lost(WORK, "chomage_long@23"), lost(WORK, "chomage_long@24")), (["logement"], ["logement"]))
        self.assertEqual(lost(WORK, twice), ["jamais_rouge", "coussin", "etudes", "logement"])
        self.assertEqual((both.first_negative_month, round(both.peak_financing_chf, 2)), (56, 10441.86))
        self.assertEqual((first.first_negative_month, second.first_negative_month), (None, None))
        # La raison est écrite dans le registre : pas d'indemnité pendant la seconde période, faute de mois cotisés.
        refused = lambda r: [m.month for m in r.months if any(f.label.startswith("Pas d'indemnité de chômage") for f in m.flows)]
        self.assertEqual((refused(first), refused(second), refused(both)), ([], [], list(range(49, 60))))
        self.assertIn("Pas d'indemnité de chômage : 11 mois cotisés sur 24, il en faut 12", [f.label for f in both.months[49].flows])
        # Dans l'histoire de la démo : chaque crise seule fait perdre « Reconversion » ; les deux, trois objectifs.
        self.assertEqual((lost(STORY, "chomage_long@23"), lost(STORY, "chomage_long@24"), lost(STORY, twice)),
                         (["reconversion"], ["reconversion"], ["coussin", "reconversion", "resilience"]))
        self.assertEqual(round(live(STORY, twice).peak_financing_chf, 2), 65024.31)


@unittest.skipIf(TestClient is None, "FastAPI non installé : .venv/bin/pip install -r requirements.txt")
class TheRoutes(unittest.TestCase):
    """Les routes acceptent un monde à deux crises partout où elles acceptent un monde, et rendent les chiffres du moteur."""
    MONDES = ["reference", "krach", "chomage_long@25+krach@24", "crise_immobiliere@24+chomage_long@27"]
    IDS = ["reference", "krach", EXAMPLE, "crise_immobiliere@24+chomage_long@27"]

    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(app)

    def post(self, route: str, **body):
        response = self.c.post(f"/{route}", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_a_route_and_its_branches_in_a_combined_world_are_the_numbers_of_the_engine(self):
        trip = self.post("path", path=STORY, world_id="chomage_long@25+krach@24", mondes=self.MONDES)
        self.assertEqual((trip["world_id"], list(trip["by_world"])), (EXAMPLE, self.IDS))
        for w in self.IDS:
            self.assertEqual(trip["by_world"][w], test_tree.expected(STORY, w, detailed=True), w)
        self.assertEqual(trip["months"], json.loads(json.dumps(months_of(live(STORY, EXAMPLE)))))
        self.assertEqual(trip["bands"]["pire"]["doors_open"], {"value": 1, "world_id": "crise_immobiliere@24+chomage_long@27"})
        node = self.post("node", path=STORY, gare_month=60, mondes=self.MONDES)
        self.assertEqual((node["worlds"], list(node["state_by_world"])), (self.IDS, self.IDS))
        for branch in node["branches"]:
            for w in self.IDS:
                self.assertEqual(branch["by_world"][w], test_tree.expected(branch["path"], w), (branch["id"], w))
        ways = self.post("pathways", path=STORY, mondes=self.MONDES)
        self.assertEqual((ways["worlds"], list(ways["by_world"])), (self.IDS, self.IDS))
        plan = self.post("adaptive", path=STORY, mondes=self.MONDES,
                         rule={"gare_month": 72, "variable": "liquidite_chf", "threshold_chf": 48200, "branch_id": "emploi"})
        self.assertEqual((plan["worlds"], plan["summary"]["worlds"]), (self.IDS, 4))
        for w in self.IDS:
            self.assertEqual(plan["by_world"][w]["fixed"], test_tree.expected(STORY, w), w)
        # Les routes d'une ligne du scénario prennent aussi un monde à deux crises.
        line = self.post("simulate", line_id="travailler", world_id=EXAMPLE)
        direct = run(ALEXIA, "travailler", None, world(EXAMPLE), EXAMPLE)
        self.assertEqual((line["net_worth_end_chf"], round(line["net_worth_end_chf"], 2)), (direct.net_worth_end_chf, 149846.64))
        self.assertEqual(line["months"], json.loads(json.dumps(months_of(direct))))
        self.assertEqual(self.post("compare", station_id="depart", world_id=EXAMPLE)["world_id"], EXAMPLE)

    def test_a_junction_says_where_each_tested_crisis_stands(self):
        """À une gare : à venir, en cours ou passée, crise par crise, dans chaque monde testé. L'état d'une gare est celui du
        début du mois : une crise qui commence ce mois-là est à venir ; une crise dont le monde dure encore est en cours."""
        expected = {48: (True, ["a_venir", "a_venir"], ["a_venir", "a_venir"]),
                    60: (False, ["passee", "a_venir"], ["en_cours", "a_venir"]),
                    72: (False, ["passee", "passee"], ["passee", "a_venir"]),
                    96: (False, ["passee", "passee"], ["passee", "passee"])}
        for gare, (before, example, housing) in expected.items():
            state = self.post("node", path=STORY, gare_month=gare, mondes=self.MONDES)["state_by_world"]
            with self.subTest(gare=gare):
                self.assertEqual([c["status"] for c in state[EXAMPLE]["crises"]], example)
                self.assertEqual([c["status"] for c in state[self.IDS[3]]["crises"]], housing)
                # `avant_le_choc` : aucune des deux crises n'a commencé. Les deux mondes commencent à 24 ans.
                self.assertEqual([(state[w]["avant_le_choc"], state[w]["choc_month"], state[w]["choc_age"]) for w in self.IDS[2:]],
                                 [(before, 48, 24)] * 2)
                self.assertEqual([(c["id"], c["from_month"], c["to_month"]) for c in state[EXAMPLE]["crises"]],
                                 [("krach@24", 48, 49), ("chomage_long@25", 60, 72)])
                # Un monde habituel a une seule crise ; le monde de référence n'en a aucune.
                self.assertEqual(state["reference"]["crises"], [])
                self.assertEqual([(c["id"], c["status"]) for c in state["krach"]["crises"]], [("krach@23", "passee")])
                self.assertEqual(state["krach"]["avant_le_choc"], False)
        # Les sept mondes habituels, gare par gare. La poussée d'inflation et le franc plus faible ne reviennent pas au monde
        # de référence : ils restent en cours. La crise immobilière dure deux ans, de 24 à 26 ans.
        kinds = ["krach", "chomage_6_mois", "perte_job_etudiant", "inflation", "crise_immobiliere", "franc_faible"]
        coming, running, over = "a_venir", "en_cours", "passee"
        usual = {12: [coming, coming, coming, coming, coming, coming], 24: [coming, coming, coming, running, coming, running],
                 36: [coming, over, coming, running, coming, running], 60: [over, over, coming, running, running, running],
                 72: [over, over, over, running, over, running], 108: [over, over, over, running, over, running]}
        for gare, statuses in usual.items():
            state = self.post("node", path=STORY, gare_month=gare)["state_by_world"]
            with self.subTest(gare=gare):
                self.assertEqual([[c["status"] for c in state[kind]["crises"]] for kind in kinds], [[status] for status in statuses])
                # « Avant le choc » et « à venir » disent la même chose, pour un monde à une seule crise.
                self.assertEqual([state[kind]["avant_le_choc"] for kind in kinds], [status == coming for status in statuses])

    def test_the_worlds_route_reads_the_plus_sign_of_an_address(self):
        """Dans une adresse, un « + » arrive comme un espace : la route le relit comme un « + »."""
        expected = json.loads(json.dumps(W.describe(TH, H, AGE0, ["reference", EXAMPLE])))
        for address in ("/worlds?mondes=reference,krach@24+chomage_long@25", "/worlds?mondes=reference,krach@24%2Bchomage_long@25",
                        "/worlds?mondes=reference,chomage_long@25+krach@24", "/worlds?mondes=reference,%20chomage_long@25%20%2B%20krach@24"):
            with self.subTest(address=address):
                answer = self.c.get(address)
                self.assertEqual(answer.status_code, 200, answer.text)
                self.assertEqual(answer.json(), expected)
        self.assertEqual(self.c.get("/worlds", params={"mondes": f"reference,{EXAMPLE}"}).json(), expected)
        self.assertEqual([w["id"] for w in expected], ["reference", EXAMPLE])

    def test_the_routes_refuse_what_the_engine_refuses_and_say_why(self):
        for route in ("path", "node", "pathways", "adaptive"):
            for refused, status, why in (("krach@24+chomage_long@25+inflation", 422, "au plus 2 crises"),
                                         ("krach@24+krach@24", 422, "deux fois la même crise au même âge"),
                                         ("reference+krach", 422, "monde entier"), ("krach@24+chomage_long@31", 422, "de 21 à 29 ans"),
                                         ("krach@24+covid_2020", 400, "pas encore disponible")):
                with self.subTest(route=route, refused=refused):
                    answer = self.c.post(f"/{route}", json={"path": STORY, "mondes": ["reference", refused]})
                    self.assertEqual(answer.status_code, status, answer.text)
                    self.assertIn(why, answer.json()["detail"])
        self.assertEqual(self.c.post("/path", json={"path": STORY, "world_id": "krach@24+krach@24"}).status_code, 422)
        self.assertEqual(self.c.get("/worlds?mondes=krach@24+chomage_long@25+inflation").status_code, 422)
        self.assertEqual(self.c.get("/worlds?mondes=krach@24+covid_2020").status_code, 400)
        self.assertEqual(self.c.post("/simulate", json={"line_id": "travailler", "world_id": "krach+krach@23"}).status_code, 422)
        # Le tableau de valeur garde une crise par monde, et le dit.
        table = self.c.post("/policies", json={"mondes": ["reference", EXAMPLE]})
        self.assertEqual((table.status_code, table.json()["detail"]),
                         (422, f"Le tableau de valeur garde une crise par monde : « {EXAMPLE} » en combine deux."))

    def ask(self, lang: str) -> dict:
        q = f"?lang={lang}"
        post = lambda route, **body: self.c.post(f"/{route}{q}", json=body).json()
        return {
            "worlds": self.c.get(f"/worlds{q}&mondes=reference,{EXAMPLE},crise_immobiliere@24%2Bcrise_immobiliere@25,krach@24~150%2Bchomage_long@25").json(),
            "path": post("path", path=STORY, world_id=EXAMPLE, mondes=self.MONDES),
            "node": post("node", path=STORY, gare_month=60, mondes=self.MONDES),
            "pathways": post("pathways", path=STORY, mondes=self.MONDES),
            "adaptive": post("adaptive", path=STORY, mondes=self.MONDES,
                             rule={"gare_month": 72, "variable": "liquidite_chf", "threshold_chf": 48200, "branch_id": "emploi"}),
            "simulate": post("simulate", line_id="travailler", world_id=EXAMPLE),
            "refusals": [post("path", path=STORY, world_id="krach@24+chomage_long@25+inflation"), post("path", path=STORY, world_id="krach+krach@23"),
                         post("path", path=STORY, world_id="reference+krach"), post("path", path=STORY, world_id="krach@24+"),
                         post("policies", mondes=["reference", EXAMPLE]), post("node", path=STORY, gare_month=60, mondes=["krach@24+prudent"])],
        }

    def test_a_combined_world_is_written_in_both_languages_with_the_same_figures(self):
        english, french = self.ask("en"), self.ask("fr")
        sentences = test_english.strings(english)
        self.assertGreater(len(sentences), 150)
        for sentence in sentences:
            with self.subTest(sentence=sentence[:80]):
                self.assertIsNone(test_english.FRENCH.search(sentence), sentence)
                self.assertIsNone(test_english.BANNED.search(sentence), sentence)
        for name in english:
            if name != "refusals":
                with self.subTest(route=name):
                    self.assertEqual(test_english.numbers(english[name]), test_english.numbers(french[name]))
        self.assertTrue(all("detail" in refusal for refusal in english["refusals"] + french["refusals"]))
        self.assertEqual([w["name"] for w in english["worlds"]][1:],
                         ["Market crash at 24 + long unemployment at 25", "Housing downturn at 24 + housing downturn at 25",
                          "Market crash at 24, severity 150% + long unemployment at 25"])
        self.assertEqual([w["name"] for w in french["worlds"]][1:],
                         ["Krach des marchés à 24 ans + chômage long à 25 ans", "Crise immobilière à 24 ans + crise immobilière à 25 ans",
                          "Krach des marchés à 24 ans, gravité 150 % + chômage long à 25 ans"])
        self.assertEqual([c["name"] for c in english["node"]["state_by_world"][EXAMPLE]["crises"]], ["Market crash at 24", "Long unemployment at 25"])
        self.assertEqual(english["refusals"][0]["detail"], "A world holds at most 2 crises: “krach@24+chomage_long@25+inflation” has 3.")
        self.assertEqual(french["refusals"][0]["detail"], "Un monde contient au plus 2 crises : « krach@24+chomage_long@25+inflation » en a 3.")

    def test_the_limits_say_what_a_combined_world_is_and_is_not(self):
        for lang, sentence in (("fr", "Crises combinées : un monde contient deux crises au plus"), ("en", "Combined crises: a world holds two crises at most")):
            limits = self.c.get(f"/limits?lang={lang}").json()["limits"]
            self.assertEqual(sum(sentence in limit for limit in limits), 1)
            self.assertFalse(any("pas de crises combinées" in limit or "no combined crises" in limit for limit in limits))


@unittest.skipIf(TestClient is None or test_web.CHROME is None, "Chrome n'est pas installé sur cette machine")
class ThePage(unittest.TestCase):
    """Chrome sans fenêtre : un monde à deux crises donné dans l'adresse devient une pastille de plus, et tout l'écran le suit."""

    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(app)
        cls.path = cls.c.get("/scenario/alexia").json()["default_path"]
        cls.ids = [w["id"] for w in cls.c.get("/worlds").json()] + [EXAMPLE]

    def page(self, query: str, lang: str = "fr") -> tuple[str, str]:
        dom = test_web.dom_of(f"/{query}{'&lang=fr' if lang == 'fr' else ''}")
        self.assertIn('data-ready="1"', dom, dom[-800:])
        return dom, re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", dom)))

    def api(self, route: str, **body) -> dict:
        return self.c.post(f"/{route}", json=body).json()

    def test_a_combined_world_in_the_address_is_one_more_pill_and_the_screen_follows(self):
        trip = self.api("path", path=self.path, world_id=EXAMPLE, mondes=self.ids)
        node = self.api("node", path=self.path, gare_month=60, mondes=self.ids)
        dom, text = self.page("?monde=krach@24+chomage_long@25&gare=60")
        # Huit pastilles : les sept mondes habituels, et le monde de l'adresse, affiché. Il n'a pas d'âge à régler.
        self.assertEqual(re.findall(r'<button[^>]*data-world="([^"]*)"', dom), self.ids)
        self.assertRegex(dom, r'<body[^>]*data-world="krach@24\+chomage_long@25"')
        self.assertRegex(dom, r'<body[^>]*data-selected="gare:60"')
        pill = re.search(r'<button[^>]*data-world="krach@24\+chomage_long@25"[^>]*>([^<]*)</button>', dom)
        self.assertEqual((html.unescape(pill.group(1)), 'aria-pressed="true"' in pill.group(0)),
                         ("Krach des marchés à 24 ans + chômage long à 25 ans", True))
        self.assertRegex(dom, r'<div[^>]*id="traffic-age"[^>]*hidden')
        self.assertNotIn("Début de la crise", text)
        # « Info trafic » décrit les deux crises, avec les mots et les chiffres du moteur.
        self.assertIn("Deux crises dans le même monde. Les placements chutent brutalement, en un mois. Perte d'emploi pendant douze mois", text)
        self.assertIn("Rendement des placements, par mois : −30 % (+0,2 % dans le monde de référence), à 24 ans.", text)
        self.assertIn("Perte d'emploi de 25 ans à 26 ans.", text)
        # La carte et la fiche montrent les chiffres de ce monde.
        shown = trip["by_world"][EXAMPLE]
        self.assertIn(f"{shown['doors_open']} stations ouvertes sur 6 · Krach des marchés à 24 ans + chômage long à 25 ans", text)
        for branch in node["branches"]:
            s = branch["by_world"][EXAMPLE]
            self.assertIn(f"{s['doors_open']} stations ouvertes sur 6 · financement max. {test_web.swiss(s['peak_financing_chf'])} · "
                          f"patrimoine à la fin {test_web.swiss(s['net_worth_end_chf'])}", text)
        # La fiche de la gare de 25 ans : où en est chacune des deux crises, puis les crises seules, avec les mêmes trois états.
        self.assertEqual([c["status"] for c in node["state_by_world"][EXAMPLE]["crises"]], ["passee", "a_venir"])
        self.assertIn("Monde à deux crises, à 25 ans : krach des marchés à 24 ans (déjà eu lieu) et chômage long à 25 ans (à venir).", text)
        self.assertIn("À 25 ans, ces crises testées ont déjà eu lieu : krach des marchés et six mois de chômage. En cours : poussée "
                      "d'inflation, crise immobilière et franc plus faible. À venir : perte du job étudiant.", text)
        # Écrit dans l'autre ordre, c'est le même monde. Une crise en cours à la gare est dite en cours.
        self.assertRegex(self.page("?monde=chomage_long@25+krach@24")[0], r'<body[^>]*data-world="krach@24\+chomage_long@25"')
        _, text = self.page("?monde=crise_immobiliere@24+chomage_long@27&gare=60")
        self.assertIn("Monde à deux crises, à 25 ans : crise immobilière à 24 ans (en cours) et chômage long à 27 ans (à venir).", text)

    def test_a_combined_world_refused_by_the_engine_leaves_the_page_open_and_says_why(self):
        dom, text = self.page("?monde=krach@24+chomage_long@25+inflation")
        self.assertEqual(len(re.findall(r'<button[^>]*data-world="', dom)), 7)
        self.assertRegex(dom, r'<body[^>]*data-world="reference"')
        self.assertIn("Demande refusée par le moteur. Un monde contient au plus 2 crises : « krach@24+chomage_long@25+inflation » en a 3.", text)

    def test_the_english_page_shows_the_combined_world_without_a_word_of_french(self):
        dom, text = self.page("?monde=krach@24+chomage_long@25&gare=60", lang="en")
        self.assertRegex(dom, r'<html lang="en"')
        for sentence in ("Market crash at 24 + long unemployment at 25", "Two crises in the same world. Investments fall sharply, within one month.",
                         "Return on investments, per month: −30% (+0.2% in the reference world), at age 24.", "Job lost from age 25 to age 26.",
                         "World with two crises, at 25: market crash at 24 (already happened) and long unemployment at 25 (still to come).",
                         "At 25, these tested crises have already happened: market crash and six months of unemployment. In progress: inflation surge, "
                         "housing downturn and weaker franc. Still to come: student job lost."):
            self.assertIn(sentence, text)
        shown = text.replace("Français", "")                      # le lien vers l'autre langue porte son nom
        found = test_english.FRENCH.search(shown)
        self.assertIsNone(found, shown[max(0, (found.start() if found else 0) - 60):(found.end() if found else 0) + 60])
        self.assertIsNone(test_english.BANNED.search(text))
        # Le lien vers l'autre langue garde le monde à deux crises, et son adresse rouvre le même monde.
        link = re.search(r'<a class="language" id="language" href="([^"]*)"', dom).group(1)
        self.assertEqual(html.unescape(link), "/?monde=krach%4024+chomage_long%4025&gare=60&lang=fr")
        self.assertRegex(test_web.dom_of(html.unescape(link)), r'<body[^>]*data-world="krach@24\+chomage_long@25"')


if __name__ == "__main__":
    unittest.main()
