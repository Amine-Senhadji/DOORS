"""Des blocs de vie aux opérations du moteur, et les branches proposées à chaque gare (engine/blocks.py)."""
from __future__ import annotations

from engine import i18n

i18n.set_default("fr")      # ces tests attendent les phrases du moteur en français ; l'anglais est testé dans tests/test_english.py

import unittest
from pathlib import Path

from engine.blocks import BLOCKS, blocks_to_ops, cut, destinations, legs_of, normalize
from engine.simulate import load_scenario, materialize, run, run_ops, theta_for

ROOT = Path(__file__).resolve().parents[1]
ALEXIA = load_scenario(ROOT / "engine/scenarios/alexia.json")
TH = theta_for(ALEXIA)
H, AGE0 = ALEXIA.horizon_months, ALEXIA.profile.age
# Les quatre lignes écrites à la main dans le scénario, dans le vocabulaire des blocs.
LINES = {
    "master": [{"block": "master", "years": 2}, {"block": "job", "years": 8}],
    "travailler": [{"block": "job", "years": 10}],
    "etranger": [{"block": "job_abroad", "years": 10}],
    "master_arret_m12": [{"block": "master", "years": 1}, {"block": "job", "years": 9}],
}


def ops(path):
    return blocks_to_ops(path, TH, H)


def by_id(path, gare):
    return {b["id"]: b for b in destinations(path, gare, H, AGE0)}


class BlocksToOperations(unittest.TestCase):
    def test_the_four_lines_of_the_scenario_come_out_identical(self):
        """Le traducteur retrouve, opération pour opération, les lignes du scénario, écrites à la main."""
        for line in ALEXIA.lines:
            with self.subTest(line=line.id):
                by_hand = [op for op in materialize(line, TH) if op.end > op.start]       # une recherche de 0 mois ne compte pas
                self.assertEqual(sorted(ops(LINES[line.id]), key=lambda o: (o.start, o.kind)),
                                 sorted(by_hand, key=lambda o: (o.start, o.kind)))
                self.assertEqual(run_ops(ALEXIA.profile, ops(LINES[line.id]), H, TH).months, run(ALEXIA, line.id).months)

    def test_a_changed_assumption_moves_the_operations(self):
        th = theta_for(ALEXIA, {"recherche_emploi_mois": 6, "salaire_apres_master": 7000})
        work = [op for op in blocks_to_ops(LINES["master"], th, H) if op.kind == "travailler"][0]
        self.assertEqual((work.start, work.params["salaire_brut_mensuel"]), (30, 7000))

    def test_seniority_follows_the_months_already_worked(self):
        """Deux ans à Lausanne, deux ans à Berlin, puis le retour : chaque emploi connaît les mois travaillés avant lui."""
        path = [{"block": "job", "years": 2}, {"block": "job_abroad", "years": 2}, {"block": "job", "years": 6}]
        jobs = [op for op in ops(path) if op.kind == "travailler"]
        search = int(TH["recherche_emploi_mois"])
        self.assertEqual([(op.start, op.end, op.params.get("anciennete_mois", 0)) for op in jobs],
                         [(0, 24, 0), (24, 48, 24), (48 + search, 120, 48)])
        moves = [(op.start, op.params["lieu"]) for op in ops(path) if op.kind == "demenager"]
        self.assertEqual(moves, [(24, "etranger"), (48, "CH")])

    def test_the_diploma_decides_the_salary_and_the_spending(self):
        with_master = [op for op in ops(LINES["master"]) if op.kind == "travailler"][0].params
        without = [op for op in ops(LINES["master_arret_m12"]) if op.kind == "travailler"][0].params
        self.assertEqual((with_master["salaire_brut_mensuel"], with_master["depenses_mensuelles"]),
                         (TH["salaire_apres_master"], TH["depenses_emploi_apres_master"]))
        self.assertEqual((without["salaire_brut_mensuel"], without["depenses_mensuelles"]),
                         (TH["salaire_sans_master"], TH["depenses_emploi_sans_master"]))
        # Un an à plein temps puis deux ans en travaillant : le master est fini, l'emploi suivant est payé comme tel.
        mixed = [{"block": "master", "years": 1}, {"block": "master_part_time", "years": 2}, {"block": "job", "years": 7}]
        last = [op for op in ops(mixed) if op.kind == "travailler"][-1]
        self.assertEqual((last.start, last.params["salaire_brut_mensuel"], last.params["anciennete_mois"]),
                         (36, TH["salaire_apres_master"], 24))

    def test_two_identical_blocks_in_a_row_are_one(self):
        self.assertEqual(normalize([{"block": "job", "years": 4}, {"block": "job", "years": 6}], H), LINES["travailler"])
        self.assertEqual(ops([{"block": "job", "years": 4}, {"block": "job", "years": 6}]), ops(LINES["travailler"]))

    def test_what_the_engine_cannot_translate_is_refused_clearly(self):
        cases = [([{"block": "phd", "years": 4}, {"block": "job", "years": 6}], "ne sait pas encore traduire le doctorat"),
                 ([{"block": "job", "years": 9}], "Le trajet couvre 9 ans : il en faut 10"),
                 ([{"block": "job_abroad", "years": 10, "options": {"city": "london"}}], "Londres est refusé"),
                 ([{"block": "job", "years": 10, "options": {"city": "zurich"}}], "n'est pas encore traduite"),
                 ([{"block": "licorne", "years": 10}], "type inconnu « licorne »"),
                 ([{"block": "job", "years": 2.5}, {"block": "job", "years": 7.5}], "nombre entier d'années"),
                 ([], "au moins un bloc")]
        for path, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    blocks_to_ops(path, TH, H)

    def test_legs_cover_the_whole_trip_without_gap(self):
        for path in list(LINES.values()) + [[{"block": "job", "years": 2}, {"block": "job_abroad", "years": 2}, {"block": "master", "years": 2},
                                              {"block": "job", "years": 4}]]:
            legs = legs_of(path, TH, H)
            self.assertEqual(legs[0]["from_month"], 0)
            self.assertEqual(legs[-1]["to_month"], H)
            for a, b in zip(legs, legs[1:]):
                self.assertEqual(a["to_month"], b["from_month"])
            self.assertTrue(all(leg["block"] in BLOCKS or leg["block"] == "recherche" for leg in legs))
        from_gare = legs_of(LINES["master"], TH, H, from_month=12)
        self.assertEqual([(l["block"], l["from_month"], l["to_month"]) for l in from_gare],
                         [("master", 12, 24), ("recherche", 24, 27), ("job", 27, 120)])


