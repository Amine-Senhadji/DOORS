"""Tests de l'exploration : comparaison à une station, portes, carte des frontières."""
from __future__ import annotations

from engine import i18n

i18n.set_default("fr")      # ces tests attendent les phrases du moteur en français ; l'anglais est testé dans tests/test_english.py

import unittest
from pathlib import Path

from engine.assumptions import defaults
from engine.explore import DOORS, compare, frontier
from engine.simulate import load_scenario, run

ALEXIA = load_scenario(Path(__file__).resolve().parents[1] / "engine/scenarios/alexia.json")
X = {"key": "job_net_mensuel", "min": 0, "max": 2800, "steps": 8}
Y = {"key": "salaire_apres_master", "min": 4000, "max": 8500, "steps": 7}


class Compare(unittest.TestCase):
    def test_shared_past_detected_at_month_12_only(self):
        c12 = compare(ALEXIA, "m12_master")
        self.assertIsNotNone(c12["shared_past"])
        self.assertEqual(c12["shared_past"]["until_month"], 12)
        a, b = run(ALEXIA, "master"), run(ALEXIA, "master_arret_m12")
        for ma, mb in zip(a.months[:12], b.months[:12]):
            self.assertAlmostEqual(ma.net_worth_chf, mb.net_worth_chf, places=9)
        self.assertIsNone(compare(ALEXIA, "depart")["shared_past"])

    def test_doors_are_explicit_rules(self):
        c = compare(ALEXIA, "depart")
        self.assertEqual({d["key"] for d in c["doors"]}, {d.key for d in DOORS})
        never_red = next(d for d in c["doors"] if d["key"] == "jamais_rouge")
        self.assertEqual((never_red["a"], never_red["b"]), ("fermee", "ouverte"))
        self.assertNotIn("{", "".join(d["rule"] for d in c["doors"]), "Les règles doivent être formatées")

    def test_unknown_station_is_refused(self):
        with self.assertRaisesRegex(ValueError, "Station inconnue"):
            compare(ALEXIA, "inexistante")


class Frontier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = frontier(ALEXIA, "depart", X, Y)

    def test_grid_shape_and_toi(self):
        self.assertEqual(len(self.f["cells"]), X["steps"])
        self.assertTrue(all(len(col) == Y["steps"] for col in self.f["cells"]))
        self.assertEqual((self.f["toi"]["x"], self.f["toi"]["y"]), (1200.0, defaults()["salaire_apres_master"]))

    def test_cell_matches_a_direct_simulation(self):
        i, j = 3, 5
        values = {X["key"]: self.f["x_values"][i], Y["key"]: self.f["y_values"][j]}
        a, b = run(ALEXIA, "master", values), run(ALEXIA, "travailler", values)
        expected = "a" if a.net_worth_end_chf > b.net_worth_end_chf else "b"
        self.assertEqual(self.f["cells"][i][j]["winner"], expected)

    def test_higher_salary_after_master_never_turns_master_into_loser(self):
        for col in self.f["cells"]:
            seen_a = False
            for cell in col:
                if seen_a:
                    self.assertEqual(cell["winner"], "a")
                seen_a = seen_a or cell["winner"] == "a"

    def test_nearest_tipping_point_really_flips_the_winner(self):
        t = self.f["nearest_tipping"]
        self.assertIsNotNone(t)
        spec = X if t["axis"] == "x" else Y
        step = (spec["max"] - spec["min"]) / 1000
        here = {X["key"]: self.f["toi"]["x"], Y["key"]: self.f["toi"]["y"]}
        on = run(ALEXIA, "master", {**here, t["key"]: t["value"]}).net_worth_end_chf > \
            run(ALEXIA, "travailler", {**here, t["key"]: t["value"]}).net_worth_end_chf
        back = t["value"] - step if t["direction"] == "au-dessus" else t["value"] + step
        before = run(ALEXIA, "master", {**here, t["key"]: back}).net_worth_end_chf > \
            run(ALEXIA, "travailler", {**here, t["key"]: back}).net_worth_end_chf
        self.assertNotEqual(on, before)
        self.assertTrue(self.f["rules"][0].startswith("Si "))

    def test_tipping_rules_never_contradict_toi(self):
        """Régression : une frontière juste à côté de « Toi » était annoncée du mauvais côté."""
        for overrides in ({}, {"salaire_apres_master": 6150}, {"salaire_apres_master": 6250},
                          {"part_epargne_placee": 0.0}):
            f = frontier(ALEXIA, "depart", X, Y, overrides=overrides, scan_steps=20)
            for t in [f["nearest_tipping"]] if f["nearest_tipping"] else []:
                with self.subTest(overrides=overrides):
                    self.assertNotEqual(t["winner_beyond"], f["toi"]["winner"])

    def test_door_criterion_and_unknown_criterion(self):
        f = frontier(ALEXIA, "depart", {**X, "steps": 3}, {**Y, "steps": 3}, criterion="jamais_rouge", scan_steps=5)
        self.assertTrue(all(c["winner"] in ("a", "b", "les_deux", "aucune") for col in f["cells"] for c in col))
        with self.assertRaisesRegex(ValueError, "Critère inconnu"):
            frontier(ALEXIA, "depart", {**X, "steps": 2}, {**Y, "steps": 2}, criterion="bonheur", scan_steps=3)


if __name__ == "__main__":
    unittest.main()
