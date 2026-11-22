"""Tests du moteur : un test par ligne de evaluation/technical-validation.md, plus les règles suisses.

Lancer depuis la racine du repo :
    python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

from engine import i18n

i18n.set_default("fr")      # ces tests attendent les phrases du moteur en français ; l'anglais est testé dans tests/test_english.py

import json
import unittest
from dataclasses import replace
from pathlib import Path

from engine.assumptions import ASSUMPTIONS, brut_depuis_net, defaults
from engine.contract import ASSET_ACCOUNTS, Category, Loan, Operation, Profile, World
from engine.simulate import (initial_state, load_scenario, materialize, reference_world, run, run_ops,
                             world_with_job_loss)
from engine.transition import monthly_rate, transition

ROOT = Path(__file__).resolve().parents[1]
ALEXIA = load_scenario(ROOT / "engine/scenarios/alexia.json")
P20 = Profile("T1", "Test", 20, "Lausanne", "VD", 8000, 0, 900)
P30 = Profile("T2", "Test", 30, "Lausanne", "VD", 20000, 0, 900)
CALM = World(market_return_monthly=0.0, fx_chf_per_eur=0.94)


def th(**kw) -> dict[str, float]:
    t = defaults()
    t.update(kw)
    return t


def work(gross=5000, start=0, end=24, **extra) -> Operation:
    return Operation("travailler", start, end, {"salaire_brut_mensuel": gross, **extra})


def study(job=1200, fee=580, start=0, end=24) -> Operation:
    return Operation("etudier", start, end, {"job_net_mensuel": job, "taxe_semestre": fee})


def flows_of(result, category=None, account=None):
    return [f for mo in result.months for f in mo.flows
            if (category is None or f.category == category) and (account is None or f.account == account)]


class AccountingIdentities(unittest.TestCase):
    """Section 2 et 3 de la checklist : identités de cash et de patrimoine."""

    def assert_identities(self, r):
        prev_nw = None
        for mo in r.months:
            cash = sum(f.amount_chf for f in mo.flows if f.account == "cash")
            self.assertAlmostEqual(mo.opening_cash_chf + cash, mo.closing_cash_chf, places=6,
                                   msg=f"Cash non réconcilié au mois {mo.month}")
            assets = sum(f.amount_chf for f in mo.flows if f.account in ASSET_ACCOUNTS)
            liabilities = sum(f.amount_chf for f in mo.flows if f.account == "dette")
            if prev_nw is not None:
                self.assertAlmostEqual(prev_nw + assets - liabilities, mo.net_worth_chf, places=6,
                                       msg=f"Patrimoine non réconcilié au mois {mo.month}")
            self.assertAlmostEqual(mo.closing_cash_chf + mo.placements_chf + mo.pilier2_chf + mo.logement_chf - mo.debt_chf,
                                   mo.net_worth_chf, places=6)
            self.assertGreaterEqual(mo.closing_cash_chf, -1e-6, "Le cash ne doit jamais être négatif")
            self.assertGreaterEqual(mo.debt_chf, -1e-6, "Une dette ne doit jamais être négative")
            prev_nw = mo.net_worth_chf

    def test_example_from_checklist(self):
        """8 000 + 1 200 de revenu − 1 800 de dépenses = 7 400."""
        t = th(loyer=1800, vie_courante=0, lamal_jeune=0, lamal_adulte=0, avs_min_annuel=0)
        r = run_ops(P20, (study(job=1200, fee=0, end=1),), 1, t)
        self.assertAlmostEqual(r.months[0].closing_cash_chf, 7400.0, places=6)

    def test_identities_hold_on_every_alexia_line(self):
        for line in ALEXIA.lines:
            with self.subTest(line=line.id):
                self.assert_identities(run(ALEXIA, line.id))

    def test_identities_hold_with_loans_fx_and_investments(self):
        ops = (work(5200, 0, 60), Operation("investir", 3, 60, {"montant_mensuel": 400}),
               Operation("emprunter", 2, 3, {"libelle": "Prêt", "montant": 10000, "taux_annuel": 0.04, "mensualite": 300}),
               Operation("demenager", 30, 31, {"lieu": "etranger", "cout_chf": 3000}))
        worlds = [World(market_return_monthly=0.004 * (-1) ** t, fx_chf_per_eur=0.94 + 0.01 * (t % 7))
                  for t in range(60)]
        self.assert_identities(run_ops(P20, ops, 60, th(), worlds))


class TransfersAndDebt(unittest.TestCase):
    """Section 3 : un virement n'appauvrit pas ; capital vs intérêts ; prêt soldé."""

    def test_investment_transfer_does_not_change_net_worth(self):
        t = th(part_epargne_placee=0)
        base = run_ops(P30, (work(6000, 0, 24),), 24, t, [CALM] * 24)
        inv = run_ops(P30, (work(6000, 0, 24), Operation("investir", 0, 24, {"montant_mensuel": 500})),
                      24, t, [CALM] * 24)
        for a, b in zip(base.months, inv.months):
            self.assertAlmostEqual(a.net_worth_chf, b.net_worth_chf, places=6)
        self.assertAlmostEqual(inv.months[-1].placements_chf, 500 * 24, places=6)

    def test_principal_repayment_reduces_cash_and_debt_interest_is_expense(self):
        x = replace(initial_state(P30, th()), loans=(Loan("L", "Prêt", 10000, 0.06, 500),))
        x2, flows = transition(x, (), CALM, th(loyer=0, vie_courante=0, lamal_adulte=0, avs_min_annuel=0))
        interest = 10000 * monthly_rate(0.06)
        self.assertAlmostEqual(x2.loans[0].principal_chf, 10000 - (500 - interest), places=6)
        self.assertTrue(any(f.category == Category.INTERETS and abs(f.amount + interest) < 1e-9 for f in flows))
        self.assertAlmostEqual(x2.cash["CHF"], 20000 - 500, places=6)

    def test_loan_paid_off_never_goes_negative(self):
        x = replace(initial_state(P30, th()), loans=(Loan("L", "Prêt", 900, 0.05, 500),))
        t = th(loyer=0, vie_courante=0, lamal_adulte=0, avs_min_annuel=0)
        for _ in range(5):
            x, _ = transition(x, (), CALM, t)
            self.assertTrue(all(l.principal_chf >= 0 for l in x.loans))
        self.assertEqual(x.loans, (), "Un prêt soldé doit disparaître")

    def test_zero_interest_rate(self):
        x = replace(initial_state(P30, th()), loans=(Loan("L", "Prêt", 1200, 0.0, 100),))
        x2, flows = transition(x, (), CALM, th(taux_decouvert=0.0))
        self.assertAlmostEqual(x2.loans[0].principal_chf, 1100, places=9)
        self.assertFalse(any(f.category == Category.INTERETS for f in flows))


