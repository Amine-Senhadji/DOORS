"""Tests de l'achat d'un logement : règles suisses simplifiées et comptabilité."""
from __future__ import annotations

import unittest

from engine.assumptions import defaults
from engine.contract import Category, Operation, Profile, World
from engine.explore import DOOR_KEYS
from engine.simulate import reference_world, run_ops

RICH = Profile("T3", "Test", 35, "Lausanne", "VD", 150000, 0, 1500)
POOR = Profile("T4", "Test", 35, "Lausanne", "VD", 20000, 0, 1500)
BUY_RULES = {"acheter_logement", "fonds_propres_min", "fonds_propres_durs_min", "taux_hypotheque"}


def th(**kw):
    t = defaults()
    t.update({"loyer": 1500, **kw})
    return t


def work(g=9000): return Operation("travailler", 0, 240, {"salaire_brut_mensuel": g})
def buy(prix=500000, s=0, e=1, **kw): return Operation("acheter_logement", s, e, {"prix": prix, **kw})


def purchase_month(r):
    return next((mo.month for mo in r.months if mo.logement_chf > 0), None)


class Purchase(unittest.TestCase):
    def test_purchase_only_costs_the_fees_in_net_worth(self):
        r = run_ops(RICH, (work(), buy()), 12, th())
        m = purchase_month(r)
        self.assertEqual(m, 0)
        mo = r.months[m]
        swap = sum(f.amount_chf * (-1 if f.account == "dette" else 1) for f in mo.flows if f.rule in BUY_RULES)
        self.assertAlmostEqual(swap, 0.0, places=6, msg="Apport + 2e pilier + hypothèque = prix : échange neutre")
        fees = [f for f in mo.flows if f.rule == "frais_achat_logement"]
        self.assertAlmostEqual(fees[0].amount_chf, -500000 * th()["frais_achat_logement"], places=6)

    def test_equity_rules(self):
        r = run_ops(RICH, (work(), buy()), 1, th())
        mo, t = r.months[0], th()
        self.assertAlmostEqual(mo.hypotheque_chf, 500000 * (1 - t["fonds_propres_min"]), places=6)
        from_p2 = -sum(f.amount_chf for f in mo.flows if f.account == "pilier2" and f.amount_chf < 0)
        self.assertLessEqual(from_p2, (t["fonds_propres_min"] - t["fonds_propres_durs_min"]) * 500000 + 1e-6)

    def test_refused_without_enough_equity_and_nothing_moves(self):
        r = run_ops(POOR, (work(), buy()), 1, th())
        self.assertIsNone(purchase_month(r))
        labels = [f.label for f in r.months[0].flows]
        self.assertTrue(any(l.startswith("Achat impossible : fonds propres insuffisants") for l in labels))
        self.assertFalse(any(f.account == "logement" for f in r.months[0].flows))

    def test_refused_by_affordability_test(self):
        """Assez de fonds propres, mais un revenu trop faible : la banque refuse."""
        wealthy = Profile("T5", "Test", 35, "Lausanne", "VD", 400000, 0, 1500)
        r = run_ops(wealthy, (work(4000), buy(800000)), 1, th())
        self.assertIsNone(purchase_month(r))
        self.assertTrue(any(f.label.startswith("Achat refusé par le test de capacité") for f in r.months[0].flows))

    def test_buy_as_soon_as_possible_finds_the_first_feasible_month(self):
        r = run_ops(POOR, (work(9000), buy(400000, 0, 120)), 120, th())
        m = purchase_month(r)
        self.assertIsNotNone(m)
        self.assertGreater(m, 0)
        self.assertTrue(any(f.label.startswith("Achat impossible") for f in r.months[m - 1].flows))
        self.assertEqual(r.peak_financing_chf, 0.0, "L'achat ne doit pas vider le compte au point de s'endetter")


class Ownership(unittest.TestCase):
    def test_rent_replaced_by_interest_upkeep_and_amortization(self):
        r = run_ops(RICH, (work(), buy()), 3, th())
        after = r.months[1].flows
        self.assertFalse(any(f.label == "Loyer" for f in after))
        self.assertTrue(any(f.label == "Entretien du logement" for f in after))
        self.assertTrue(any(f.label == "Intérêts : Hypothèque" and f.category == Category.INTERETS for f in after))
        self.assertTrue(any(f.label == "Remboursement : Hypothèque" and f.account == "dette" for f in after))

    def test_amortization_stops_at_two_thirds_of_price(self):
        r = run_ops(RICH, (work(), buy()), 240, th(hausse_prix_logement_annuelle=0.0))
        self.assertAlmostEqual(r.months[-1].hypotheque_chf, 500000 * 2 / 3, places=4)
        self.assertGreaterEqual(min(mo.hypotheque_chf for mo in r.months), 500000 * 2 / 3 - 1e-6)

    def test_house_price_drop_hits_net_worth_not_cash(self):
        t = th()
        base = run_ops(RICH, (work(), buy()), 12, t)
        worlds = reference_world(t, 12)
        worlds[6] = World(**{**worlds[6].__dict__, "house_return_monthly": -0.20})
        crash = run_ops(RICH, (work(), buy()), 12, t, worlds)
        self.assertAlmostEqual(base.months[-1].closing_cash_chf, crash.months[-1].closing_cash_chf, places=6)
        self.assertLess(crash.months[-1].net_worth_chf, base.months[-1].net_worth_chf - 90000)

    def test_mortgage_does_not_close_the_cushion_door(self):
        t = th(coussin_age=36)
        r = run_ops(RICH, (work(), buy()), 24, t)
        self.assertTrue(DOOR_KEYS["coussin"].test(r, t, RICH.age))
        self.assertTrue(DOOR_KEYS["logement"].test(r, t, RICH.age))


if __name__ == "__main__":
    unittest.main()