class Destinations(unittest.TestCase):
    def test_at_departure_three_lines_leave_and_they_are_the_lines_of_the_scenario(self):
        branches = destinations([], 0, H, AGE0)
        self.assertEqual([(b["id"], b["label"]) for b in branches],
                         [("master", "Faire un master"), ("emploi", "Travailler à Lausanne"), ("berlin", "Partir à Berlin")])
        self.assertEqual([b["path"] for b in branches], [LINES["master"], LINES["travailler"], LINES["etranger"]])
        self.assertFalse(any(b["on_path"] for b in branches))

    def test_from_studies(self):
        b = by_id(LINES["master"], 12)
        self.assertEqual(list(b), ["continuer", "emploi", "master_en_travaillant"])
        self.assertEqual((b["continuer"]["on_path"], b["continuer"]["path"]), (True, LINES["master"]))
        self.assertEqual(b["emploi"]["path"], LINES["master_arret_m12"])
        # La moitié du master est faite : l'autre moitié, en travaillant, prend un an et demi, soit deux années entières.
        self.assertEqual(b["master_en_travaillant"]["path"],
                         [{"block": "master", "years": 1}, {"block": "master_part_time", "years": 2}, {"block": "job", "years": 7}])

    def test_from_a_job_in_switzerland(self):
        b = by_id(LINES["travailler"], 36)
        self.assertEqual([(k, v["label"]) for k, v in b.items()],
                         [("emploi", "Rester en emploi à Lausanne"), ("master", "Commencer un master"), ("berlin", "Partir à Berlin")])
        self.assertTrue(b["emploi"]["on_path"])
        self.assertEqual(b["master"]["path"], [{"block": "job", "years": 3}, {"block": "master", "years": 2}, {"block": "job", "years": 5}])
        self.assertEqual(b["berlin"]["path"], [{"block": "job", "years": 3}, {"block": "job_abroad", "years": 7}])

    def test_from_berlin(self):
        b = by_id(LINES["etranger"], 24)
        self.assertEqual([(k, v["label"]) for k, v in b.items()],
                         [("berlin", "Rester à Berlin"), ("emploi", "Rentrer pour un emploi à Lausanne"),
                          ("master", "Commencer un master à Lausanne")])
        self.assertEqual(b["emploi"]["path"], [{"block": "job_abroad", "years": 2}, {"block": "job", "years": 8}])
        back = [(op.kind, op.start) for op in ops(b["master"]["path"]) if op.kind in ("demenager", "etudier")]
        self.assertEqual(back, [("demenager", 0), ("demenager", 24), ("etudier", 24)])

    def test_an_impossible_branch_is_barred_with_its_reason(self):
        graduated = by_id(LINES["master"], 48)["master"]
        self.assertEqual((graduated["available"], graduated["reason"], graduated["path"]), (False, "Alexia a déjà un master.", None))
        late = by_id(LINES["travailler"], 108)["master"]
        self.assertFalse(late["available"])
        self.assertEqual(late["reason"], "Il reste 1 an avant 30 ans : il en faut 2 pour finir le master.")
        with self.assertRaisesRegex(ValueError, "Pas de gare au mois 7"):
            destinations(LINES["master"], 7, H, AGE0)

    def test_the_trip_followed_is_marked_and_kept_as_it_is(self):
        # Au départ du trajet « master arrêté » : la branche du master est celle qu'on suit, avec son arrêt à 21 ans.
        b = by_id(LINES["master_arret_m12"], 0)
        self.assertEqual([k for k, v in b.items() if v["on_path"]], ["master"])
        self.assertEqual(b["master"]["path"], LINES["master_arret_m12"])
        self.assertEqual([k for k, v in by_id(LINES["master_arret_m12"], 12).items() if v["on_path"]], ["emploi"])
        for gare in range(0, H, 12):
            for path in LINES.values():
                self.assertEqual(sum(v["on_path"] for v in by_id(path, gare).values()), 1)

    def test_every_branch_keeps_the_past_and_can_be_simulated(self):
        for name, path in LINES.items():
            for gare in range(0, H, 12):
                branches = destinations(path, gare, H, AGE0)
                self.assertLessEqual(len(branches), 3)
                for branch in branches:
                    if not branch["available"]:
                        self.assertTrue(branch["reason"])
                        continue
                    with self.subTest(line=name, gare=gare, branch=branch["id"]):
                        self.assertEqual(cut(branch["path"], gare), cut(path, gare))
                        r = run_ops(ALEXIA.profile, ops(branch["path"]), H, TH)
                        self.assertEqual(r.months[:gare], run_ops(ALEXIA.profile, ops(path), H, TH).months[:gare])


if __name__ == "__main__":
    unittest.main()
