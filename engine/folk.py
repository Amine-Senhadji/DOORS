"""Une règle répandue, mise à l'épreuve : « trois mois d'épargne de précaution suffisent ».

Le moteur ne suit pas cette règle : il la teste. À un âge donné, il met sur le compte d'Alexia exactement trois mois
de ses dépenses courantes, rien d'autre, et regarde si elle passe dans le rouge pendant les deux ans qui suivent,
dans chaque monde testé (le monde de référence, et chaque crise placée à cet âge). Il le fait dans deux états :
Alexia salariée, et Alexia qui commence son master au même âge. La réponse dépend de l'état : c'est ce qu'une
règle fixe ne peut pas dire, et ce qu'une politique lit.
"""
from __future__ import annotations

import json

from engine import i18n
from engine import worlds as W
from engine.blocks import legs_of, normalize
from engine.explore import _monthly_expenses
from engine.i18n import say
from engine.tree import Tree, _chf

GARE = 60                                    # l'épreuve se fait à 25 ans : l'âge où l'histoire de la démo passe de l'emploi au master
CRISES = ("krach", "chomage_6_mois", "chomage_long", "perte_job_etudiant", "inflation", "crise_immobiliere", "franc_faible")
EMPLOYED = [{"block": "job", "years": 10}]
SEARCH = (0, 300_000)                        # où chercher le coussin qui suffirait, en CHF


def _holds(run, gare: int, window: int) -> tuple[bool, int | None, float]:
    """Le coussin tient-il ? Aucun financement nécessaire pendant la fenêtre. Sinon : le premier mois dans le rouge."""
    months = run.months[gare:gare + window]
    red = next((m.month for m in months if "financement_necessaire" in m.flags), None)
    return red is None, red, round(max((m.overdraft_chf for m in months), default=0.0), 2)


def view(tree: Tree, student_path: list[dict], overrides: dict | None = None) -> dict:
    key = (json.dumps(student_path, sort_keys=True), json.dumps(overrides or {}, sort_keys=True), i18n.current())
    cache = tree.__dict__.setdefault("_folk_views", {})
    if key in cache:
        return cache[key]
    th, age = tree.theta(overrides), tree.age(GARE)
    months, window = round(th["regle_coussin_mois"]), round(th["regle_coussin_fenetre_mois"])
    worlds = ("reference",) + tuple(W.canonical(f"{kind}@{age}", th, tree.h, tree.age0) for kind in CRISES)
    states = []
    for state_id, label, path in (("salariee", say(f"Employed at {age}", f"Salariée à {age} ans"), normalize(EMPLOYED, tree.h)),
                                  ("etudiante", say(f"Starting a master's at {age}", f"En master à {age} ans"), normalize(student_path, tree.h))):
        # Ses dépenses courantes à cet âge, comme le moteur les compte (logement, vie courante, santé), dans le monde de référence.
        expenses = _monthly_expenses(tree.trip(path, "reference", overrides)[0], GARE)
        cushion = months * expenses

        def test(cash: float) -> dict:
            out = {}
            for w in worlds:
                ok, red, peak = _holds(tree.with_cushion(path, GARE, cash, w, overrides), GARE, window)
                out[w] = {"holds": ok, "first_red_month": red, "first_red_age": None if red is None else tree.age(red),
                          "peak_financing_chf": peak}
            return out
        by_world = test(cushion)
        # Le coussin qui suffirait dans tous les mondes testés, à 100 CHF près, par dichotomie.
        enough = lambda cash: all(row["holds"] for row in test(cash).values())
        low, high = SEARCH
        if enough(low):
            needed = float(low)
        elif not enough(high):
            needed = None
        else:
            while high - low > 100:
                middle = (low + high) // 200 * 100
                low, high = (low, middle) if enough(middle) else (middle, high)
            needed = float(high)
        states.append({"id": state_id, "label": label, "path": path, "legs": legs_of(path, th, tree.h),
                       "expenses_chf": round(expenses, 2), "cushion_chf": round(cushion, 2), "by_world": by_world,
                       "kept": sum(row["holds"] for row in by_world.values()), "total": len(worlds),
                       "needed_chf": needed, "needed_months": None if needed is None else round(needed / expenses, 1)})
    employed, student = states
    if student["needed_chf"] is not None:
        enough = i18n.decimal(student["needed_months"])
        need = say(f"She would need {enough} months of expenses set aside ({_chf(student['needed_chf'])}), not {months}.",
                   f"Il lui faudrait {enough} mois de dépenses de côté ({_chf(student['needed_chf'])}), pas {months}.")
    else:
        need = say("No tested cushion is enough.", "Aucun coussin testé ne suffit.")
    rule = say(f"{months} months of emergency savings are enough", f"{months} mois d'épargne de précaution suffisent")
    sentence = say(f"“{rule}”: true in {employed['kept']} of the {employed['total']} tested worlds for Alexia employed at {age}, "
                   f"in {student['kept']} of the {student['total']} for Alexia starting her master's at the same age. {need}",
                   f"« {rule} » : vrai dans {employed['kept']} des {employed['total']} mondes testés "
                   f"pour Alexia salariée à {age} ans, dans {student['kept']} des {student['total']} pour Alexia qui commence son master "
                   f"au même âge. {need}")
    cache[key] = {"rule": {"months": months, "window_months": window, "age": age, "gare_month": GARE, "text": rule},
                  "worlds": W.describe(th, tree.h, tree.age0, list(worlds)), "states": states, "sentence": sentence}
    return cache[key]
