"""Des politiques, pas des plans (engine/policy.py) et la route /policies.

Une politique lit l'état présent et décide : a(t) = π(x(t)). Chaque chiffre du tableau de valeur est celui du moteur
appelé directement ; le seuil est recalculé, jamais écrit ; la référence clairvoyante n'est qu'un étalon.
"""
from __future__ import annotations

from engine import i18n

i18n.set_default("fr")      # ces tests attendent les phrases du moteur en français ; l'anglais est testé dans tests/test_english.py

import json
import unittest
from dataclasses import replace
from pathlib import Path

from engine import folk
from engine import policy as P
from engine import worlds as W
from engine.blocks import blocks_to_ops, destinations
from engine.checks import _identities
from engine.explore import _monthly_expenses, doors_of, margins_of
from engine.simulate import load_scenario, run_ops, theta_for, world_with_job_loss
from engine.tree import VARIABLES, Tree

try:
    from fastapi.testclient import TestClient
    from api.main import app
except ImportError:  # pragma: no cover
    TestClient = None

ROOT = Path(__file__).resolve().parents[1]
ALEXIA = load_scenario(ROOT / "engine/scenarios/alexia.json")
TH = theta_for(ALEXIA)
H, AGE0 = ALEXIA.horizon_months, ALEXIA.profile.age
STORY = [{"block": "job", "years": 5}, {"block": "master", "years": 2}, {"block": "job", "years": 3}]
SIDE = VARIABLES["liquidite_chf"][1]
ROWS = ["fige", "securite", "equilibre", "ambition"]


def direct(path: list[dict], world_id: str, start_cash: float | None = None):
    """Le moteur, sans passer par l'arbre : le trajet simulé depuis le départ. `start_cash` : une autre épargne de départ."""
    profile = ALEXIA.profile if start_cash is None else replace(ALEXIA.profile, cash_chf=start_cash)
    return run_ops(profile, blocks_to_ops(path, TH, H), H, TH, W.build(TH, world_id, H, AGE0))


class ValueTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = Tree(ALEXIA)
        cls.view = P.view(cls.tree, STORY)
        cls.worlds = [w["id"] for w in cls.view["worlds"]]
        cls.rules = {row["id"]: row["rule"] for row in cls.view["policies"]}
        cls.a = P.Analysis(cls.tree, STORY)

    def test_the_table_has_the_fixed_plan_and_three_policies_in_four_worlds_with_the_long_shock_put_forward(self):
        self.assertEqual([row["id"] for row in self.view["policies"]], ROWS)
        self.assertEqual(self.worlds, ["reference", "krach@24", "chomage_6_mois@24", "chomage_long"])
        self.assertEqual([w["highlight"] for w in self.view["worlds"]], [False, False, False, True])
        self.assertEqual((self.view["target"]["key"], self.view["target"]["age"], self.view["target"]["required_chf"]),
                         ("reconversion", 28, 39365.95))
        # Le choc long : une seule crise, douze mois de perte d'emploi à 24 ans, dont la durée est une hypothèse modifiable.
        self.assertEqual(TH["chomage_long_mois"], 12)
        self.assertEqual(W.build(TH, "chomage_long", H, AGE0), world_with_job_loss(TH, H, 48, 12))
        shorter = theta_for(ALEXIA, {"chomage_long_mois": 9})
        self.assertEqual(W.build(shorter, "chomage_long", H, AGE0), world_with_job_loss(shorter, H, 48, 9))
        self.assertNotIn("chomage_long", W.WORLD_IDS, "Le choc long ne s'ajoute pas aux mondes testés par défaut")

    def test_a_policy_is_a_date_a_quantity_a_threshold_and_a_branch(self):
        self.assertIsNone(self.rules["fige"])
        self.assertEqual({k: (r["age"], r["variable"], r["threshold_chf"], r["branch_id"]) for k, r in self.rules.items() if r},
                         {"securite": (25, "liquidite_chf", 74600.0, "emploi"), "equilibre": (26, "liquidite_chf", 50100.0, "emploi"),
                          "ambition": (26, "liquidite_chf", 50100.0, "master_en_travaillant")})
        self.assertEqual(self.rules["equilibre"]["text"],
                         "À 26 ans, si tu as moins de 50'100 CHF de côté (cash + placements − dettes) : arrêter pour un emploi à Lausanne.")

    def test_every_cell_is_the_engine_called_directly(self):
        for row in ROWS:
            rule = self.rules[row]
            for w in self.worlds:
                with self.subTest(row=row, world=w):
                    cell, plan = self.view["cells"][row][w], direct(STORY, w)
                    applies, taken = False, STORY
                    if rule:
                        m = plan.months[rule["gare_month"] - 1]              # l'état à la gare : la fin du mois d'avant
                        level = m.closing_cash_chf + m.placements_chf - m.debt_chf
                        applies = level < rule["threshold_chf"]
                        self.assertEqual(cell["observed_chf"], round(level, 2))
                        if applies:
                            taken = next(b["path"] for b in destinations(STORY, rule["gare_month"], H, AGE0) if b["id"] == rule["branch_id"])
                    run = direct(taken, w)
                    kept = doors_of(run, TH, AGE0)
                    value, required = margins_of(run, TH, AGE0)["reconversion"]
                    self.assertEqual((cell["applies"], cell["path"]), (applies, taken))
                    self.assertEqual((cell["doors_open"], cell["doors_total"]), (sum(kept.values()), 6))
                    self.assertEqual(cell["peak_financing_chf"], round(run.peak_financing_chf, 2))
                    self.assertEqual(cell["net_worth_end_chf"], round(run.net_worth_end_chf, 2))
                    self.assertEqual((cell["target_holds"], cell["target_value_chf"]), (kept["reconversion"], round(value, 2)))

    def test_the_table_of_the_demo_story(self):
        """Les objectifs gardés et le sort du master, case par case : ce que chaque choix achète, et ce qu'il coûte."""
        shown = {row: [(c["doors_open"], c["master"]["state"], c["master"]["age"]) for c in self.view["cells"][row].values()] for row in ROWS}
        self.assertEqual(shown["fige"], [(3, "termine", 27), (2, "termine", 27), (2, "termine", 27), (2, "termine", 27)])
        self.assertEqual(shown["securite"], [(3, "termine", 27)] + [(5, "pas_commence", None)] * 3)
        self.assertEqual(shown["equilibre"], [(3, "termine", 27)] + [(4, "arrete", 26)] * 3)
        self.assertEqual(shown["ambition"], [(3, "termine", 27), (3, "termine_en_travaillant", 28), (3, "termine_en_travaillant", 28),
                                              (2, "termine_en_travaillant", 28)])
        # Sans choc, les trois politiques suivent le plan ; dans le choc long, elles le quittent toutes.
        for row in ROWS[1:]:
            self.assertEqual([c["applies"] for c in self.view["cells"][row].values()], [False, True, True, True])
        long = {row: self.view["cells"][row]["chomage_long"] for row in ROWS}
        self.assertEqual([long[row]["peak_financing_chf"] > 0 for row in ROWS], [True, False, False, True])
        self.assertLess(long["ambition"]["peak_financing_chf"], 1000)
        self.assertGreater(long["fige"]["peak_financing_chf"], 20000)

    def test_the_fate_of_the_master_is_read_in_the_blocks_of_the_trip(self):
        fate = lambda path: tuple(P.master_fate(path, AGE0).values())
        self.assertEqual(fate(STORY), ("termine", 27))
        self.assertEqual(fate([{"block": "job", "years": 10}]), ("pas_commence", None))
        self.assertEqual(fate([{"block": "job", "years": 5}, {"block": "master", "years": 1}, {"block": "job", "years": 4}]), ("arrete", 26))
        self.assertEqual(fate([{"block": "job", "years": 5}, {"block": "master", "years": 1}, {"block": "master_part_time", "years": 2},
                               {"block": "job", "years": 2}]), ("termine_en_travaillant", 28))

    def test_each_row_has_three_bands_the_worst_of_the_four_columns_the_reference_world_and_the_cautious_world(self):
        for row in ROWS:
            band, cells = self.view["bands"][row], self.view["cells"][row]
            with self.subTest(row=row):
                self.assertEqual(band["pire"]["doors_open"]["value"], min(c["doors_open"] for c in cells.values()))
                self.assertEqual(band["pire"]["peak_financing_chf"]["value"], max(c["peak_financing_chf"] for c in cells.values()))
                self.assertEqual(band["pire"]["net_worth_end_chf"]["value"], min(c["net_worth_end_chf"] for c in cells.values()))
                self.assertEqual({k: band["central"][k]["value"] for k in ("doors_open", "peak_financing_chf", "net_worth_end_chf")},
                                 {k: cells["reference"][k] for k in ("doors_open", "peak_financing_chf", "net_worth_end_chf")})
                # Dans le monde prudent, la politique lit l'épargne de ce monde et décide ; puis le moteur donne son trajet.
                rule, taken = self.rules[row], STORY
                if rule:
                    m = direct(STORY, "prudent").months[rule["gare_month"] - 1]
                    if m.closing_cash_chf + m.placements_chf - m.debt_chf < rule["threshold_chf"]:
                        taken = next(b["path"] for b in destinations(STORY, rule["gare_month"], H, AGE0) if b["id"] == rule["branch_id"])
                run = direct(taken, "prudent")
                self.assertEqual(band["prudent"]["doors_open"]["value"], sum(doors_of(run, TH, AGE0).values()))
                self.assertEqual(band["prudent"]["net_worth_end_chf"]["value"], round(run.net_worth_end_chf, 2))
        self.assertEqual({k: c["world_id"] for k, c in self.view["bands"]["fige"]["pire"].items()},
                         {"doors_open": "krach@24", "peak_financing_chf": "chomage_long", "net_worth_end_chf": "chomage_long"})
        # Pour Sécurité et Équilibre, le pire monde testé est le monde sans choc : elles y suivent le plan, master compris.
        for row in ("securite", "equilibre"):
            self.assertEqual({c["world_id"] for c in self.view["bands"][row]["pire"].values()}, {"reference"})

    # ------------------------------------------------------------------ Alexia fragile : la même politique, un autre état
    def test_fragile_alexia_is_the_same_alexia_with_less_savings_at_the_start_and_the_same_policies(self):
        fragile = self.view["fragile"]
        self.assertEqual((self.view["start_cash_chf"], fragile["start_cash_chf"], TH["epargne_depart_fragile"]), (8000.0, 2000.0, 2000))
        for row in ROWS:
            rule = self.rules[row]                                   # les règles et les seuils d'Alexia : rien n'est recalibré
            for w in self.worlds:
                with self.subTest(row=row, world=w):
                    cell, plan, taken = fragile["cells"][row][w], direct(STORY, w, 2000.0), STORY
                    applies = False
                    if rule:
                        m = plan.months[rule["gare_month"] - 1]
                        level = m.closing_cash_chf + m.placements_chf - m.debt_chf
                        applies = level < rule["threshold_chf"]
                        self.assertEqual(cell["observed_chf"], round(level, 2))
                        if applies:
                            taken = next(b["path"] for b in destinations(STORY, rule["gare_month"], H, AGE0) if b["id"] == rule["branch_id"])
                    run = direct(taken, w, 2000.0)
                    self.assertEqual((cell["applies"], cell["doors_open"], cell["peak_financing_chf"]),
                                     (applies, sum(doors_of(run, TH, AGE0).values()), round(run.peak_financing_chf, 2)))
                    self.assertGreaterEqual(cell["regret_chf"], 0)
        # Avec 2'000 CHF au départ, le plan figé perd « Reconversion » même sans choc, et les trois politiques quittent
        # le plan dans les quatre mondes : elles lisent un autre état.
        self.assertFalse(fragile["cells"]["fige"]["reference"]["target_holds"])
        self.assertTrue(self.view["cells"]["fige"]["reference"]["target_holds"])
        for row in ROWS[1:]:
            self.assertEqual([c["applies"] for c in fragile["cells"][row].values()], [True] * 4)
        self.assertEqual([c["doors_open"] for c in fragile["cells"]["fige"].values()], [2, 2, 2, 2])
        self.assertEqual([fragile["cells"][row]["reference"]["doors_open"] for row in ROWS], [2, 5, 4, 3])

    def test_the_gap_between_each_policy_and_the_fixed_plan_is_given_for_both(self):
        for case in (self.view, self.view["fragile"]):
            for row in ROWS[1:]:
                for w in self.worlds:
                    ours, plan, gap = case["cells"][row][w], case["cells"]["fige"][w], case["gap"][row][w]
                    self.assertEqual(gap["doors_more"], ours["doors_open"] - plan["doors_open"])
                    self.assertAlmostEqual(gap["financing_difference_chf"], ours["peak_financing_chf"] - plan["peak_financing_chf"], places=2)
                    self.assertAlmostEqual(gap["regret_difference_chf"], ours["regret_chf"] - plan["regret_chf"], places=2)
                    self.assertEqual(gap["target_saved"], ours["target_holds"] and not plan["target_holds"])
        # Sans choc : aucun écart pour Alexia, qui suit son plan ; un écart pour Alexia fragile, dès le monde sans choc.
        calm = lambda case: [case["gap"][row]["reference"]["doors_more"] for row in ROWS[1:]]
        self.assertEqual((calm(self.view), calm(self.view["fragile"])), ([0, 0, 0], [3, 2, 1]))
        self.assertEqual([self.view["fragile"]["gap"][row]["reference"]["target_saved"] for row in ROWS[1:]], [True, True, False])

    # ------------------------------------------------------------------ non-anticipativité, référence clairvoyante, regret
    def test_a_policy_only_reads_the_present_state_two_worlds_alike_until_its_date_get_the_same_decision(self):
        """Non-anticipativité : a(t) = π(x(t)). Un choc qui arrive après la date de la règle ne peut pas changer sa décision."""
        for policy in P.POLICIES:
            threshold = self.rules[policy.id]["threshold_chf"]
            age = AGE0 + policy.gare_month // 12
            for later in (f"chomage_long@{age}", "chomage_long@27", f"krach@{age}", "krach@29", "perte_job_etudiant@26", "perte_job_etudiant@27"):
                if W.shock_start(TH, later, H, AGE0) < policy.gare_month:
                    continue
                with self.subTest(policy=policy.id, world=later):
                    self.assertEqual(direct(STORY, later).months[:policy.gare_month], direct(STORY, "reference").months[:policy.gare_month])
                    self.assertEqual(self.a.level(policy, later), self.a.level(policy, "reference"))
                    self.assertEqual(self.a.decide(policy, threshold, later), self.a.decide(policy, threshold, "reference"))
        # La décision ne dépend que de l'épargne lue : sous le seuil la branche, sinon le plan.
        for policy in P.POLICIES:
            for w in self.worlds:
                applies, option = self.a.decide(policy, self.rules[policy.id]["threshold_chf"], w)
                self.assertEqual(applies, self.a.level(policy, w) < self.rules[policy.id]["threshold_chf"])
                self.assertEqual(option, policy.id if applies else "fige")

    def test_the_clairvoyant_reference_is_one_of_the_four_options_and_no_row_does_better_on_the_target(self):
        for w in self.worlds:
            seer = self.view["clairvoyant"][w]
            self.assertIn(seer["option"], ROWS)
            reached = min(seer["target_value_chf"], seer["target_required_chf"])
            for row in ROWS:
                cell = self.view["cells"][row][w]
                self.assertLessEqual(min(cell["target_value_chf"], cell["target_required_chf"]), reached + 0.01)
        # Sans choc le plan tient l'objectif : la référence clairvoyante reste sur le plan. Sous un choc, elle le quitte.
        self.assertEqual([self.view["clairvoyant"][w]["option"] for w in self.worlds], ["fige", "equilibre", "equilibre", "equilibre"])

    def test_the_regret_is_what_is_missing_for_the_target_never_negative_and_zero_when_the_target_holds(self):
        for row in ROWS:
            for w in self.worlds:
                cell, seer = self.view["cells"][row][w], self.view["clairvoyant"][w]
                cap = lambda c: min(c["target_value_chf"], c["target_required_chf"])
                self.assertGreaterEqual(cell["regret_chf"], 0)
                self.assertAlmostEqual(cell["regret_chf"], cap(seer) - cap(cell), places=1)
                if cell["target_holds"]:
                    self.assertEqual(cell["regret_chf"], 0)
        regret = {row: [round(c["regret_chf"]) for c in self.view["cells"][row].values()] for row in ROWS}
        self.assertEqual(regret, {"fige": [0, 6268, 4728, 12474], "securite": [0, 0, 0, 0], "equilibre": [0, 0, 0, 0],
                                  "ambition": [0, 2535, 789, 8329]})

    # ------------------------------------------------------------------ le choix du seuil
    def test_the_threshold_is_in_the_middle_of_the_zone_whose_lower_edge_is_the_tipping_point_found_by_the_engine(self):
        for policy in P.POLICIES:
            found = next(row for row in self.view["policies"] if row["id"] == policy.id)["calibration"]
            zone, threshold = found["zone"], found["threshold_chf"]
            with self.subTest(policy=policy.id):
                self.assertLessEqual(zone["low_chf"], threshold)
                self.assertLessEqual(threshold, zone["high_chf"])
                self.assertLessEqual(abs(threshold - (zone["low_chf"] + zone["high_chf"]) / 2), 50)
                self.assertEqual(zone["low_chf"], zone["tipping_chf"])
                # Le point de bascule, vérifié de part et d'autre : avec cette épargne à la gare le plan tient l'objectif
                # dans le monde sans choc ; avec 100 CHF de moins, il le perd.
                keeps = lambda x: doors_of(self.tree.observed(STORY, policy.gare_month, x, STORY, "reference", None, keep=False)[0],
                                           TH, AGE0)["reconversion"]
                self.assertTrue(keeps(zone["tipping_chf"]))
                self.assertFalse(keeps(zone["tipping_chf"] - 100))
                # Le bord haut : la plus basse épargne d'un monde où rester sur le plan tient l'objectif.
                self.assertEqual(zone["high_chf"], round(self.a.level(policy, "reference"), 2))
        self.assertEqual({p.id: self.rules[p.id]["threshold_chf"] for p in P.POLICIES}, {"securite": 74600.0, "equilibre": 50100.0, "ambition": 50100.0})

    def test_the_old_threshold_between_two_worlds_was_on_the_wrong_side_of_the_tipping_point(self):
        """Le surapprentissage, sur un cas : 48'200 CHF était le milieu entre deux mondes testés ; avec 48'500 CHF à 26 ans
        cette règle disait « continue », et l'objectif était perdu. Le point de bascule calculé est 48'800 CHF."""
        run = self.tree.observed(STORY, 72, 48500.0, STORY, "reference", None, keep=False)[0]
        self.assertFalse(doors_of(run, TH, AGE0)["reconversion"])
        self.assertEqual(self.tree.tipping_level(STORY, 72, STORY, "reference", "reconversion", None), 48800.0)
        sign = next(r for r in self.tree.pathways_view(STORY)["by_world"]["krach"]["doors"] if r["key"] == "reconversion")["signpost"]
        self.assertEqual(sign["threshold_chf"], self.rules["equilibre"]["threshold_chf"])     # le signal et la politique disent le même seuil

    def test_the_choice_is_lexicographic_worlds_kept_then_regret_then_the_fewest_departures_from_the_plan(self):
        equilibre, ambition = P.POLICIES[1], P.POLICIES[2]
        worlds = tuple(self.worlds)
        found = self.a.calibrate(equilibre, worlds)
        self.assertEqual((found["kept"], found["worst_regret_chf"], found["applies_in"]), (4, 0, self.worlds[1:]))
        # « Toujours quitter le plan » tiendrait aussi l'objectif dans les quatre mondes, sans regret : c'est le troisième
        # critère qui l'écarte.
        always = [self.a.run("equilibre", w) for w in worlds]
        self.assertTrue(all(self.a.holds(run) for run in always))
        # Ambition ne sauve pas l'objectif sous un choc, mais réduit ce qui manque : le deuxième critère la fait s'appliquer.
        found = self.a.calibrate(ambition, worlds)
        self.assertEqual((found["kept"], found["applies_in"]), (1, self.worlds[1:]))
        for w in self.worlds[1:]:
            self.assertLess(self.a.regret(self.a.run("ambition", w), w), self.a.regret(self.a.run("fige", w), w))

    # ------------------------------------------------------------------ contre le surapprentissage
    def test_leaving_one_world_out_gives_a_threshold_that_still_decides_right_in_that_world(self):
        for row in self.view["policies"][1:]:
            policy = next(p for p in P.POLICIES if p.id == row["id"])
            for test in row["leave_one_out"]:
                with self.subTest(policy=row["id"], left_out=test["world_id"]):
                    others = tuple(w for w in self.worlds if w != test["world_id"])
                    self.assertEqual(test["threshold_chf"], self.a.calibrate(policy, others)["threshold_chf"])
                    # Le seuil trouvé sans ce monde y prend la même décision que le seuil retenu.
                    self.assertEqual(test["applies"], self.view["cells"][row["id"]][test["world_id"]]["applies"])
                    self.assertEqual(test["target_holds"], self.view["cells"][row["id"]][test["world_id"]]["target_holds"])

    def test_the_variants_are_the_test_set_and_a_shock_after_the_last_date_is_seen_by_no_policy(self):
        variants = {v["world"]["id"]: v for v in self.view["validation"]["variants"]}
        self.assertEqual(set(variants), {"krach", "krach@25", "krach@24~67", "krach@24~133", "chomage_6_mois@23", "chomage_6_mois@25",
                                         "chomage_6_mois@24~67", "chomage_6_mois@24~133", "chomage_long@23", "chomage_long@25",
                                         "chomage_long~67", "chomage_long~133", "chomage_long@27"})
        self.assertFalse(set(variants) & set(self.worlds), "Une variante de test n'est pas un monde du tableau")
        for world_id, variant in variants.items():
            for row in ROWS:
                rule, cell = self.rules[row], variant["cells"][row]
                run = direct(STORY, world_id)
                if rule and cell["applies"]:
                    run = direct(next(b["path"] for b in destinations(STORY, rule["gare_month"], H, AGE0) if b["id"] == rule["branch_id"]), world_id)
                self.assertEqual((cell["doors_open"], cell["target_holds"]),
                                 (sum(doors_of(run, TH, AGE0).values()), doors_of(run, TH, AGE0)["reconversion"]), (world_id, row))
        # Douze mois de chômage à 27 ans, après les deux dates de décision : les trois politiques suivent le plan.
        late = variants["chomage_long@27"]["cells"]
        self.assertEqual([(late[row]["applies"], late[row]["doors_open"], late[row]["target_holds"]) for row in ROWS], [(False, 1, False)] * 4)
        self.assertGreater(late["equilibre"]["regret_chf"], 39365)
        # Un krach à 25 ans arrive après la date de Sécurité, pas après celle d'Équilibre.
        self.assertEqual((variants["krach@25"]["cells"]["securite"]["applies"], variants["krach@25"]["cells"]["equilibre"]["applies"]), (False, True))
        # La gravité met l'écart au monde de référence à l'échelle, sans recopier de paramètre.
        strong, usual = W.build(TH, "krach@24~133", H, AGE0)[48], W.build(TH, "krach@24", H, AGE0)[48]
        normal = W.build(TH, "reference", H, AGE0)[48].market_return_monthly
        self.assertAlmostEqual(strong.market_return_monthly - normal, 1.33 * (usual.market_return_monthly - normal), places=12)
        self.assertEqual(sum(w.job_lost for w in W.build(TH, "chomage_6_mois@24~133", H, AGE0)), 8)
        for refused in ("krach@24~10", "krach@24~beaucoup", "reference~120"):
            with self.assertRaises(ValueError):
                W.canonical(refused, TH, H, AGE0)

    def test_the_random_variants_are_reproducible_and_only_score_the_policies(self):
        drawn = self.view["validation"]["random"]
        self.assertEqual((drawn["seed"], drawn["draws"], drawn["ages"], drawn["gravity"]), (2026, 200, [21, 29], [50, 150]))
        self.assertEqual(set(drawn["kept"]), {"securite", "equilibre", "ambition"}, "Le plan figé n'est jamais évalué sur un tirage")
        self.assertNotIn("fige", json.dumps(drawn))
        again = P.validate(Tree(ALEXIA), STORY, None, tuple(self.worlds), {k: r["threshold_chf"] for k, r in self.rules.items() if r})["random"]
        self.assertEqual(again, drawn)
        for row in ROWS[1:]:
            self.assertLessEqual(drawn["kept"][row], drawn["clairvoyant_kept"])
            self.assertLessEqual(drawn["applied"][row], drawn["draws"])
        self.assertGreater(drawn["kept"]["equilibre"], drawn["kept"]["ambition"])


