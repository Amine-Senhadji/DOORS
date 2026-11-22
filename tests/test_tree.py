"""L'arbre des trajets (engine/tree.py) et ses routes : /worlds, /path, /node, /pathways.

Chaque chiffre rendu par une route est celui du moteur appelé directement. Une branche, calculée en repartant
de l'état de la gare, est exactement le même trajet simulé depuis le départ.
"""
from __future__ import annotations

import json
import unittest
from dataclasses import asdict, replace
from pathlib import Path

from engine import worlds as W
from engine.blocks import blocks_to_ops, destinations
from engine.explore import DOORS, door_age, doors_of, margins_of, rule_text
from engine.simulate import load_scenario, reference_world, run, run_ops, theta_for
from engine.checks import _identities
from engine.tree import VARIABLES, Tree, observe

try:
    from fastapi.testclient import TestClient
    from api.main import app
except ImportError:  # pragma: no cover
    TestClient = None

ROOT = Path(__file__).resolve().parents[1]
ALEXIA = load_scenario(ROOT / "engine/scenarios/alexia.json")
TH = theta_for(ALEXIA)
H, AGE0 = ALEXIA.horizon_months, ALEXIA.profile.age
MASTER = [{"block": "master", "years": 2}, {"block": "job", "years": 8}]
WORK = [{"block": "job", "years": 10}]
BERLIN = [{"block": "job_abroad", "years": 10}]
STOPPED = [{"block": "master", "years": 1}, {"block": "job", "years": 9}]
RETURN_TO_STUDY = [{"block": "job", "years": 5}, {"block": "master", "years": 2}, {"block": "job", "years": 3}]     # reprise d'études à 25 ans
SIDE = VARIABLES["liquidite_chf"][1]       # ce qu'Alexia a de côté : cash + placements − dettes
LINES = {"master": MASTER, "travailler": WORK, "etranger": BERLIN, "master_arret_m12": STOPPED}


def direct(path: list[dict], world_id: str, overrides: dict | None = None):
    """Le moteur, sans passer par l'arbre : le trajet simulé depuis le départ."""
    th = theta_for(ALEXIA, overrides)
    return run_ops(ALEXIA.profile, blocks_to_ops(path, th, H), H, th, W.build(th, world_id, H)), th


def expected(path: list[dict], world_id: str, overrides: dict | None = None, detailed: bool = False) -> dict:
    r, th = direct(path, world_id, overrides)
    states, margins = doors_of(r, th, AGE0), margins_of(r, th, AGE0)
    word = lambda ok: "ouverte" if ok else "fermee"
    doors = ({k: {"state": word(ok), "value_chf": None if margins[k] is None else round(margins[k][0], 2),
                  "required_chf": None if margins[k] is None else round(margins[k][1], 2)} for k, ok in states.items()}
             if detailed else {k: word(ok) for k, ok in states.items()})
    return {"doors": doors, "doors_open": sum(states.values()), "doors_total": len(DOORS),
            "first_negative_month": r.first_negative_month,
            "financing_months": [m.month for m in r.months if "financement_necessaire" in m.flags],
            "peak_financing_chf": round(r.peak_financing_chf, 2), "net_worth_end_chf": round(r.net_worth_end_chf, 2)}


class NamedWorlds(unittest.TestCase):
    def test_worlds_are_the_ones_of_the_catalogue_and_their_names_stay_true(self):
        worlds = {w["id"]: w for w in W.describe(TH, H, AGE0)}
        self.assertEqual(list(worlds), list(W.WORLD_IDS))
        self.assertEqual(worlds["reference"]["parameters"], [])
        reference = reference_world(TH, H)
        for world_id, world in worlds.items():
            if world_id == "reference":
                continue
            with self.subTest(world=world_id):
                built = W.build(TH, world_id, H)
                self.assertEqual(len(built), H)
                self.assertNotEqual(built, reference, "Un monde identique au monde de référence ne teste rien")
                for p in world["parameters"]:
                    differs = [t for t in range(H) if getattr(built[t], p["field"]) != getattr(reference[t], p["field"])]
                    self.assertEqual((p["from_month"], p["to_month"], p["months"]), (differs[0], differs[-1] + 1, len(differs)))
                    self.assertEqual(p["value"], getattr(built[differs[-1]], p["field"]))
        # Les noms et les phrases des mondes restent vrais tant que le catalogue ne change pas.
        duration = lambda world_id: worlds[world_id]["parameters"][0]["months"]
        self.assertEqual((duration("chomage_6_mois"), duration("krach"), duration("crise_immobiliere")), (6, 1, 24))
        self.assertLess(worlds["krach"]["parameters"][0]["value"], 0)
        self.assertGreater(worlds["inflation"]["parameters"][0]["value"], 1)
        self.assertGreater(worlds["franc_faible"]["parameters"][0]["value"], worlds["franc_faible"]["parameters"][0]["reference"])

    def test_an_unknown_world_and_a_random_draw_are_refused_for_now(self):
        with self.assertRaisesRegex(KeyError, "pas encore disponible"):
            W.build(TH, "covid_2020", H)
        with self.assertRaisesRegex(KeyError, "mondes nommés seulement"):
            W.asked({"tirage": 100, "graine": 2026})
        self.assertEqual(W.asked(None), W.WORLD_IDS)

    def test_stations_change_colour_from_one_world_to_another(self):
        """Ce pour quoi les mondes existent : au moins une porte change d'état selon le monde, sur au moins une ligne."""
        changes = [(name, w, k) for name, path in LINES.items() for w in W.WORLD_IDS for k in (d.key for d in DOORS)
                   if expected(path, w)["doors"][k] != expected(path, "reference")["doors"][k]]
        self.assertIn(("master_arret_m12", "chomage_6_mois", "coussin"), changes)
        self.assertIn(("travailler", "krach", "logement"), changes)
        self.assertIn(("etranger", "franc_faible", "logement"), changes)
        self.assertGreaterEqual(len(changes), 5)


