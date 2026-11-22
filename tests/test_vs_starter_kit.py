"""Le moteur de l'équipe contre le moteur de référence du starter-kit (starter-kit/financial_twin.py).

Le starter-kit est un moteur en cash seul : des revenus nets, des dépenses et des coûts ponctuels.
Il n'a ni cotisations, ni impôt, ni 2e pilier, ni placements, ni intérêts. Quand on neutralise dans
notre moteur tout ce que le starter-kit n'a pas, les deux doivent donner les mêmes 120 soldes
mensuels, au centime, sur les trois scénarios du starter-kit.

Deux précisions de lecture :
- Notre moteur ne montre jamais de cash négatif : il inscrit un « Financement du découvert »
  (le cash négatif n'est jamais effacé). Le solde comparé est donc « cash − dette », avec un découvert à 0 %.
- Aucun fichier de engine/ n'est modifié pour ce test : la neutralisation passe par les hypothèses.

Lancer depuis la racine du dépôt :
    .venv/bin/python -m unittest tests.test_vs_starter_kit -v
"""
from __future__ import annotations

import json
import sys
import types
import unittest
from pathlib import Path

from engine.assumptions import defaults
from engine.checks import _identities
from engine.contract import Category, Operation, Profile
from engine.simulate import load_scenario, materialize, run_ops

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "starter-kit"
PROFILE = json.loads((KIT / "sample_profile.json").read_text(encoding="utf-8"))
SCENARIOS = {s["name"]: s for s in json.loads((KIT / "scenario_config.json").read_text(encoding="utf-8"))["scenarios"]}
ALEXIA = load_scenario(ROOT / "engine/scenarios/alexia.json")
HORIZON = PROFILE["horizon_months"]
PERSON = Profile("starter-kit", PROFILE["name"], PROFILE["age_at_start"], PROFILE["city"], "VD",
                 PROFILE["opening_cash_chf"], 0, 0)

# Soldes finaux que donne le moteur du starter-kit pour ses trois scénarios. Il ne les publie pas : ils sont
# constatés en le lançant, et écrits ici pour qu'un changement de ses fichiers se voie.
CLOSING = {"Start working": 152_000, "Master's degree": 144_600, "Move abroad": 97_500}

# Tout ce que le starter-kit n'a pas, mis à zéro par les hypothèses.
NEUTRAL = {
    # Dépenses que le moteur ajoute de lui-même à une personne qui vit en Suisse
    "loyer": 0, "vie_courante": 0, "lamal_jeune": 0, "lamal_adulte": 0, "avs_min_annuel": 0,
    # Du brut au net : cotisations, 2e pilier, impôt (seuil hors d'atteinte), prélèvements à l'étranger
    "taux_avs_ai_apg": 0, "taux_ac": 0, "lpp_taux_total": 0, "impot_seuil": 1e12, "taux_global_etranger": 0,
    # Ce qui fait bouger un solde sans décision : hausses de salaire, intérêts, épargne placée
    "hausse_salaire_annuelle": 0, "taux_decouvert": 0, "taux_interet_cash": 0, "part_epargne_placee": 0,
    # Un franc pour un euro, pas de coût de la vie à l'étranger ni de taxe d'études par défaut
    "fx_initial": 1.0, "cout_vie_etranger_eur": 0, "taxe_semestre": 0,
}
# Catégories du registre qui n'existent pas dans le starter-kit.
SWISS_ONLY = {Category.COTISATION, Category.IMPOT, Category.SANTE, Category.PREVOYANCE, Category.INTERETS,
              Category.RENDEMENT, Category.CHANGE}


def load_starter_kit() -> types.ModuleType:
    """Le moteur de référence du starter-kit, exécuté tel quel, sans rien écrire dans son dossier."""
    path = KIT / "financial_twin.py"
    module = types.ModuleType("starter_kit_engine")
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), module.__dict__)
    return module


KIT_ENGINE = load_starter_kit()


def theta(**changes) -> dict[str, float]:
    """Les hypothèses par défaut du moteur, neutralisées, puis les valeurs du scénario."""
    th = defaults()
    th.update(NEUTRAL)
    th.update(changes)
    return th


def balances(result) -> list[float]:
    """Le solde du starter-kit, lu dans notre registre : cash moins dette (le découvert financé)."""
    return [round(m.closing_cash_chf - m.debt_chf, 2) for m in result.months]


