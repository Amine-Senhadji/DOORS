"""Vérifications comptables en direct, affichées dans l'interface (« Chaque franc est comptabilisé »).

Ce sont les mêmes règles que tests/test_engine.py, exécutées sur le scénario réellement
affiché avec les hypothèses choisies par l'utilisateur.
"""
from __future__ import annotations

from engine.contract import ASSET_ACCOUNTS, Category, Scenario
from engine.simulate import run

TOL = 1e-6


def _identities(r) -> tuple[bool, bool, int]:
    cash_ok = nw_ok = True
    prev = None
    for mo in r.months:
        cash = sum(f.amount_chf for f in mo.flows if f.account == "cash")
        cash_ok &= abs(mo.opening_cash_chf + cash - mo.closing_cash_chf) < TOL
        assets = sum(f.amount_chf for f in mo.flows if f.account in ASSET_ACCOUNTS)
        debt = sum(f.amount_chf for f in mo.flows if f.account == "dette")
        if prev is not None:
            nw_ok &= abs(prev + assets - debt - mo.net_worth_chf) < TOL
        nw_ok &= mo.closing_cash_chf >= -TOL and mo.debt_chf >= -TOL
        prev = mo.net_worth_chf
    return cash_ok, nw_ok, len(r.months)


def run_checks(sc: Scenario, line_ids: list[str], overrides: dict | None = None) -> list[dict]:
    results = [run(sc, lid, overrides) for lid in line_ids]
    ids = [_identities(r) for r in results]
    n = sum(i[2] for i in ids)
    out = [
        {"id": "reconciliation", "ok": all(i[0] for i in ids), "title": "Réconciliation du cash",
         "detail": f"Début + toutes les lignes du registre = fin, sur {n} mois."},
        {"id": "patrimoine", "ok": all(i[1] for i in ids), "title": "Patrimoine = actifs − dettes",
         "detail": "Vérifié à chaque mois. Le découvert est une dette, jamais effacé."},
    ]
    again = [run(sc, lid, overrides) for lid in line_ids]
    out.append({"id": "reproductible", "ok": all([m.net_worth_chf for m in a.months] == [m.net_worth_chf for m in b.months]
                                                 for a, b in zip(results, again)),
                "title": "Reproductible", "detail": "Mêmes hypothèses, même résultat au centime près."})
    rent = dict(overrides or {})
    rent["loyer"] = rent.get("loyer", 900) + 100
    income = lambda r: sum(f.amount_chf for mo in r.months for f in mo.flows if f.category == Category.REVENU)
    shifted = [run(sc, lid, rent) for lid in line_ids]
    out.append({"id": "isolation", "ok": all(abs(income(a) - income(b)) < TOL for a, b in zip(results, shifted)),
                "title": "Isolation d'une hypothèse", "detail": "Loyer +100 CHF : les revenus ne bougent pas."})
    zero = {**(overrides or {}), "job_net_mensuel": 0, "salaire_sans_master": 0, "salaire_apres_master": 0,
            "salaire_etranger_eur": 0}
    rz = run(sc, line_ids[0], zero)
    out.append({"id": "revenu_nul", "ok": rz.first_negative_month is not None,
                "title": "Cas limite : revenu nul",
                "detail": f"Pas d'erreur de calcul, financement signalé au mois {rz.first_negative_month}."})
    return out
