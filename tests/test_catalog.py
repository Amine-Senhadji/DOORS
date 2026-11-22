"""Tests du catalogue : les 120 scénarios sont encodés, et chaque scénario couvert est sain."""
from __future__ import annotations

from engine import i18n

i18n.set_default("fr")      # ces tests attendent les phrases du moteur en français ; l'anglais est testé dans tests/test_english.py

import unittest

from engine.catalog import SPECS, catalog_names, run_spec

RESULTS = {s.id: run_spec(s) for s in SPECS}


class Catalog(unittest.TestCase):
    def test_every_catalog_scenario_is_encoded_exactly_once(self):
        ids = [s.id for s in SPECS]
        self.assertEqual(len(ids), len(set(ids)), "Un scénario est encodé deux fois")
        self.assertEqual(set(ids), set(catalog_names()), "Le catalogue et l'encodage divergent")

    def test_labels_are_valid(self):
        for s in SPECS:
            with self.subTest(id=s.id):
                self.assertIn(s.family, ("A", "B", "C"))
                self.assertIn(s.fidelity, ("modelise", "approxime", "non_couvert"))
                if s.fidelity == "approxime":
                    self.assertTrue(s.note, "Une approximation doit être écrite")
                if s.fidelity == "non_couvert":
                    self.assertTrue(s.missing, "Un scénario non couvert doit nommer l'opération manquante")

    def test_covered_scenarios_keep_accounting_identities(self):
        for sid, r in RESULTS.items():
            if r["fidelity"] != "non_couvert":
                with self.subTest(id=sid):
                    self.assertTrue(r["identities_ok"])

    def test_intervention_really_changes_the_outcome(self):
        """FAQ, erreur classique n°6 : deux scénarios qui donnent exactement le même résultat."""
        for sid, r in RESULTS.items():
            if r["fidelity"] != "non_couvert":
                with self.subTest(id=sid):
                    self.assertTrue(r["changed"], "L'intervention ne change rien : le scénario ne teste rien")

    def test_expected_directions(self):
        """Quelques sens évidents : plus de dépenses ou un choc ne rendent jamais plus riche."""
        for sid in ("S004", "S014", "S037", "S042", "S047", "S048", "S058", "S065", "S085", "S101", "S110"):
            with self.subTest(id=sid):
                self.assertLess(RESULTS[sid]["delta"], 0)
        for sid in ("S012", "S032", "S041", "S056", "S057", "S102"):
            with self.subTest(id=sid):
                self.assertGreater(RESULTS[sid]["delta"], 0)


if __name__ == "__main__":
    unittest.main()