def generic(scenario: dict):
    """Traduction générique : chaque phase devient un revenu net et une dépense ; chaque coût, une dépense ponctuelle."""
    ops = []
    for phase in scenario["phases"]:
        start, end = phase["start_month"], phase["end_month"]
        ops.append(Operation("revenu_recurrent", start, end, {"libelle": "Revenu net (starter-kit)",
                                                              "montant": phase["monthly_income_chf"], "imposable": False}))
        ops.append(Operation("depense_recurrente", start, end, {"libelle": "Dépenses (starter-kit)",
                                                                "montant": phase["monthly_expenses_chf"]}))
    for cost in scenario.get("one_off_costs", []):
        ops.append(Operation("depense_ponctuelle", cost["month"], cost["month"] + 1,
                             {"libelle": "Coût ponctuel (starter-kit)", "montant": cost["amount_chf"]}))
    return run_ops(PERSON, tuple(ops), HORIZON, theta())


def real_line(name: str, restore: str | None = None):
    """Les vraies lignes d'engine/scenarios/alexia.json, avec les valeurs du starter-kit passées par les hypothèses.

    `restore` remet une hypothèse neutralisée à sa valeur par défaut : c'est ce qui prouve qu'elle comptait.
    """
    scenario = SCENARIOS[name]
    first, extra = scenario["phases"][0], ()
    if name == "Start working":
        line_id = "travailler"
        th = theta(salaire_sans_master=first["monthly_income_chf"], depenses_emploi_sans_master=first["monthly_expenses_chf"])
    elif name == "Master's degree":
        line_id, (study, work) = "master", scenario["phases"]
        # Pendant les études, les dépenses du starter-kit passent par le loyer ; en emploi, par les dépenses totales.
        th = theta(job_net_mensuel=study["monthly_income_chf"], salaire_apres_master=work["monthly_income_chf"],
                   recherche_emploi_mois=0, loyer=study["monthly_expenses_chf"],
                   depenses_emploi_apres_master=work["monthly_expenses_chf"])
        # Un ajustement : les frais d'études du starter-kit sont annuels, ceux du moteur semestriels.
        # Ils sont repris comme dépenses ponctuelles.
        extra = tuple(Operation("depense_ponctuelle", c["month"], c["month"] + 1,
                                {"libelle": "Frais d'études (starter-kit)", "montant": c["amount_chf"]})
                      for c in scenario["one_off_costs"])
    elif name == "Move abroad":
        line_id = "etranger"
        th = theta(salaire_etranger_eur=first["monthly_income_chf"], cout_vie_etranger_eur=first["monthly_expenses_chf"],
                   cout_demenagement=scenario["one_off_costs"][0]["amount_chf"])
    else:
        raise ValueError(f"Scénario du starter-kit inconnu : « {name} »")
    if restore is not None:
        th[restore] = defaults()[restore]
    line = next(l for l in ALEXIA.lines if l.id == line_id)
    return run_ops(PERSON, materialize(line, th) + extra, HORIZON, th)