class BoundaryCases(unittest.TestCase):
    """Section 5 de la checklist : cas limites."""

    def test_zero_income_flags_financing(self):
        r = run_ops(P20, (Operation("pause", 0, 24),), 24, th())
        self.assertIsNotNone(r.first_negative_month)
        self.assertGreater(r.peak_financing_chf, 0)
        self.assertIn("financement_necessaire", r.months[-1].flags)

    def test_negative_cash_is_financed_never_clamped(self):
        r = run(ALEXIA, "master")
        self.assertEqual(r.first_negative_month, 3)          # 8'000 CHF de côté, 4'000 CHF de frais d'études dès le premier mois
        lent = sum(f.amount_chf for f in flows_of(r, Category.EMPRUNT, "dette"))
        self.assertGreater(lent, 0, "Le découvert doit apparaître comme un financement explicite")

    def test_negative_investment_return(self):
        worlds = [World(market_return_monthly=-0.02)] * 12
        r = run_ops(P30, (work(6000, 0, 12), Operation("investir", 0, 1, {"montant_mensuel": 10000})), 12,
                    th(part_epargne_placee=0), worlds)
        self.assertAlmostEqual(r.months[-1].placements_chf, 10000 * 0.98 ** 11, places=6)

    def test_higher_tuition_never_increases_wealth(self):
        low = run(ALEXIA, "master", {"taxe_semestre": 580})
        high = run(ALEXIA, "master", {"taxe_semestre": 2000})
        for a, b in zip(low.months, high.months):
            self.assertLessEqual(b.net_worth_chf, a.net_worth_chf + 1e-9)

    def test_missing_input_is_refused_with_clear_message(self):
        with self.assertRaisesRegex(ValueError, "paramètre manquant « salaire_brut_mensuel »"):
            run_ops(P20, (Operation("travailler", 0, 12, {}),), 12, th())
        with self.assertRaisesRegex(ValueError, "Hypothèse manquante"):
            materialize(replace(ALEXIA.lines[0], operations=(Operation("travailler", 0, 12, {"salaire_brut_mensuel": "$inconnue"}),)), th())

    def test_monthly_and_annual_rates_are_consistent(self):
        self.assertAlmostEqual((1 + monthly_rate(0.05)) ** 12, 1.05, places=12)
        r = run_ops(P30, (work(6000, 0, 12), Operation("investir", 0, 1, {"montant_mensuel": 10000})),
                    13, th(rendement_placements_annuel=0.05, part_epargne_placee=0))
        self.assertAlmostEqual(r.months[12].placements_chf, 10000 * 1.05, places=6)