class FolkRule(unittest.TestCase):
    """Une règle répandue, mise à l'épreuve : « trois mois d'épargne de précaution suffisent ». La réponse dépend de l'état."""

    @classmethod
    def setUpClass(cls):
        cls.tree = Tree(ALEXIA)
        cls.view = folk.view(cls.tree, STORY)
        cls.states = {s["id"]: s for s in cls.view["states"]}
        cls.worlds = [w["id"] for w in cls.view["worlds"]]

    def test_the_test_is_three_months_of_expenses_at_25_in_two_states_and_the_same_eight_worlds(self):
        self.assertEqual(self.view["rule"], {"months": 3, "window_months": 24, "age": 25, "gare_month": 60,
                                             "text": "3 mois d'épargne de précaution suffisent"})
        self.assertEqual(self.worlds, ["reference", "krach@25", "chomage_6_mois@25", "chomage_long@25", "perte_job_etudiant",
                                       "inflation@25", "crise_immobiliere@25", "franc_faible@25"])
        for state, path in (("salariee", [{"block": "job", "years": 10}]), ("etudiante", STORY)):
            s = self.states[state]
            expenses = _monthly_expenses(direct(path, "reference"), 60)        # ses dépenses courantes à 25 ans, comptées par le moteur
            self.assertEqual((s["path"], s["expenses_chf"], s["cushion_chf"]), (path, round(expenses, 2), round(3 * expenses, 2)))
        self.assertEqual((self.states["salariee"]["cushion_chf"], self.states["etudiante"]["cushion_chf"]), (9000.0, 6690.0))

    def test_the_cushion_replaces_the_simulated_savings_and_every_franc_stays_accounted_for(self):
        for state in self.states.values():
            for w in self.worlds:
                run = self.tree.with_cushion(state["path"], 60, state["cushion_chf"], w, None)
                self.assertEqual(_identities(run), (True, True, H), (state["id"], w))
                self.assertEqual(run.months[:60], self.tree.trip(state["path"], w, None)[0].months[:60])
                put = [f for f in run.months[60].flows if f.rule == "regle_coussin_mois"]
                simulated = self.tree.trip(state["path"], w, None)[1][60]
                self.assertAlmostEqual(sum(f.amount_chf for f in put if f.account == "cash"), state["cushion_chf"] - sum(simulated.cash.values()), places=6)
                self.assertAlmostEqual(sum(f.amount_chf for f in put if f.account == "placements"), -simulated.placements_chf, places=6)
                # La règle tient si aucun financement n'est nécessaire pendant les 24 mois qui suivent.
                red = [m.month for m in run.months[60:84] if "financement_necessaire" in m.flags]
                row = state["by_world"][w]
                self.assertEqual((row["holds"], row["first_red_month"]), (not red, red[0] if red else None))

    def test_the_rule_holds_for_alexia_employed_and_in_no_tested_world_for_alexia_starting_her_master(self):
        employed, student = self.states["salariee"], self.states["etudiante"]
        self.assertEqual((employed["kept"], employed["total"], student["kept"], student["total"]), (8, 8, 0, 8))
        # Le coussin qui suffirait : il tient dans tous les mondes testés, et 100 CHF de moins ne suffisent plus.
        for state in (employed, student):
            enough = lambda cash: all("financement_necessaire" not in m.flags for w in self.worlds
                                      for m in self.tree.with_cushion(state["path"], 60, cash, w, None).months[60:84])
            self.assertTrue(enough(state["needed_chf"]))
            self.assertFalse(enough(state["needed_chf"] - 100))
            self.assertEqual(state["needed_months"], round(state["needed_chf"] / state["expenses_chf"], 1))
        self.assertLess(employed["needed_chf"], employed["cushion_chf"])
        self.assertGreater(student["needed_months"], 20)
        self.assertEqual(self.view["sentence"],
                         "« 3 mois d'épargne de précaution suffisent » : vrai dans 8 des 8 mondes testés pour Alexia salariée à 25 ans, "
                         "dans 0 des 8 pour Alexia qui commence son master au même âge. Il lui faudrait 24,8 mois de dépenses de côté "
                         "(55'200 CHF), pas 3.")

    def test_the_rule_and_its_window_are_assumptions_that_go_through_to_the_engine(self):
        longer = folk.view(Tree(ALEXIA), STORY, {"regle_coussin_mois": 30})
        self.assertEqual({s["id"]: s["kept"] for s in longer["states"]}, {"salariee": 8, "etudiante": 8})
        self.assertIn("« 30 mois d'épargne de précaution suffisent »", longer["sentence"])
        shorter = folk.view(Tree(ALEXIA), STORY, {"regle_coussin_fenetre_mois": 1})
        self.assertEqual(next(s for s in shorter["states"] if s["id"] == "etudiante")["kept"], 8)