@unittest.skipIf(TestClient is None, "FastAPI non installé : .venv/bin/pip install -r requirements.txt")
class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(app)
        cls.worlds = list(W.WORLD_IDS)

    def post(self, route: str, **body):
        response = self.c.post(f"/{route}", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    # ------------------------------------------------------------------------- /worlds et /path
    def test_worlds_route_equals_the_engine(self):
        self.assertEqual(self.c.get("/worlds").json(), json.loads(json.dumps(W.describe(TH, H, AGE0))))

    def test_the_four_lines_written_as_blocks_equal_the_lines_of_the_scenario(self):
        for line in ALEXIA.lines:
            answer = self.post("path", path=LINES[line.id])
            self.assertEqual(answer["path"], LINES[line.id])
            self.assertEqual([m["net_worth_chf"] for m in answer["months"]], [m.net_worth_chf for m in run(ALEXIA, line.id).months])

    def test_every_number_of_a_path_is_the_one_of_the_engine_in_every_world(self):
        for name, path in LINES.items():
            answer = self.post("path", path=path)
            self.assertEqual(list(answer["by_world"]), self.worlds)
            for world_id in self.worlds:
                with self.subTest(line=name, world=world_id):
                    self.assertEqual(answer["by_world"][world_id], expected(path, world_id, detailed=True))

    def test_the_ledger_of_a_path_is_the_one_of_the_engine_for_the_world_shown(self):
        answer = self.post("path", path=MASTER, world_id="chomage_6_mois")
        r, _ = direct(MASTER, "chomage_6_mois")
        as_json = lambda value: json.loads(json.dumps(value, default=lambda enum: enum.value))
        self.assertEqual(answer["months"], as_json(asdict(r)["months"]))
        self.assertTrue(any(f["label"].startswith("Pas d'indemnité de chômage") for f in answer["months"][27]["flows"]),
                        "Dans ce monde, la jeune diplômée perd son emploi sans avoir assez cotisé : le registre le dit")

    def test_a_changed_assumption_goes_through_to_the_engine(self):
        overrides = {"job_net_mensuel": 2000, "recherche_emploi_mois": 6}
        answer = self.post("path", path=MASTER, assumptions=overrides)
        self.assertEqual(answer["by_world"]["krach"], expected(MASTER, "krach", overrides, detailed=True))
        self.assertNotEqual(answer["by_world"]["krach"], expected(MASTER, "krach", detailed=True))
        self.assertEqual([(l["block"], l["from_month"], l["to_month"]) for l in answer["legs"]],
                         [("master", 0, 24), ("recherche", 24, 30), ("job", 30, 120)])

    def test_doors_carry_their_age_their_rule_and_their_origin(self):
        doors = {d["key"]: d for d in self.post("path", path=MASTER)["doors"]}
        self.assertEqual(list(doors), [d.key for d in DOORS])
        for door in DOORS:
            age = door_age(door, TH, AGE0, H)
            self.assertEqual((doors[door.key]["name"], doors[door.key]["rule"]), (door.name, rule_text(door, TH)))
            self.assertEqual((doors[door.key]["age"], doors[door.key]["whole_trip"]), (age, age is None))
            self.assertTrue(doors[door.key]["source"])
        self.assertEqual([doors[k]["age"] for k in ("coussin", "etudes", "reconversion", "resilience", "logement")], [25, 27, 28, 29, 30])
        self.assertEqual((doors["coussin"]["kind"], doors["reconversion"]["kind"]), ("observe", "observe"))
        self.assertIn("Data/synthetic-goals.csv", doors["coussin"]["source"])

    # ------------------------------------------------------------------------- /node
    def test_at_departure_the_branches_are_the_three_lines_of_the_scenario(self):
        node = self.post("node", path=[], gare_month=0)
        self.assertEqual([b["path"] for b in node["branches"]], [MASTER, WORK, BERLIN])
        self.assertFalse(any(b["on_path"] for b in node["branches"]))
        self.assertEqual(node["state_by_world"]["reference"]["cash_chf"], ALEXIA.profile.cash_chf)
        self.assertEqual((node["gare_month"], node["age"], node["worlds"]), (0, AGE0, self.worlds))

    def test_a_branch_computed_from_the_gare_equals_the_same_trip_simulated_from_the_start(self):
        """Le cœur de l'arbre : chaque branche de chaque gare, dans chaque monde, contre le moteur appelé directement."""
        for name, path in LINES.items():
            for gare in range(0, H, 12):
                node = self.post("node", path=path, gare_month=gare)
                wanted = destinations(path, gare, H, AGE0)
                self.assertEqual([(b["id"], b["label"], b["available"], b["reason"], b["on_path"], b["path"]) for b in node["branches"]],
                                 [(b["id"], b["label"], b["available"], b["reason"], b["on_path"], b["path"]) for b in wanted])
                for branch in node["branches"]:
                    if not branch["available"]:
                        self.assertNotIn("by_world", branch)
                        continue
                    self.assertTrue(all(leg["from_month"] >= gare for leg in branch["legs"]), "Une branche ne redessine pas le passé")
                    for world_id in self.worlds:
                        with self.subTest(line=name, gare=gare, branch=branch["id"], world=world_id):
                            self.assertEqual(branch["by_world"][world_id], expected(branch["path"], world_id))

    def test_the_state_at_a_gare_is_the_state_of_the_engine(self):
        node = self.post("node", path=MASTER, gare_month=12)
        before = direct(MASTER, "krach")[0].months[11]
        got = node["state_by_world"]["krach"]
        self.assertEqual((got["cash_chf"], got["placements_chf"], got["debt_chf"], got["net_worth_chf"]),
                         (round(before.closing_cash_chf, 2), round(before.placements_chf, 2), round(before.debt_chf, 2),
                          round(before.net_worth_chf, 2)))
        self.assertEqual((got["status"], got["location"]), ("etudiant", "CH"))

    def test_flexibility_is_a_count_over_the_trips_reachable_with_one_change(self):
        for path, gare in ((MASTER, 12), (WORK, 60), (BERLIN, 96), (STOPPED, 0)):
            node = self.post("node", path=path, gare_month=gare)
            reachable = [b["path"] for b in destinations(path, gare, H, AGE0) if b["available"]]
            for later in range(gare + 12, H, 12):
                reachable += [b["path"] for b in destinations(path, later, H, AGE0) if b["available"] and not b["on_path"]]
            for door in DOORS:
                with self.subTest(gare=gare, door=door.key):
                    open_in = [w for w in self.worlds if any(expected(trip, w)["doors"][door.key] == "ouverte" for trip in reachable)]
                    got = node["flexibility"]["by_door"][door.key]
                    self.assertEqual((got["worlds_open"], got["possible"], got["robust"]),
                                     (open_in, bool(open_in), len(open_in) == len(self.worlds)))
            flex = node["flexibility"]
            self.assertEqual(sorted(flex["robust"] + flex["possible"]), sorted(k for k, d in flex["by_door"].items() if d["possible"]))
            self.assertEqual((flex["doors_total"], flex["horizon"]), (len(DOORS), "en changeant de route au plus une fois"))

    def test_a_gare_matters_only_if_two_branches_differ_on_a_door(self):
        for path, gare in ((MASTER, 12), (WORK, 96), (BERLIN, 24)):
            node = self.post("node", path=path, gare_month=gare)
            trips = [b["path"] for b in node["branches"] if b["available"]]
            differ = any(expected(t, w)["doors"] != expected(trips[0], w)["doors"] for t in trips for w in self.worlds)
            self.assertEqual(node["matters"], differ)
            staying = next(b for b in node["branches"] if b["on_path"])
            for row in node["best_by_world"]:
                counts = {b["id"]: b["by_world"][row["world_id"]]["doors_open"] for b in node["branches"] if b["available"]}
                self.assertEqual(row["doors_open"], max(counts.values()))
                self.assertEqual(row["doors_more_than_staying"], row["doors_open"] - counts[staying["id"]])

    def test_a_barred_branch_says_why(self):
        late = {b["id"]: b for b in self.post("node", path=WORK, gare_month=108)["branches"]}
        self.assertEqual((late["master"]["available"], late["master"]["reason"]),
                         (False, "Il reste 1 an avant 30 ans : il en faut 2 pour finir le master."))
        done = {b["id"]: b for b in self.post("node", path=MASTER, gare_month=36)["branches"]}
        self.assertEqual(done["master"]["reason"], "Alexia a déjà un master.")

    # ------------------------------------------------------------------------- /pathways
    def test_pathways_follow_the_definitions_of_the_contract(self):
        for name, path in LINES.items():
            answer = self.post("pathways", path=path, gare_month=0)
            for world_id in self.worlds:
                mine = expected(path, world_id)
                for row in answer["by_world"][world_id]["doors"]:
                    with self.subTest(line=name, world=world_id, door=row["key"]):
                        self.assertEqual(row["holds"], mine["doors"][row["key"]] == "ouverte")
                        if row["holds"]:
                            self.assertEqual((row["tipping"], row["no_return"], row["last_transfer"], row["signpost"]), (None,) * 4)
                            continue
                        # Point de bascule : le premier mois de financement, ou l'âge où la porte est testée.
                        age = door_age(next(d for d in DOORS if d.key == row["key"]), TH, AGE0, H)
                        tipping = mine["first_negative_month"] if age is None else (age - AGE0) * 12
                        self.assertEqual(row["tipping"]["month"], tipping)

                        def saving(gare: int) -> list[dict]:
                            return [b for b in destinations(path, gare, H, AGE0) if b["available"] and not b["on_path"]
                                    and expected(b["path"], world_id)["doors"][row["key"]] == "ouverte"]
                        before = [g for g in range(0, H, 12) if g < max(tipping, 1)]
                        useful = [g for g in before if saving(g)]
                        if useful:
                            # Dernière correspondance utile : la plus tardive des gares où une branche ouvre encore la porte.
                            self.assertEqual(row["last_transfer"]["gare_month"], max(useful))
                            self.assertIn(row["last_transfer"]["branch_id"], [b["id"] for b in saving(max(useful))])
                            self.assertEqual(row["no_return"]["gare_month"], max(useful) + 12)
                        else:
                            self.assertIsNone(row["last_transfer"])
                            self.assertEqual(row["no_return"]["gare_month"], 0)

    def test_a_station_can_hold_in_the_reference_world_break_in_a_crisis_and_be_saved_by_a_transfer(self):
        """Travailler, puis reprendre un master à 25 ans. Dans le monde de référence, « Reconversion » tient à 28 ans.
        Sous un krach, six mois de chômage ou une poussée d'inflation, elle casse ; la dernière correspondance utile
        est la gare de 26 ans, où arrêter pour un emploi la garde ouverte. Un signal à surveiller l'annonce."""
        answer = self.post("pathways", path=RETURN_TO_STUDY)
        calm = next(r for r in answer["by_world"]["reference"]["doors"] if r["key"] == "reconversion")
        self.assertTrue(calm["holds"])
        for world_id in ("krach", "chomage_6_mois", "inflation"):
            row = next(r for r in answer["by_world"][world_id]["doors"] if r["key"] == "reconversion")
            with self.subTest(world=world_id):
                self.assertFalse(row["holds"])
                self.assertEqual(row["tipping"], {"month": 96, "age": 28})
                self.assertEqual((row["last_transfer"]["gare_month"], row["last_transfer"]["branch_id"]), (72, "emploi"))
                self.assertEqual(row["no_return"], {"gare_month": 84, "age": 27})
                self.assertEqual(row["signpost"]["gare_month"], 72)
                self.assertIn("à 26 ans, ce trajet ne tient plus « Reconversion »", row["signpost"]["text"])
        saved = next(b for b in self.post("node", path=RETURN_TO_STUDY, gare_month=72)["branches"] if b["id"] == "emploi")
        self.assertEqual(saved["by_world"]["krach"]["doors"]["reconversion"], "ouverte")

    def test_the_gares_of_a_trip_say_which_ones_matter(self):
        gares = self.post("pathways", path=MASTER)["gares"]
        self.assertEqual([g["gare_month"] for g in gares], list(range(0, H, 12)))
        for g in gares:
            node = self.post("node", path=MASTER, gare_month=g["gare_month"])
            self.assertEqual((g["matters"], g["branches"], g["age"]),
                             (node["matters"], sum(b["available"] for b in node["branches"]), node["age"]))
        self.assertTrue(any(g["matters"] for g in gares) and not all(g["matters"] for g in gares))

    def test_a_signpost_is_only_given_when_a_threshold_really_separates_the_worlds(self):
        given = 0
        for name, path in {**LINES, "reprise": RETURN_TO_STUDY}.items():
            for world_id, world in self.post("pathways", path=path)["by_world"].items():
                for row in world["doors"]:
                    sign = row["signpost"]
                    if sign is None:
                        continue
                    with self.subTest(line=name, world=world_id, door=row["key"]):
                        g = sign["gare_month"]
                        self.assertEqual(g, row["last_transfer"]["gare_month"])
                        given += 1
                        for w in self.worlds:
                            m = direct(path, w)[0].months[g - 1]
                            level = m.closing_cash_chf + m.placements_chf - m.debt_chf
                            lost = expected(path, w)["doors"][row["key"]] == "fermee"
                            self.assertEqual(level < sign["threshold_chf"], lost)
        self.assertGreater(given, 0, "Au moins un trajet doit donner un signal à surveiller")

    # ------------------------------------------------------------------------- l'histoire de la démo
    def test_the_default_trip_is_the_demo_story_and_is_computed_at_startup(self):
        """Le trajet par défaut est écrit dans le scénario ; au démarrage du serveur, il est calculé dans tous les mondes et gardé."""
        from api.main import _tree, default_path
        self.assertEqual(default_path(), RETURN_TO_STUDY)
        self.assertEqual(self.c.get("/scenario/alexia").json()["default_path"], RETURN_TO_STUDY)
        _tree.cache_clear()
        with TestClient(app):                       # le démarrage du serveur
            tree = _tree("alexia")
            for world_id in self.worlds:
                self.assertIn(tree._key(RETURN_TO_STUDY, world_id, {}), tree._full)
            before = len(tree._branch)
            self.post("path", path=RETURN_TO_STUDY)
            self.post("pathways", path=RETURN_TO_STUDY)
            self.post("node", path=RETURN_TO_STUDY, gare_month=72)
            self.assertEqual(len(tree._branch), before, "Ouvrir la page par défaut ne déclenche plus aucune simulation")

    def test_a_gare_says_for_each_world_whether_the_crisis_has_already_begun(self):
        early = self.post("node", path=RETURN_TO_STUDY, gare_month=12)["state_by_world"]
        late = self.post("node", path=RETURN_TO_STUDY, gare_month=72)["state_by_world"]
        self.assertIsNone(early["reference"]["avant_le_choc"])
        for world_id in self.worlds[1:]:
            start = W.shock_start(TH, world_id, H)
            with self.subTest(world=world_id):
                self.assertEqual((early[world_id]["choc_month"], early[world_id]["avant_le_choc"]), (start, 12 <= start))
                self.assertEqual(late[world_id]["avant_le_choc"], 72 <= start)
        self.assertTrue(all(early[w]["avant_le_choc"] for w in self.worlds[1:]))
        self.assertFalse(any(late[w]["avant_le_choc"] for w in self.worlds[1:]))

    # ------------------------------------------------------------------------- /adaptive
    def test_adaptive_compares_the_fixed_plan_with_the_plan_that_applies_the_rule(self):
        """Chaque monde, contre le moteur appelé directement : la décision ne lit que l'état à la gare."""
        answer = self.post("adaptive", path=RETURN_TO_STUDY)
        rule = answer["rule"]
        self.assertEqual((rule["gare_month"], rule["age"], rule["variable"], rule["branch_id"]), (72, 26, "liquidite_chf", "emploi"))
        taken = next(b for b in destinations(RETURN_TO_STUDY, 72, H, AGE0) if b["id"] == "emploi")["path"]
        for world_id in self.worlds:
            row = answer["by_world"][world_id]
            with self.subTest(world=world_id):
                m = direct(RETURN_TO_STUDY, world_id)[0].months[71]                 # l'état à la gare de 26 ans : la clôture du mois d'avant
                observed = m.closing_cash_chf + m.placements_chf - m.debt_chf
                applies = observed < rule["threshold_chf"]
                self.assertEqual((row["adaptive"]["applies"], row["adaptive"]["observed_chf"]), (applies, round(observed, 2)))
                self.assertEqual(row["fixed"], expected(RETURN_TO_STUDY, world_id))
                chosen = taken if applies else RETURN_TO_STUDY
                self.assertEqual(row["adaptive"]["path"], chosen)
                self.assertEqual({k: row["adaptive"][k] for k in expected(chosen, world_id)}, expected(chosen, world_id))
                f, a = row["fixed"], expected(chosen, world_id)
                self.assertEqual(row["saved"], {
                    "doors_reopened": [k for k in f["doors"] if f["doors"][k] == "fermee" and a["doors"][k] == "ouverte"],
                    "doors_lost": [k for k in f["doors"] if f["doors"][k] == "ouverte" and a["doors"][k] == "fermee"],
                    "financing_avoided_chf": round(f["peak_financing_chf"] - a["peak_financing_chf"], 2),
                    "net_worth_difference_chf": round(a["net_worth_end_chf"] - f["net_worth_end_chf"], 2)})

    def test_the_default_rule_is_the_signpost_of_the_trip_and_keeps_its_station_in_every_world(self):
        answer = self.post("adaptive", path=RETURN_TO_STUDY)
        sign = next(r for r in self.post("pathways", path=RETURN_TO_STUDY)["by_world"]["krach"]["doors"] if r["key"] == "reconversion")
        self.assertEqual((answer["rule"]["gare_month"], answer["rule"]["threshold_chf"], answer["rule"]["branch_id"]),
                         (sign["signpost"]["gare_month"], sign["signpost"]["threshold_chf"], sign["last_transfer"]["branch_id"]))
        self.assertEqual(answer["target_door"], "reconversion")
        self.assertIn("À 26 ans, si tu as moins de 50'100 CHF de côté", answer["rule"]["text"])
        self.assertIn("arrêter pour un emploi à Lausanne", answer["rule"]["text"])
        # Le résumé sur les sept mondes : la règle garde la reconversion partout, le plan figé dans trois mondes seulement.
        kept = answer["summary"]["doors_kept"]
        self.assertEqual((answer["summary"]["worlds"], kept["reconversion"]), (7, {"fixed": 3, "adaptive": 7}))
        self.assertEqual(answer["summary"]["applies_in"], ["krach", "chomage_6_mois", "perte_job_etudiant", "inflation"])
        for key, counts in kept.items():
            self.assertEqual(counts["fixed"], sum(expected(RETURN_TO_STUDY, w)["doors"][key] == "ouverte" for w in self.worlds))
        # Dans le monde du krach : la règle rouvre la reconversion et évite tout emprunt.
        krach = answer["by_world"]["krach"]
        self.assertIn("reconversion", krach["saved"]["doors_reopened"])
        self.assertEqual(krach["saved"]["financing_avoided_chf"], krach["fixed"]["peak_financing_chf"])
        self.assertEqual(answer["by_world"]["reference"]["saved"]["doors_reopened"], [])

    def test_a_rule_is_data_and_another_threshold_gives_another_plan(self):
        """La règle est une donnée (gare, grandeur, seuil, branche) : un seuil très haut l'applique partout, un seuil nul nulle part."""
        rule = {"gare_month": 72, "variable": "liquidite_chf", "threshold_chf": 1_000_000, "branch_id": "emploi"}
        always = self.post("adaptive", path=RETURN_TO_STUDY, rule=rule, door="reconversion")
        self.assertEqual(always["summary"]["applies_in"], self.worlds)
        never = self.post("adaptive", path=RETURN_TO_STUDY, rule={**rule, "threshold_chf": 0})
        self.assertEqual(never["summary"]["applies_in"], [])
        self.assertTrue(all(never["by_world"][w]["adaptive"]["doors"] == never["by_world"][w]["fixed"]["doors"] for w in self.worlds))
        other = self.post("adaptive", path=RETURN_TO_STUDY, rule={**rule, "branch_id": "master_en_travaillant", "threshold_chf": 48_200})
        self.assertEqual(other["rule"]["branch_label"], "Passer en master en travaillant")

    def test_an_invalid_rule_is_refused_clearly(self):
        base = {"gare_month": 72, "variable": "liquidite_chf", "threshold_chf": 48_200, "branch_id": "emploi"}
        for change, message in (({"variable": "humeur"}, "Grandeur inconnue"), ({"gare_month": 70}, "Pas de gare au mois 70"),
                                ({"branch_id": "doctorat"}, "n'existe pas ou n'est pas ouverte"), ({"threshold_chf": "beaucoup"}, "se décrit par")):
            response = self.c.post("/adaptive", json={"path": RETURN_TO_STUDY, "rule": {**base, **change}})
            self.assertEqual(response.status_code, 422, change)
            self.assertIn(message, response.json()["detail"])
        none = self.c.post("/adaptive", json={"path": WORK})           # un trajet sans signal à surveiller
        self.assertEqual(none.status_code, 422)
        self.assertIn("pas de règle par défaut", none.json()["detail"])

    # ------------------------------------------------------------------------- ce que le tiroir demande
    def test_the_limits_are_read_from_the_project_document(self):
        limits = self.c.get("/limits").json()
        listed = (ROOT / "docs/limits.fr.md").read_text(encoding="utf-8").splitlines()
        self.assertEqual(limits["source"], "docs/limits.fr.md")
        self.assertEqual(limits["limits"], [line[2:].strip() for line in listed if line.startswith("- ")])
        self.assertTrue(any("prélèvement unique de 22 %" in limit for limit in limits["limits"]))

    def test_the_starter_kit_equality_can_be_rerun_live(self):
        result = self.c.post("/checks/starter-kit").json()
        self.assertTrue(result["ok"])
        self.assertEqual((result["total"], result["failed"], result["failures"]), (16, 0, []))
        self.assertEqual(result["source"], "tests/test_vs_starter_kit.py")

    # ------------------------------------------------------------------------- refus
    def test_what_cannot_be_computed_is_refused_with_a_clear_message(self):
        unknown = self.c.post("/path", json={"path": [{"block": "phd", "years": 4}, {"block": "job", "years": 6}]})
        self.assertEqual(unknown.status_code, 422)
        self.assertIn("ne sait pas encore traduire le doctorat", unknown.json()["detail"])
        self.assertEqual(self.c.post("/path", json={"path": MASTER, "world_id": "covid_2020"}).status_code, 400)
        draw = self.c.post("/node", json={"path": [], "mondes": {"tirage": 100, "graine": 2026}})
        self.assertEqual(draw.status_code, 400)
        self.assertIn("mondes nommés seulement", draw.json()["detail"])
        self.assertEqual(self.c.post("/node", json={"path": MASTER, "gare_month": 7}).status_code, 422)
        self.assertEqual(self.c.post("/pathways", json={"path": [{"block": "job", "years": 9}]}).status_code, 422)

    def test_the_tested_worlds_can_be_chosen_by_name(self):
        self.assertEqual(list(self.post("path", path=MASTER, mondes=["reference", "krach"])["by_world"]), ["reference", "krach"])
        node = self.post("node", path=MASTER, gare_month=12, mondes=["chomage_6_mois"])
        self.assertEqual((node["worlds"], list(node["branches"][0]["by_world"])), (["chomage_6_mois"], ["chomage_6_mois"]))

    def test_simulate_and_compare_accept_the_named_worlds(self):
        r = self.c.post("/simulate", json={"line_id": "master", "world_id": "chomage_6_mois"}).json()
        self.assertEqual(round(r["peak_financing_chf"], 2), expected(MASTER, "chomage_6_mois")["peak_financing_chf"])
        self.assertEqual(self.c.post("/compare", json={"station_id": "depart", "world_id": "krach"}).json()["world_id"], "krach")


class CrisisAges(unittest.TestCase):
    """Une crise est un type et un âge : « krach@25 » est le krach du catalogue, déplacé pour commencer à 25 ans."""

    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(app)
        cls.crises = [w for w in W.WORLD_IDS if w != "reference"]

    def post(self, route: str, **body):
        response = self.c.post(f"/{route}", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_a_moved_crisis_is_the_world_of_the_catalogue_shifted_by_whole_years(self):
        reference = reference_world(TH, H)
        self.assertEqual(W.ages(H, AGE0), (21, 29))
        self.assertEqual({w: W.default_age(TH, w, H, AGE0) for w in W.WORLD_IDS},
                         {"reference": None, "krach": 23, "chomage_6_mois": 22, "perte_job_etudiant": 25, "inflation": 21,
                          "crise_immobiliere": 24, "franc_faible": 21})
        for kind in self.crises:
            original, home = W.build(TH, kind, H, AGE0), W.default_age(TH, kind, H, AGE0)
            self.assertEqual(W.build(TH, f"{kind}@{home}", H, AGE0), original)
            self.assertEqual(W.canonical(f"{kind}@{home}", TH, H, AGE0), kind)
            for age in range(21, 30):
                with self.subTest(crise=kind, age=age):
                    moved, shift = W.build(TH, f"{kind}@{age}", H, AGE0), (age - home) * 12
                    self.assertEqual(len(moved), H)
                    for t in range(H):
                        self.assertEqual(moved[t], reference[t] if t < shift else original[min(t - shift, H - 1)])
                    # La crise commence bien dans l'année de vie demandée.
                    self.assertEqual(AGE0 + W.shock_start(TH, f"{kind}@{age}", H, AGE0) // 12, age)

    def test_the_worlds_to_test_are_names_or_a_type_and_an_age(self):
        asked = W.asked(["reference", "krach@25", {"type": "chomage_6_mois", "age": 26}, {"type": "krach", "age": 23}, "krach"], TH, H, AGE0)
        self.assertEqual(asked, ("reference", "krach@25", "chomage_6_mois@26", "krach"))
        for refused, error in (("krach@20", ValueError), ("krach@30", ValueError), ("krach@25.5", ValueError), ("krach@vingt", ValueError),
                               ("reference@25", ValueError), ({"age": 25}, ValueError), ("covid_2020@25", KeyError)):
            with self.assertRaises(error, msg=refused):
                W.asked([refused], TH, H, AGE0)
        with self.assertRaises(ValueError):
            W.asked([], TH, H, AGE0)
        with self.assertRaisesRegex(KeyError, "mondes nommés seulement"):
            W.asked({"tirage": 100, "graine": 2026}, TH, H, AGE0)

    def test_the_routes_accept_a_crisis_with_its_age_and_return_the_numbers_of_the_engine(self):
        mondes = ["reference", "krach@25", {"type": "chomage_6_mois", "age": 26}, "perte_job_etudiant@21"]
        ids = ["reference", "krach@25", "chomage_6_mois@26", "perte_job_etudiant@21"]
        trip = self.post("path", path=RETURN_TO_STUDY, world_id="krach@25", mondes=mondes)
        self.assertEqual((trip["world_id"], list(trip["by_world"])), ("krach@25", ids))
        for w in ids:
            self.assertEqual(trip["by_world"][w], expected(RETURN_TO_STUDY, w, detailed=True), w)
        self.assertEqual(trip["months"], json.loads(json.dumps(asdict(direct(RETURN_TO_STUDY, "krach@25")[0])["months"])))
        node = self.post("node", path=RETURN_TO_STUDY, gare_month=72, mondes=mondes)
        self.assertEqual((node["worlds"], list(node["state_by_world"])), (ids, ids))
        for branch in node["branches"]:
            for w in ids:
                self.assertEqual(branch["by_world"][w], expected(branch["path"], w), (branch["id"], w))
        # Où en est chaque crise à la gare de 26 ans : le krach de 25 ans a eu lieu, le chômage de 26 ans pas encore.
        self.assertEqual({w: node["state_by_world"][w]["avant_le_choc"] for w in ids},
                         {"reference": None, "krach@25": False, "chomage_6_mois@26": True, "perte_job_etudiant@21": False})
        self.assertEqual(node["state_by_world"]["krach@25"]["choc_age"], 25)
        ways = self.post("pathways", path=RETURN_TO_STUDY, mondes=mondes)
        self.assertEqual((ways["worlds"], list(ways["by_world"])), (ids, ids))
        plan = self.post("adaptive", path=RETURN_TO_STUDY, mondes=mondes,
                         rule={"gare_month": 72, "variable": "liquidite_chf", "threshold_chf": 48200, "branch_id": "emploi"})
        self.assertEqual((plan["worlds"], plan["summary"]["worlds"]), (ids, 4))
        for w in ids:
            self.assertEqual(plan["by_world"][w]["fixed"], expected(RETURN_TO_STUDY, w), w)
        for route in ("path", "node", "pathways", "adaptive"):
            self.assertEqual(self.c.post(f"/{route}", json={"path": RETURN_TO_STUDY, "mondes": ["krach@30"]}).status_code, 422)
            self.assertEqual(self.c.post(f"/{route}", json={"path": RETURN_TO_STUDY, "mondes": ["covid_2020@25"]}).status_code, 400)

    def test_the_worlds_route_describes_each_crisis_at_the_age_chosen(self):
        usual = self.c.get("/worlds").json()
        self.assertEqual([(w["id"], w["type"], w["age"], w["default_age"], w["adjustable"]) for w in usual][:3],
                         [("reference", "reference", None, None, False), ("krach", "krach", 23, 23, True),
                          ("chomage_6_mois", "chomage_6_mois", 22, 22, True)])
        self.assertTrue(all((w["min_age"], w["max_age"]) == (21, 29) for w in usual))
        moved = self.c.get("/worlds", params={"mondes": "reference,krach@25,chomage_6_mois,perte_job_etudiant@26"}).json()
        self.assertEqual([(w["id"], w["age"], w["default_age"]) for w in moved],
                         [("reference", None, None), ("krach@25", 25, 23), ("chomage_6_mois", 22, 22), ("perte_job_etudiant@26", 26, 25)])
        krach = moved[1]["parameters"][0]
        self.assertEqual((krach["field"], krach["from_month"], krach["months"], krach["from_age"]), ("market_return_monthly", 60, 1, 25))
        self.assertEqual(self.c.get("/worlds", params={"mondes": "krach@12"}).status_code, 422)

    def test_the_age_of_a_crisis_changes_what_a_trip_keeps(self):
        """Ce pour quoi l'âge se règle : le même krach, à un autre âge, ne ferme pas les mêmes stations."""
        ages = [f"krach@{age}" for age in range(21, 30)]
        trip = self.post("path", path=RETURN_TO_STUDY, mondes=["reference", *ages])
        state = {w: s["doors"]["reconversion"]["state"] for w, s in trip["by_world"].items()}
        self.assertEqual((state["reference"], state["krach@21"], state["krach"], state["krach@25"]), ("ouverte", "ouverte", "fermee", "fermee"))
        self.assertEqual(list(state), ["reference", "krach@21", "krach@22", "krach", *ages[3:]])

    def test_losing_the_student_job_stops_its_income_for_the_months_of_the_assumption_and_only_for_a_student_with_a_job(self):
        self.assertEqual(TH["perte_job_etudiant_mois"], 6)
        lost, _ = direct(MASTER, "perte_job_etudiant@21")
        usual, _ = direct(MASTER, "reference")
        self.assertEqual(_identities(lost), (True, True, H))
        for t in range(H):
            labels = [f.label for f in lost.months[t].flows]
            notes = [f for f in lost.months[t].flows if f.rule == "perte_job_etudiant_mois"]
            if 12 <= t < 18:
                self.assertNotIn("Job étudiant (net)", labels)
                self.assertEqual([(f.amount_chf, f.category.value) for f in notes], [(0.0, "revenu")])
                self.assertIn("Job étudiant perdu", notes[0].label)
            else:
                self.assertEqual(notes, [])
                self.assertEqual("Job étudiant (net)" in labels, "Job étudiant (net)" in [f.label for f in usual.months[t].flows])
        income = lambda r: sum(f.amount_chf for m in r.months[:24] for f in m.flows if f.label == "Job étudiant (net)")
        self.assertAlmostEqual(income(usual) - income(lost), 6 * TH["job_net_mensuel"], places=6)
        # Qui a un emploi, ou étudie sans job, n'est pas concernée ; la durée suit l'hypothèse affichée.
        self.assertEqual(direct(WORK, "perte_job_etudiant@21")[0].months, direct(WORK, "reference")[0].months)
        shorter, _ = direct(MASTER, "perte_job_etudiant@21", {"perte_job_etudiant_mois": 3})
        self.assertEqual([m.month for m in shorter.months if any(f.rule == "perte_job_etudiant_mois" for f in m.flows)], [12, 13, 14])
        # Sur l'histoire de la démo, à son âge d'origine (25 ans, pendant le master), elle ferme « Reconversion ».
        self.assertEqual(expected(RETURN_TO_STUDY, "perte_job_etudiant")["doors"]["reconversion"], "fermee")
        self.assertEqual(expected(RETURN_TO_STUDY, "perte_job_etudiant@21")["doors"]["reconversion"], "ouverte")


class ThreeBands(unittest.TestCase):
    """Trois bandes pour chaque résultat, sans fréquence chiffrée : pire monde testé, central, prudent."""

    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(app)
        cls.trip = cls.c.post("/path", json={"path": RETURN_TO_STUDY}).json()
        cls.bands = cls.trip["bands"]

    def test_the_cautious_world_is_the_reference_world_with_a_lower_return_and_it_is_not_a_crisis(self):
        cautious, reference = W.build(TH, "prudent", H, AGE0), reference_world(TH, H)
        self.assertEqual(TH["prudent_ecart_rendement"], 0.01)
        for t in range(H):
            self.assertEqual(replace(cautious[t], market_return_monthly=reference[t].market_return_monthly), reference[t])
            self.assertAlmostEqual((1 + cautious[t].market_return_monthly) ** 12 - 1, TH["rendement_placements_annuel"] - 0.01, places=12)
        self.assertNotIn("prudent", W.WORLD_IDS)
        self.assertIsNone(W.default_age(TH, "prudent", H, AGE0))
        for refused in ("prudent@25", "prudent~150"):
            with self.assertRaisesRegex(ValueError, "pas une crise"):
                W.canonical(refused, TH, H, AGE0)
        self.assertFalse(W.describe(TH, H, AGE0, ["prudent"])[0]["adjustable"])

    def test_the_worst_tested_world_is_taken_figure_by_figure_and_names_the_world_it_comes_from(self):
        by_world = self.trip["by_world"]
        worst = self.bands["pire"]
        self.assertEqual(worst["doors_open"]["value"], min(s["doors_open"] for s in by_world.values()))
        self.assertEqual(worst["peak_financing_chf"]["value"], max(s["peak_financing_chf"] for s in by_world.values()))
        self.assertEqual(worst["net_worth_end_chf"]["value"], min(s["net_worth_end_chf"] for s in by_world.values()))
        for key, cell in worst.items():
            self.assertEqual(by_world[cell["world_id"]][key], cell["value"])
        # Sur l'histoire de la démo : trois mondes différents pour les trois chiffres.
        self.assertEqual({k: c["world_id"] for k, c in worst.items()},
                         {"doors_open": "krach", "peak_financing_chf": "perte_job_etudiant", "net_worth_end_chf": "inflation"})
        # Quand tous les mondes testés donnent le même chiffre, aucun monde n'est nommé.
        same = self.c.post("/path", json={"path": RETURN_TO_STUDY, "mondes": ["reference", "franc_faible"]}).json()["bands"]["pire"]
        self.assertEqual({c["world_id"] for c in same.values()}, {None})

    def test_central_is_the_reference_world_and_prudent_is_the_cautious_world_computed_by_the_engine(self):
        cautious = expected(RETURN_TO_STUDY, "prudent", detailed=True)
        for key in ("doors_open", "peak_financing_chf", "net_worth_end_chf"):
            self.assertEqual(self.bands["central"][key], {"value": self.trip["by_world"]["reference"][key], "world_id": "reference"})
            self.assertEqual(self.bands["prudent"][key], {"value": cautious[key], "world_id": "prudent"})
        self.assertLess(self.bands["prudent"]["net_worth_end_chf"]["value"], self.bands["central"]["net_worth_end_chf"]["value"])
        self.assertEqual((self.bands["doors_total"], self.bands["prudent_points"]), (6, 1.0))
        # La bande ne dépend pas des mondes demandés : même sans le monde de référence parmi eux.
        other = self.c.post("/path", json={"path": RETURN_TO_STUDY, "mondes": ["krach"]}).json()["bands"]
        self.assertEqual((other["central"], other["prudent"]), (self.bands["central"], self.bands["prudent"]))

    def test_each_station_has_its_three_bands(self):
        doors, by_world = self.bands["doors"], self.trip["by_world"]
        cautious = expected(RETURN_TO_STUDY, "prudent", detailed=True)["doors"]
        for key, band in doors.items():
            self.assertEqual(band["central"], by_world["reference"]["doors"][key])
            self.assertEqual(band["prudent"], cautious[key])
            values = [s["doors"][key]["value_chf"] for s in by_world.values()]
            if None not in values:
                self.assertEqual(band["pire"]["value_chf"], min(values))
            else:                                # une porte sans montant : fermée dans le pire monde testé si un monde la ferme
                closed = any(s["doors"][key]["state"] == "fermee" for s in by_world.values())
                self.assertEqual(band["pire"]["state"], "fermee" if closed else "ouverte")
        low = doors["reconversion"]
        self.assertEqual((low["pire"]["world_id"], low["pire"]["state"], low["central"]["state"], low["prudent"]["state"]),
                         ("inflation", "fermee", "ouverte", "ouverte"))
        # Avec deux points de rendement en moins, le monde prudent perd la reconversion : l'hypothèse passe jusqu'au moteur.
        harder = self.c.post("/path", json={"path": RETURN_TO_STUDY, "assumptions": {"prudent_ecart_rendement": 0.02}}).json()["bands"]
        self.assertEqual((harder["prudent_points"], harder["doors"]["reconversion"]["prudent"]["state"]), (2.0, "fermee"))


class LearningTwin(unittest.TestCase):
    """Le jumeau qui apprend : à une gare, ce qu'Alexia a vraiment de côté remplace l'épargne simulée."""

    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(app)
        cls.tree = Tree(ALEXIA)
        cls.worlds = list(W.WORLD_IDS)

    def post(self, route: str, **body):
        response = self.c.post(f"/{route}", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    @staticmethod
    def seen(value: float, gare: int = 72) -> dict:
        return {"gare_month": gare, "value_chf": value}

    def test_the_observed_state_holds_exactly_the_value_entered_and_every_franc_is_moved_between_accounts(self):
        x = self.tree.trip(RETURN_TO_STUDY, "krach", None)[1][72]
        before = SIDE(x)
        for value in (before + 5000, before - 5000, 0.0, -3000.0):
            after, moves = observe(x, value)
            self.assertAlmostEqual(SIDE(after), value, places=6)
            self.assertAlmostEqual(moves["cash"] + moves["placements"] - moves["dette"], value - before, places=6)
            self.assertGreaterEqual(min(after.cash.values()), -1e-9)
            self.assertGreaterEqual(after.placements_chf, -1e-9)
        # Moins que prévu : le compte d'abord, puis les placements, puis un découvert.
        _, moves = observe(x, -3000.0)
        self.assertAlmostEqual(moves["dette"], 3000.0, places=6)
        self.assertEqual(observe(x, before)[0], x)

    def test_the_lived_trip_keeps_the_past_and_the_accounting_identities(self):
        for w in self.worlds:
            simulated, states = self.tree.trip(RETURN_TO_STUDY, w, None)
            for value in (40_000.0, 60_000.0):
                lived, later = self.tree.lived(RETURN_TO_STUDY, w, None, (72, value))
                self.assertEqual(_identities(lived), (True, True, H), (w, value))
                self.assertEqual(lived.months[:72], simulated.months[:72])
                self.assertAlmostEqual(SIDE(later[72]), value, places=6)
                # L'écart est écrit dans le registre du mois de la gare, sous la règle « observation ».
                gap = [f for f in lived.months[72].flows if f.rule == "observation"]
                self.assertAlmostEqual(sum(f.amount_chf * (-1 if f.account == "dette" else 1) for f in gap), value - SIDE(states[72]), places=6)
                self.assertEqual(lived.months[72].opening_cash_chf, simulated.months[72].opening_cash_chf)
            # Constater exactement ce que le moteur simulait ne change rien.
            same = self.tree.lived(RETURN_TO_STUDY, w, None, (72, SIDE(states[72])))[0]
            self.assertEqual([round(m.net_worth_chf, 6) for m in same.months], [round(m.net_worth_chf, 6) for m in simulated.months])

    def test_at_the_gare_the_branches_leave_from_the_observed_savings_in_every_world(self):
        plain = self.post("node", path=RETURN_TO_STUDY, gare_month=72)
        self.assertIsNone(plain["observation"])
        for value in (40_000.0, 60_000.0):
            node = self.post("node", path=RETURN_TO_STUDY, gare_month=72, observation=self.seen(value))
            self.assertEqual({s["liquidite_chf"] for s in node["state_by_world"].values()}, {value})
            for branch in node["branches"]:
                for w in self.worlds:
                    run = self.tree.fork(RETURN_TO_STUDY, 72, branch["path"], w, None, (72, value))
                    self.assertEqual(branch["by_world"][w], self.tree.summary(run, TH, detailed=False), (branch["id"], w))
            self.assertEqual(node["observation"]["simulated_chf"], {w: plain["state_by_world"][w]["liquidite_chf"] for w in self.worlds})

    def test_the_screen_is_told_on_which_side_of_the_signal_the_observed_savings_stand(self):
        rows = self.post("pathways", path=RETURN_TO_STUDY)["by_world"]["krach"]["doors"]
        sign = next(r["signpost"] for r in rows if r["key"] == "reconversion")
        self.assertEqual((sign["gare_month"], sign["threshold_chf"]), (72, 50100.0))
        for value, side, words in ((40_000, "sous", "sous le seuil de 50'100 CHF"), (50_100, "au_dessus", "au-dessus du seuil"),
                                   (60_000, "au_dessus", "au-dessus du seuil de 50'100 CHF")):
            signal = self.post("node", path=RETURN_TO_STUDY, gare_month=72, observation=self.seen(value))["observation"]["signals"]
            self.assertEqual([(s["door"], s["side"], s["threshold_chf"]) for s in signal], [("reconversion", side, 50100.0)])
            self.assertIn(words, signal[0]["text"])
            self.assertIn("« Reconversion »", signal[0]["text"])

    def test_the_trip_the_later_gares_and_the_pathways_follow_the_observed_savings(self):
        low, high = self.seen(40_000), self.seen(60_000)
        state = lambda o: {w: s["doors"]["reconversion"]["state"] for w, s in self.post("path", path=RETURN_TO_STUDY, observation=o)["by_world"].items()}
        self.assertEqual(set(state(low).values()), {"fermee"})
        self.assertEqual(set(state(high).values()), {"ouverte"})
        trip = self.post("path", path=RETURN_TO_STUDY, world_id="krach", observation=low)
        self.assertEqual(trip["observation"]["age"], 26)
        self.assertEqual([f["rule"] for f in trip["months"][72]["flows"]].count("observation") >= 1, True)
        # Avant la gare, rien ne change ; après, la gare suivante part du trajet vécu.
        self.assertEqual(self.post("node", path=RETURN_TO_STUDY, gare_month=60, observation=low)["state_by_world"],
                         self.post("node", path=RETURN_TO_STUDY, gare_month=60)["state_by_world"])
        later = self.post("node", path=RETURN_TO_STUDY, gare_month=84, observation=low)
        for w in self.worlds:
            self.assertEqual(later["state_by_world"][w]["liquidite_chf"], round(SIDE(self.tree.lived(RETURN_TO_STUDY, w, None, (72, 40_000.0))[1][84]), 2))
        # Les chemins d'adaptation : avec 40'000 CHF, la reconversion se perd partout et la correspondance de 26 ans la sauve.
        ways = self.post("pathways", path=RETURN_TO_STUDY, observation=low)["by_world"]
        for w in self.worlds:
            row = next(r for r in ways[w]["doors"] if r["key"] == "reconversion")
            self.assertEqual((row["holds"], row["last_transfer"]["gare_month"], row["last_transfer"]["branch_id"]), (False, 72, "emploi"), w)
        ways = self.post("pathways", path=RETURN_TO_STUDY, observation=high)["by_world"]
        self.assertTrue(all(next(r for r in ways[w]["doors"] if r["key"] == "reconversion")["holds"] for w in self.worlds))

    def test_the_adaptive_rule_reads_the_observed_savings(self):
        usual = self.post("adaptive", path=RETURN_TO_STUDY)
        self.assertEqual((usual["observation"], usual["summary"]["applies_in"]),
                         (None, ["krach", "chomage_6_mois", "perte_job_etudiant", "inflation"]))
        low = self.post("adaptive", path=RETURN_TO_STUDY, observation=self.seen(40_000))
        self.assertEqual(low["rule"], usual["rule"])                       # la règle reste celle du trajet simulé
        self.assertEqual(low["summary"]["applies_in"], self.worlds)
        self.assertEqual(low["summary"]["doors_kept"]["reconversion"], {"fixed": 0, "adaptive": 7})
        self.assertEqual({row["adaptive"]["observed_chf"] for row in low["by_world"].values()}, {40_000.0})
        for w in self.worlds:
            fixed = self.tree.lived(RETURN_TO_STUDY, w, None, (72, 40_000.0))[0]
            self.assertEqual(low["by_world"][w]["fixed"], self.tree.summary(fixed, TH, detailed=False))
            self.assertEqual(low["by_world"][w]["saved"]["doors_reopened"].count("reconversion"), 1)
        high = self.post("adaptive", path=RETURN_TO_STUDY, observation=self.seen(60_000))
        self.assertEqual((high["summary"]["applies_in"], high["summary"]["doors_kept"]["reconversion"]), ([], {"fixed": 7, "adaptive": 7}))
        # Constatée après la gare de la règle, l'épargne arrive trop tard : la règle lit l'état simulé.
        late = self.post("adaptive", path=RETURN_TO_STUDY, observation=self.seen(1000, 84))
        self.assertEqual((late["observation"], late["by_world"]), (None, usual["by_world"]))

    def test_an_observation_without_a_gare_of_the_trip_is_refused_clearly(self):
        for body in ({"path": RETURN_TO_STUDY, "gare_month": 72, "observation": {"gare_month": 70, "value_chf": 1}},
                     {"path": RETURN_TO_STUDY, "gare_month": 72, "observation": {"gare_month": 0, "value_chf": 1}},
                     {"path": RETURN_TO_STUDY, "gare_month": 72, "observation": {"value_chf": 1}},
                     {"path": [], "gare_month": 0, "observation": {"gare_month": 72, "value_chf": 1}}):
            response = self.c.post("/node", json=body)
            self.assertEqual(response.status_code, 422, body)
            self.assertIn("épargne constatée", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