class Currencies(unittest.TestCase):
    """Multi-devises : convention explicite et traçable."""

    def test_salary_in_eur_converted_at_world_rate(self):
        r = run_ops(P20, (Operation("demenager", 0, 1, {"lieu": "etranger", "cout_chf": 0}),
                          work(3000, 0, 2, devise="EUR")), 2, th(), [World(fx_chf_per_eur=0.90)] * 2)
        sal = [f for f in r.months[0].flows if f.label == "Salaire brut"][0]
        self.assertEqual(sal.currency, "EUR")
        self.assertAlmostEqual(sal.amount_chf, 3000 * 0.90, places=9)

    def test_fx_drop_revalues_eur_cash_in_ledger(self):
        ops = (Operation("demenager", 0, 1, {"lieu": "etranger", "cout_chf": 0}), work(4000, 0, 3, devise="EUR"))
        worlds = [World(fx_chf_per_eur=0.94), World(fx_chf_per_eur=0.94), World(fx_chf_per_eur=0.80)]
        r = run_ops(P20, ops, 3, th(), worlds)
        fx_flows = [f for f in r.months[2].flows if f.category == Category.CHANGE]
        self.assertEqual(len(fx_flows), 1)
        self.assertLess(fx_flows[0].amount_chf, 0, "Une baisse de l'euro doit réduire la valeur du cash en EUR")


class ScenarioIsolationAndReproducibility(unittest.TestCase):
    """Section 1 et 4 de la checklist."""

    def test_reproducible(self):
        a, b = run(ALEXIA, "master"), run(ALEXIA, "master")
        self.assertEqual([m.net_worth_chf for m in a.months], [m.net_worth_chf for m in b.months])

    def test_changing_rent_only_changes_housing_and_its_consequences(self):
        a = run(ALEXIA, "travailler", {"loyer": 900})
        b = run(ALEXIA, "travailler", {"loyer": 1000})
        income = lambda r: sum(f.amount_chf for f in flows_of(r, Category.REVENU))
        housing = lambda r: sum(f.amount_chf for f in flows_of(r, Category.LOGEMENT))
        self.assertAlmostEqual(income(a), income(b), places=6)
        self.assertAlmostEqual(housing(b) - housing(a), -100 * 120, places=6)

    def test_transition_does_not_mutate_its_input(self):
        x = initial_state(P20, th())
        snapshot = (dict(x.cash), x.month, x.overdraft_chf)
        transition(x, (study(),), CALM, th())
        self.assertEqual(snapshot, (dict(x.cash), x.month, x.overdraft_chf))


