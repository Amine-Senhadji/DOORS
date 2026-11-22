"""Continuer depuis un état : reprendre une simulation à une gare donne exactement la simulation complète.

C'est le test qui prouve l'arbre des trajets : comme F est pure et déterministe, on peut calculer chaque
branche à partir de l'état atteint à sa gare, sans refaire le passé, et retrouver les mêmes mois au centime.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from engine.catalog import SPECS, build_world
from engine.contract import Operation
from engine.simulate import (initial_state, load_scenario, materialize, reference_world, resume, run, run_from, run_ops,
                             run_with_states, theta_for, truncate)

ROOT = Path(__file__).resolve().parents[1]
ALEXIA = load_scenario(ROOT / "engine/scenarios/alexia.json")
TH = theta_for(ALEXIA)
H = ALEXIA.horizon_months
GARES = tuple(range(12, H, 12))                      # une gare par an, de 21 à 29 ans
# Le monde de référence et cinq mondes du catalogue : krach, chômage, inflation, crise immobilière, change.
WORLDS = {"reference": reference_world(TH, H),
          **{sid: build_world(TH, next(s for s in SPECS if s.id == sid).world_int) for sid in ("S065", "S014", "S101", "S108", "S028")}}


def ops_of(line_id: str):
    return materialize(next(l for l in ALEXIA.lines if l.id == line_id), TH)


class ContinueFromAState(unittest.TestCase):
    def test_resuming_at_any_gare_gives_exactly_the_full_simulation(self):
        """Chaque ligne, chaque gare, chaque monde : les mois repris sont ceux de la simulation complète, à l'identique."""
        for line in ALEXIA.lines:
            ops = ops_of(line.id)
            for world_id, world in WORLDS.items():
                full, states = run_with_states(ALEXIA.profile, ops, H, TH, world, line.id, world_id, snapshots=GARES)
                self.assertEqual(sorted(states), list(GARES))
                for gare in GARES:
                    with self.subTest(line=line.id, world=world_id, gare=gare):
                        self.assertEqual(states[gare].month, gare)
                        end, months, _ = run_from(ALEXIA.profile, states[gare], ops, H, TH, world)
                        self.assertEqual(months, full.months[gare:])
                        self.assertEqual(end.month, H)
                        again = resume(ALEXIA.profile, full.months[:gare], states[gare], ops, H, TH, world, line.id, world_id)
                        self.assertEqual(again, full)

    def test_a_full_run_is_a_run_from_the_initial_state(self):
        for line in ALEXIA.lines:
            ops = ops_of(line.id)
            _, months, _ = run_from(ALEXIA.profile, initial_state(ALEXIA.profile, TH), ops, H, TH, WORLDS["reference"])
            self.assertEqual(months, run(ALEXIA, line.id).months)

    def test_a_branch_taken_at_a_gare_equals_the_same_trip_simulated_from_the_start(self):
        """Suivre le master jusqu'à 21 ans puis prendre un emploi : l'état du master à la gare suffit, le passé n'est pas refait."""
        master, gare = ops_of("master"), 12
        branch = truncate(master, gare) + (Operation("travailler", gare, H, {"salaire_brut_mensuel": TH["salaire_sans_master"],
                                                                              "depenses_mensuelles": TH["depenses_emploi_sans_master"]}),)
        for world_id, world in WORLDS.items():
            with self.subTest(world=world_id):
                on_master, states = run_with_states(ALEXIA.profile, master, H, TH, world, snapshots=(gare,))
                from_gare = resume(ALEXIA.profile, on_master.months[:gare], states[gare], branch, H, TH, world)
                from_start = run_ops(ALEXIA.profile, branch, H, TH, world)
                self.assertEqual(from_gare.months, from_start.months)
                self.assertEqual((from_gare.min_cash_chf, from_gare.first_negative_month, from_gare.peak_financing_chf,
                                  from_gare.net_worth_end_chf),
                                 (from_start.min_cash_chf, from_start.first_negative_month, from_start.peak_financing_chf,
                                  from_start.net_worth_end_chf))
                self.assertNotEqual(from_gare.net_worth_end_chf, on_master.net_worth_end_chf, "La branche doit changer la suite")

    def test_the_summary_counts_the_past_too(self):
        """Le premier mois de financement du master est avant la gare de 21 ans : le résumé d'une reprise à 22 ans le garde."""
        ops = ops_of("master")
        full, states = run_with_states(ALEXIA.profile, ops, H, TH, snapshots=(24,))
        self.assertLess(full.first_negative_month, 24)
        again = resume(ALEXIA.profile, full.months[:24], states[24], ops, H, TH)
        self.assertEqual((again.first_negative_month, again.min_cash_chf, again.peak_financing_chf),
                         (full.first_negative_month, full.min_cash_chf, full.peak_financing_chf))

    def test_truncating_operations_at_a_gare_does_not_change_the_past(self):
        master = ops_of("master")
        cut = truncate(master, 12)
        self.assertTrue(all(op.end <= 12 for op in cut))
        self.assertEqual([op.kind for op in cut], ["etudier"])
        past = run_ops(ALEXIA.profile, cut + (Operation("pause", 12, H),), H, TH).months[:12]
        self.assertEqual(past, run(ALEXIA, "master").months[:12])

    def test_states_are_snapshots_and_are_never_mutated_by_a_later_run(self):
        ops = ops_of("etranger")
        _, states = run_with_states(ALEXIA.profile, ops, H, TH, snapshots=GARES)
        before = replace(states[36], cash=dict(states[36].cash))
        run_from(ALEXIA.profile, states[36], ops, H, TH, WORLDS["S028"])
        self.assertEqual(states[36], before)

    def test_a_past_that_does_not_match_the_state_is_refused(self):
        ops = ops_of("travailler")
        full, states = run_with_states(ALEXIA.profile, ops, H, TH, snapshots=(24,))
        with self.assertRaisesRegex(ValueError, "Le passé compte 12 mois, l'état reprend au mois 24"):
            resume(ALEXIA.profile, full.months[:12], states[24], ops, H, TH)
        with self.assertRaisesRegex(ValueError, "Le monde couvre 60 mois"):
            run_from(ALEXIA.profile, states[24], ops, H, TH, WORLDS["reference"][:60])


if __name__ == "__main__":
    unittest.main()
