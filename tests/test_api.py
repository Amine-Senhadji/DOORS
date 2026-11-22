"""Tests de bout en bout de l'API (ignorés si FastAPI n'est pas installé)."""
from __future__ import annotations

import unittest

try:
    from fastapi.testclient import TestClient
    from api.main import app
except ImportError:  # pragma: no cover
    TestClient = None


@unittest.skipIf(TestClient is None, "FastAPI non installé : .venv/bin/pip install -r requirements.txt")
class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(app)

    def test_scenario_and_assumptions(self):
        self.assertEqual(self.c.get("/scenario/alexia").json()["profile"]["name"], "Alexia")
        keys = {a["key"] for a in self.c.get("/assumptions").json()}
        self.assertIn("lamal_jeune", keys)
        self.assertEqual(self.c.get("/scenario/inconnu").status_code, 404)

    def test_simulate_returns_ledger_matching_contract(self):
        r = self.c.post("/simulate", json={"line_id": "master", "assumptions": {"job_net_mensuel": 1200}}).json()
        self.assertEqual(r["first_negative_month"], 3)       # 8'000 CHF de côté, 4'000 CHF de frais d'études dès le premier mois
        flow = r["months"][0]["flows"][0]                    # le premier flux du premier mois : le job étudiant
        self.assertEqual(set(flow), {"month", "label", "category", "account", "amount", "currency", "amount_chf", "rule"})
        self.assertEqual(flow["category"], "revenu")

    def test_compare_frontier_checks(self):
        c = self.c.post("/compare", json={"station_id": "m12_master"}).json()
        self.assertEqual(c["shared_past"]["until_month"], 12)
        f = self.c.post("/frontier", json={"station_id": "depart",
                                           "x": {"key": "job_net_mensuel", "min": 0, "max": 2800, "steps": 4},
                                           "y": {"key": "salaire_apres_master", "min": 4000, "max": 8500, "steps": 4}}).json()
        self.assertEqual(len(f["cells"]), 4)
        self.assertTrue(all(ch["ok"] for ch in self.c.get("/checks").json()))

    def test_errors_are_explained(self):
        self.assertEqual(self.c.post("/simulate", json={"line_id": "inexistante"}).status_code, 422)
        bad_world = self.c.post("/simulate", json={"line_id": "master", "world_id": "crise_2008"})
        self.assertEqual(bad_world.status_code, 400)
        self.assertIn("pas encore disponible", bad_world.json()["detail"])
        self.assertEqual(self.c.post("/ask").status_code, 501)


if __name__ == "__main__":
    unittest.main()