class SwissRules(unittest.TestCase):
    """Section 6 de la checklist : brut/net, impôt, 2e pilier."""

    def test_gross_to_net_contributions(self):
        r = run_ops(P20, (work(5000, 0, 1),), 1, th())
        soc = [f for f in r.months[0].flows if f.label.startswith("AVS/AI/APG")][0]
        self.assertAlmostEqual(soc.amount_chf, -5000 * (0.053 + 0.011), places=9)

    def test_no_lpp_before_25_then_lpp_counts_as_wealth(self):
        young = run_ops(P20, (work(6000, 0, 12),), 12, th())
        self.assertEqual(young.months[-1].pilier2_chf, 0.0)
        older = run_ops(P30, (work(6000, 0, 12),), 12, th())
        self.assertGreater(older.months[-1].pilier2_chf, 0.0)
        employee = -sum(f.amount_chf for f in flows_of(older) if f.label == "2e pilier, part salarié")
        self.assertAlmostEqual(older.months[-1].pilier2_chf, 2 * employee, places=6)

    def test_tax_paid_the_following_year_and_not_double_counted(self):
        r = run_ops(P30, (work(6000, 0, 24),), 24, th())
        first_year = [f for mo in r.months[:12] for f in mo.flows if f.category == Category.IMPOT]
        second_year = [f for mo in r.months[12:] for f in mo.flows if f.category == Category.IMPOT]
        self.assertEqual(first_year, [], "Pas d'impôt payé pendant la première année de travail")
        self.assertEqual(len(second_year), 12)

    def test_unemployment_benefit_requires_enough_contribution_months(self):
        """Une jeune salariée qui perd son emploi après 3 mois n'a pas droit aux indemnités ;
        après 18 mois de cotisation, elle y a droit."""
        t = th()
        early = run_ops(P30, (work(6000, 0, 12),), 12, t, world_with_job_loss(t, 12, 3, 3))
        self.assertFalse(any(f.label == "Indemnité de chômage" for f in flows_of(early)))
        self.assertTrue(any(f.label.startswith("Pas d'indemnité de chômage : 3 mois cotisés") for f in flows_of(early)))
        late = run_ops(P30, (work(6000, 0, 24),), 24, t, world_with_job_loss(t, 24, 18, 3))
        paid = [f for f in flows_of(late) if f.label == "Indemnité de chômage"]
        self.assertEqual(len(paid), 3)
        self.assertAlmostEqual(paid[0].amount_chf, 6000 * 1.02 * 0.70, places=6)

    def test_benefit_months_do_not_count_as_contributions(self):
        t = th()
        r = run_ops(P30, (work(6000, 0, 40),), 40, t, world_with_job_loss(t, 40, 12, 14))
        flows = flows_of(r)
        paid = [f.month for f in flows if f.label == "Indemnité de chômage"]
        refused = [f.month for f in flows if f.label.startswith("Pas d'indemnité")]
        self.assertEqual(paid[0], 12)
        self.assertTrue(refused, "Après des mois au chômage, la fenêtre de cotisation doit se vider")