class Comparison(unittest.TestCase):
    """Les vérifications communes aux deux traductions."""

    def run_ours(self, name: str):
        raise unittest.SkipTest("classe de base")

    def test_same_120_balances_to_the_cent(self):
        for name, scenario in SCENARIOS.items():
            with self.subTest(scenario=name):
                theirs, ours = KIT_ENGINE.simulate(PROFILE, scenario), balances(self.run_ours(name))
                self.assertEqual(len(ours), HORIZON)
                self.assertEqual(len(theirs.cash_by_month_chf), HORIZON)
                for month, (a, b) in enumerate(zip(ours, theirs.cash_by_month_chf)):
                    self.assertAlmostEqual(a, b, places=2, msg=f"« {name} », mois {month}")

    def test_closing_balances_of_the_starter_kit_engine(self):
        self.assertEqual(set(CLOSING), set(SCENARIOS))
        for name, closing in CLOSING.items():
            with self.subTest(scenario=name):
                self.assertEqual(KIT_ENGINE.simulate(PROFILE, SCENARIOS[name]).closing_cash_chf, closing)
                self.assertAlmostEqual(balances(self.run_ours(name))[-1], closing, places=2)

    def test_same_first_negative_month_and_same_lowest_balance(self):
        for name, scenario in SCENARIOS.items():
            with self.subTest(scenario=name):
                theirs, ours = KIT_ENGINE.simulate(PROFILE, scenario), self.run_ours(name)
                self.assertEqual(ours.first_negative_month, theirs.first_negative_month)
                self.assertAlmostEqual(ours.min_cash_chf, theirs.minimum_cash_chf, places=2)

    def test_the_master_goes_negative_in_month_7_and_the_shortfall_is_financed(self):
        """Le « Month 7 » du starter-kit : le mois d'indice 6. Chez nous, chaque mois négatif porte un financement explicite."""
        theirs, ours = KIT_ENGINE.simulate(PROFILE, SCENARIOS["Master's degree"]), self.run_ours("Master's degree")
        self.assertEqual(theirs.first_negative_month, 6)
        self.assertEqual(ours.first_negative_month, 6)
        negative = [month for month, cash in enumerate(theirs.cash_by_month_chf) if cash < 0]
        financed = [m.month for m in ours.months if "financement_necessaire" in m.flags]
        self.assertEqual(financed, negative)
        self.assertAlmostEqual(ours.peak_financing_chf, -theirs.minimum_cash_chf, places=2)
        self.assertTrue(all(m.closing_cash_chf >= 0 for m in ours.months), "Le cash affiché ne passe jamais sous zéro")

    def test_accounting_identities_hold_on_these_runs(self):
        for name in SCENARIOS:
            with self.subTest(scenario=name):
                cash_ok, net_worth_ok, months = _identities(self.run_ours(name))
                self.assertTrue(cash_ok and net_worth_ok)
                self.assertEqual(months, HORIZON)

    def test_nothing_swiss_is_left_in_the_ledger(self):
        """Garde-fou : si une future règle du moteur ajoute une ligne obligatoire, ce test la nomme."""
        for name in SCENARIOS:
            with self.subTest(scenario=name):
                left = sorted({f.label for m in self.run_ours(name).months for f in m.flows if f.category in SWISS_ONLY})
                self.assertEqual(left, [])


class GenericTranslation(Comparison):
    """Chaque phase du starter-kit devient un revenu net et une dépense ; chaque coût, une dépense ponctuelle."""

    def run_ours(self, name: str):
        return generic(SCENARIOS[name])


class RealLines(Comparison):
    """Les lignes « travailler », « master » et « etranger » du moteur, règles suisses neutralisées."""

    def run_ours(self, name: str):
        return real_line(name)

    def test_the_ledger_only_holds_the_lines_of_the_starter_kit(self):
        expected = {
            "Start working": {"Salaire brut", "Vie courante"},
            "Master's degree": {"Job étudiant (net)", "Salaire brut", "Loyer", "Vie courante", "Frais d'études (starter-kit)",
                                "Financement du découvert", "Remboursement du découvert"},
            "Move abroad": {"Déménagement (etranger)", "Salaire brut", "Coût de la vie à l'étranger"},
        }
        for name in SCENARIOS:
            with self.subTest(scenario=name):
                self.assertEqual({f.label for m in real_line(name).months for f in m.flows}, expected[name])

    def test_every_neutralised_assumption_matters(self):
        """Remettre une seule hypothèse neutralisée à sa valeur par défaut change les soldes d'au moins un
        scénario : la liste NEUTRAL ne contient rien d'inutile, et chaque règle du moteur est bien active."""
        base = {name: balances(real_line(name)) for name in SCENARIOS}
        # La LAMal adulte ne commence qu'à 26 ans, quand Alexia est en emploi sur ces lignes : elle est alors
        # comprise dans les dépenses totales de l'emploi, et la changer ne déplace aucun solde.
        absorbed = {"lamal_adulte"}
        for key, neutral in NEUTRAL.items():
            if defaults()[key] == neutral:
                continue                      # déjà neutre par défaut : rien à prouver
            with self.subTest(assumption=key):
                moved = any(balances(real_line(name, restore=key)) != base[name] for name in SCENARIOS)
                self.assertEqual(moved, key not in absorbed)


del Comparison          # la classe de base ne se lance pas seule


class Sources(unittest.TestCase):
    def test_the_values_are_read_from_the_files_of_the_starter_kit_not_copied(self):
        self.assertEqual(len(SCENARIOS), 3)
        self.assertEqual((PROFILE["opening_cash_chf"], PROFILE["age_at_start"], PROFILE["city"]),
                         (ALEXIA.profile.cash_chf, ALEXIA.profile.age, ALEXIA.profile.city))
        self.assertEqual(HORIZON, ALEXIA.horizon_months)

    def test_every_neutralised_assumption_exists_in_the_engine(self):
        """Une hypothèse renommée dans le moteur ne serait plus neutralisée : mieux vaut le dire clairement."""
        self.assertEqual(set(NEUTRAL) - set(defaults()), set())


if __name__ == "__main__":
    unittest.main()