@unittest.skipIf(TestClient is None, "FastAPI non installé")
class Route(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(app)

    def test_the_route_returns_the_table_of_the_engine_for_the_demo_trip_by_default(self):
        answer = self.c.post("/policies", json={})
        self.assertEqual(answer.status_code, 200, answer.text)
        self.assertEqual(answer.json(), json.loads(json.dumps(P.view(Tree(ALEXIA), STORY))))
        self.assertEqual(self.c.post("/policies", json={"path": STORY}).json(), answer.json())

    def test_a_changed_assumption_and_other_worlds_go_through_to_the_engine(self):
        usual = self.c.post("/policies", json={}).json()
        shorter = self.c.post("/policies", json={"assumptions": {"chomage_long_mois": 9}}).json()
        self.assertLess(shorter["cells"]["fige"]["chomage_long"]["regret_chf"], usual["cells"]["fige"]["chomage_long"]["regret_chf"])
        richer = self.c.post("/policies", json={"assumptions": {"epargne_depart_fragile": 5000}}).json()
        self.assertEqual((richer["fragile"]["start_cash_chf"], richer["start_cash_chf"]), (5000.0, 8000.0))
        self.assertGreater(richer["fragile"]["cells"]["fige"]["reference"]["target_value_chf"],
                           usual["fragile"]["cells"]["fige"]["reference"]["target_value_chf"])
        other = self.c.post("/policies", json={"mondes": ["reference", {"type": "krach", "age": 24}, "chomage_long@23"]}).json()
        self.assertEqual([w["id"] for w in other["worlds"]], ["reference", "krach@24", "chomage_long@23"])

    def test_the_folk_rule_route_returns_the_test_of_the_engine(self):
        answer = self.c.post("/folk-rule", json={})
        self.assertEqual(answer.status_code, 200, answer.text)
        self.assertEqual(answer.json(), json.loads(json.dumps(folk.view(Tree(ALEXIA), STORY))))
        longer = self.c.post("/folk-rule", json={"assumptions": {"regle_coussin_mois": 30}}).json()
        self.assertEqual([s["kept"] for s in longer["states"]], [8, 8])

    def test_a_trip_without_the_branches_of_the_policies_is_refused_clearly(self):
        answer = self.c.post("/policies", json={"path": [{"block": "job", "years": 10}]})
        self.assertEqual(answer.status_code, 422)
        self.assertIn("ce trajet ne la propose pas", answer.json()["detail"])
        self.assertEqual(self.c.post("/policies", json={"mondes": ["covid_2020"]}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