class AutomaticSaving(unittest.TestCase):
    """Épargne placée automatiquement : un transfert, jamais une dépense."""

    def test_auto_investment_is_a_transfer(self):
        a = run_ops(P30, (work(7000, 0, 36),), 36, th(part_epargne_placee=0.0), [CALM] * 36)
        b = run_ops(P30, (work(7000, 0, 36),), 36, th(part_epargne_placee=0.8), [CALM] * 36)
        self.assertGreater(b.months[-1].placements_chf, 0)
        for x, y in zip(a.months, b.months):
            self.assertAlmostEqual(x.net_worth_chf, y.net_worth_chf, places=6)

    def test_reserve_is_kept_and_nothing_invested_while_in_debt(self):
        t = th(part_epargne_placee=1.0, reserve_cash_mois=3)
        r = run(ALEXIA, "master", {"part_epargne_placee": 1.0, "reserve_cash_mois": 3})
        for mo in r.months:
            invested = sum(f.amount_chf for f in mo.flows if f.rule == "part_epargne_placee" and f.account == "placements")
            if mo.debt_chf > 0:
                self.assertEqual(invested, 0.0, f"Placement pendant un découvert au mois {mo.month}")
            if invested > 0:
                expenses = -sum(f.amount_chf for f in mo.flows if f.category in
                                (Category.LOGEMENT, Category.VIE_COURANTE, Category.SANTE))
                self.assertGreaterEqual(mo.closing_cash_chf + 1e-6, t["reserve_cash_mois"] * expenses)


class Seniority(unittest.TestCase):
    """L'ancienneté : les hausses de salaire acquises survivent à un changement d'opération."""

    def salaries(self, r) -> list[float]:
        return [sum(f.amount_chf for f in mo.flows if f.label == "Salaire brut") for mo in r.months]

    def test_a_job_cut_in_two_with_seniority_pays_exactly_like_one_job(self):
        one = run_ops(P20, (work(5000, 0, 60),), 60, th())
        two = run_ops(P20, (work(5000, 0, 24), work(5000, 24, 60, anciennete_mois=24)), 60, th())
        self.assertEqual(self.salaries(one), self.salaries(two))
        self.assertEqual([m.net_worth_chf for m in one.months], [m.net_worth_chf for m in two.months])

    def test_without_seniority_the_raises_start_again_from_zero(self):
        cut = run_ops(P20, (work(5000, 0, 24), work(5000, 24, 60)), 60, th())
        self.assertAlmostEqual(self.salaries(cut)[24], 5000, places=6)
        self.assertAlmostEqual(self.salaries(cut)[23], 5000 * 1.02, places=6)

    def test_going_part_time_keeps_the_raises_already_earned(self):
        """Passer à 80 % au bout de trois ans : 80 % du salaire avec ses trois hausses, pas 80 % du salaire de départ."""
        r = run_ops(P20, (work(5000, 0, 36), work(5000, 36, 60, taux_activite=0.8, anciennete_mois=36)), 60, th())
        self.assertAlmostEqual(self.salaries(r)[36], 0.8 * 5000 * 1.02 ** 3, places=6)
        self.assertAlmostEqual(self.salaries(r)[48], 0.8 * 5000 * 1.02 ** 4, places=6)

    def test_seniority_survives_a_pause(self):
        """Deux ans d'emploi, un an de pause, puis la reprise : les deux années travaillées comptent, pas l'année de pause."""
        ops = (work(5000, 0, 24), Operation("pause", 24, 36), work(5000, 36, 60, anciennete_mois=24))
        self.assertAlmostEqual(self.salaries(run_ops(P20, ops, 60, th()))[36], 5000 * 1.02 ** 2, places=6)

    def test_seniority_is_optional_and_changes_nothing_by_default(self):
        self.assertEqual(self.salaries(run_ops(P20, (work(5000, 0, 36),), 36, th())),
                         self.salaries(run_ops(P20, (work(5000, 0, 36, anciennete_mois=0),), 36, th())))


class AlexiaFirstThenStarterKit(unittest.TestCase):
    """Les données d'Alexia d'abord, le starter-kit du défi ensuite : salaires et dépenses des lignes d'Alexia."""

    KIT = {s["name"]: s for s in json.loads((ROOT / "starter-kit/scenario_config.json").read_text(encoding="utf-8"))["scenarios"]}

    def expenses(self, mo) -> float:
        return -sum(f.amount_chf for f in mo.flows if f.category in (Category.LOGEMENT, Category.VIE_COURANTE, Category.SANTE))

    def net_of_contributions(self, mo) -> float:
        return sum(f.amount_chf for f in mo.flows if f.label in ("Salaire brut", "AVS/AI/APG + assurance chômage"))

    def test_the_values_of_the_starter_kit_are_the_ones_in_its_file(self):
        work, master = self.KIT["Start working"]["phases"][0], self.KIT["Master's degree"]["phases"][1]
        t = defaults()
        self.assertEqual((t["salaire_net_sans_master"], t["depenses_emploi_sans_master"]),
                         (work["monthly_income_chf"], work["monthly_expenses_chf"]))
        self.assertEqual((t["salaire_net_apres_master"], t["depenses_emploi_apres_master"]),
                         (master["monthly_income_chf"], master["monthly_expenses_chf"]))
        kinds = {a.key: a.kind for a in ASSUMPTIONS}
        for key in ("salaire_net_sans_master", "salaire_net_apres_master", "depenses_emploi_sans_master", "depenses_emploi_apres_master"):
            self.assertEqual(kinds[key], "starter_kit")

    def test_net_salaries_of_the_starter_kit_are_converted_to_gross_by_the_engine_rules(self):
        """Le premier salaire, net d'AVS/AI/APG et d'assurance chômage, est celui du starter-kit, au centime."""
        t = defaults()
        work = run(ALEXIA, "travailler").months[0]
        self.assertAlmostEqual(self.net_of_contributions(work), t["salaire_net_sans_master"], places=2)
        start = int(24 + t["recherche_emploi_mois"])
        self.assertAlmostEqual(self.net_of_contributions(run(ALEXIA, "master").months[start]), t["salaire_net_apres_master"], places=2)
        self.assertAlmostEqual(brut_depuis_net(4200) * (1 - t["taux_avs_ai_apg"] - t["taux_ac"]), 4200, places=9)

    def test_spending_follows_alexia_while_studying_and_the_starter_kit_while_employed(self):
        t = defaults()
        student = t["loyer"] + t["vie_courante"] + t["lamal_jeune"]
        self.assertAlmostEqual(student, 2230, delta=1)                      # l'historique de compte d'Alexia : 2'231 CHF par mois
        master = run(ALEXIA, "master")
        self.assertAlmostEqual(self.expenses(master.months[3]), student, places=6)
        start = int(24 + t["recherche_emploi_mois"])
        self.assertAlmostEqual(self.expenses(master.months[start - 1]), student, places=6)     # recherche d'emploi : pas encore en emploi
        for month in (start, 71, 72, 119):                                  # avant et après le passage à la LAMal adulte, à 26 ans
            self.assertAlmostEqual(self.expenses(master.months[month]), t["depenses_emploi_apres_master"], places=6)
        work = run(ALEXIA, "travailler")
        for month in (0, 71, 72, 119):
            self.assertAlmostEqual(self.expenses(work.months[month]), t["depenses_emploi_sans_master"], places=6)

    def test_an_employment_without_the_parameter_keeps_the_default_living_costs(self):
        t = th()
        r = run_ops(P20, (work(5000, 0, 1),), 1, t)
        self.assertAlmostEqual(self.expenses(r.months[0]), t["loyer"] + t["vie_courante"] + t["lamal_jeune"], places=6)


class SwissRulesEnd(unittest.TestCase):
    def test_every_assumption_is_labelled_with_a_source(self):
        for a in ASSUMPTIONS:
            with self.subTest(key=a.key):
                self.assertIn(a.kind, ("observe", "hypothese", "a_verifier", "regle", "starter_kit"))
                self.assertTrue(a.source)
                if a.kind == "a_verifier":
                    self.assertIn("[à vérifier]", a.source)


if __name__ == "__main__":
    unittest.main()
