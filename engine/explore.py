"""Exploration au-dessus du moteur : portes, comparaison à une station, carte des frontières.

Tout ici est déterministe et ne fait qu'appeler le moteur. Aucune probabilité : une porte
est ouverte ou fermée dans un monde donné. (Le Monte Carlo pourra plus tard donner des
portes « entrouvertes » en comptant les mondes.)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from engine import english
from engine.i18n import percent, say
from engine.assumptions import by_key
from engine.contract import Category, Scenario, SimulationResult, Station, World
from engine.simulate import run, theta_for

_EXPENSES = (Category.LOGEMENT, Category.VIE_COURANTE, Category.SANTE)


# ----------------------------------------------------------------------------- portes
# Six portes, au vocabulaire des objectifs du défi (Data/synthetic-goals.csv). Chacune est ouverte ou fermée
# dans un monde donné. Les portes datées se testent sur l'état atteint à leur âge ; « jamais dans le rouge »
# porte sur tout le trajet, et « logement » sur la fin de la période.
@dataclass(frozen=True)
class Door:
    key: str
    name: str
    rule: str                                             # gabarit ; l'écrire avec rule_text(porte, theta)
    test: Callable[[SimulationResult, dict, int], bool]   # (résultat, theta, âge de départ)
    age_key: str | None = None                            # l'hypothèse qui donne l'âge du test
    at_end: bool = False                                  # testée à la fin de la période
    # Ce qui explique la couleur : (valeur atteinte, valeur demandée), en CHF. None si la règle a plusieurs conditions.
    measure: Callable[[SimulationResult, dict, int], tuple[float, float]] | None = None
    source_key: str | None = None                         # l'hypothèse qui porte l'origine de l'objectif (nature et source)


class _Fr(float):
    """Un nombre qui s'écrit dans une règle, les montants au format suisse : {x:chf} -> 12'800 CHF, {x:pct} -> 30 %, {x:n} -> 25."""

    def __format__(self, spec: str) -> str:
        if spec == "chf":
            return f"{self:,.0f}".replace(",", "'") + " CHF"
        if spec == "pct":
            return percent(float(self))
        if spec == "n":
            return f"{self:.0f}"
        return float.__format__(self, spec)


def rule_text(door: Door, th: dict) -> str:
    """La règle d'une porte, écrite avec les hypothèses en cours."""
    rule = say(english.DOORS[door.key][1], door.rule)
    return rule.format(**{k: _Fr(v) for k, v in th.items()})


def door_name(door: Door) -> str:
    """Le nom d'une porte, dans la langue courante."""
    return say(english.DOORS[door.key][0], door.name)


def door_age(door: Door, th: dict, age0: int, horizon_months: int) -> float | None:
    """L'âge où la porte est testée. None : elle porte sur tout le trajet."""
    if door.at_end:
        return age0 + horizon_months / 12
    return None if door.age_key is None else th[door.age_key]


def _month_at(r: SimulationResult, age0: int, age: float) -> int:
    return max(0, min(len(r.months) - 1, int(round((age - age0) * 12)) - 1))


def _liquidity(r: SimulationResult, m: int) -> float:
    mo = r.months[m]
    # L'hypothèque est adossée au logement : elle n'entame pas le coussin de liquidité.
    return mo.closing_cash_chf + mo.placements_chf - (mo.debt_chf - mo.hypotheque_chf)


def _monthly_expenses(r: SimulationResult, m: int) -> float:
    return -sum(f.amount_chf for f in r.months[m].flows if f.category in _EXPENSES and f.account == "cash")


def _never_red(r, th, age0) -> tuple[float, float]:
    """Le solde le plus bas du trajet, découvert financé compris : il doit rester au-dessus de zéro."""
    return r.min_cash_chf, 0.0


def _cushion(r, th, age0) -> tuple[float, float]:
    return _liquidity(r, _month_at(r, age0, th["coussin_age"])), th["coussin_montant"]


def _studies(r, th, age0) -> tuple[float, float]:
    """De quoi vivre en étudiante sans aucun revenu : loyer, vie courante, LAMal, AVS minimale et taxes d'études."""
    year = 12 * (th["loyer"] + th["vie_courante"] + th["lamal_adulte"]) + th["avs_min_annuel"] + 2 * th["taxe_semestre"]
    return _liquidity(r, _month_at(r, age0, th["etudes_age"])), th["etudes_annees"] * year


def _career_change(r, th, age0) -> tuple[float, float]:
    return _liquidity(r, _month_at(r, age0, th["reconversion_age"])), th["reconversion_montant"]


def _resilience(r, th, age0) -> tuple[float, float]:
    """Ce qui reste de côté après une baisse des placements, face à quelques mois de dépenses courantes."""
    m = _month_at(r, age0, th["resilience_age"])
    return (_liquidity(r, m) - th["resilience_baisse"] * r.months[m].placements_chf,
            th["resilience_mois"] * _monthly_expenses(r, m))


def _met(measure) -> Callable[[SimulationResult, dict, int], bool]:
    def test(r, th, age0) -> bool:
        value, required = measure(r, th, age0)
        return value >= required
    return test


def _home(r, th, age0) -> bool:
    """Règle suisse de capacité, simplifiée : fonds propres et charges théoriques."""
    end, price = r.months[-1], th["prix_logement"]
    if end.logement_chf > 0:
        return True                  # déjà propriétaire
    hard = max(0.0, end.closing_cash_chf + end.placements_chf - end.debt_chf)
    equity = min(price, hard + min(end.pilier2_chf, max(0.0, th["fonds_propres_min"] - th["fonds_propres_durs_min"]) * price))
    mortgage = price - equity
    amort = max(0.0, mortgage - 2 / 3 * price) / th["amortissement_annees"]
    charges = mortgage * th["taux_theorique"] + amort + price * th["entretien_logement"]
    gross_year = 12 * sum(f.amount_chf for f in end.flows if f.label == "Salaire brut")
    return (hard >= th["fonds_propres_durs_min"] * price and equity >= th["fonds_propres_min"] * price
            and gross_year > 0 and charges <= th["ratio_charges_max"] * gross_year)


DOORS: tuple[Door, ...] = (
    Door("jamais_rouge", "Ne jamais passer dans le rouge",
         "Aucun financement de découvert sur toute la période.",
         lambda r, th, a0: r.first_negative_month is None, measure=_never_red),
    Door("coussin", "Épargne de précaution",
         "À {coussin_age:n} ans, cash + placements − dettes atteignent {coussin_montant:chf} (objectif d'Alexia dans les données synthétiques du défi).",
         _met(_cushion), age_key="coussin_age", measure=_cushion, source_key="coussin_montant"),
    Door("etudes", "Reprendre des études",
         "À {etudes_age:n} ans, cash + placements − dettes couvrent {etudes_annees:n} ans de vie d'étudiante sans revenu : "
         "loyer, vie courante, LAMal, AVS minimale et taxes d'études.",
         _met(_studies), age_key="etudes_age", measure=_studies, source_key="etudes_annees"),
    Door("reconversion", "Reconversion",
         "À {reconversion_age:n} ans, cash + placements − dettes atteignent {reconversion_montant:chf} (objectif d'Alexia dans les données synthétiques du défi).",
         _met(_career_change), age_key="reconversion_age", measure=_career_change, source_key="reconversion_montant"),
    Door("resilience", "Résilience",
         "À {resilience_age:n} ans, après une baisse de {resilience_baisse:pct} des placements, il reste de quoi couvrir "
         "{resilience_mois:n} mois de dépenses courantes.",
         _met(_resilience), age_key="resilience_age", measure=_resilience, source_key="resilience_mois"),
    Door("logement", "Apport pour un logement",
         "À la fin de la période : fonds propres d'au moins {fonds_propres_min:pct} d'un bien de {prix_logement:chf} "
         "(dont {fonds_propres_durs_min:pct} hors 2e pilier), charges théoriques sous {ratio_charges_max:pct} du revenu brut.",
         _home, at_end=True, source_key="prix_logement"),
)
DOOR_KEYS = {d.key: d for d in DOORS}


def doors_of(r: SimulationResult, th: dict, age0: int) -> dict[str, bool]:
    return {d.key: d.test(r, th, age0) for d in DOORS}


def margins_of(r: SimulationResult, th: dict, age0: int) -> dict[str, tuple[float, float] | None]:
    """Pour chaque porte : (valeur atteinte, valeur demandée), ou None quand la règle a plusieurs conditions."""
    return {d.key: d.measure(r, th, age0) if d.measure else None for d in DOORS}


# ------------------------------------------------------------------------- comparaison
def _station(sc: Scenario, station_id: str) -> Station:
    st = next((s for s in sc.stations if s.id == station_id), None)
    if st is None:
        raise ValueError(say(f"Unknown station “{station_id}”. Stations: {[s.id for s in sc.stations]}",
                             f"Station inconnue « {station_id} ». Stations : {[s.id for s in sc.stations]}"))
    return st


def _name(sc: Scenario, line_id: str) -> str:
    return next(l.name for l in sc.lines if l.id == line_id)


def _summary(sc: Scenario, r: SimulationResult) -> dict:
    return {"line_id": r.line_id, "name": _name(sc, r.line_id), "net_worth_end_chf": round(r.net_worth_end_chf, 2),
            "peak_financing_chf": round(r.peak_financing_chf, 2), "first_negative_month": r.first_negative_month}


def catches_up_month(a: SimulationResult, b: SimulationResult) -> int | None:
    """Premier mois à partir duquel A reste devant B jusqu'à la fin."""
    month = None
    for ma, mb in zip(reversed(a.months), reversed(b.months)):
        if ma.net_worth_chf < mb.net_worth_chf:
            break
        month = ma.month
    return month


def compare(sc: Scenario, station_id: str, overrides: dict | None = None,
            worlds: list[World] | None = None, world_id: str = "reference") -> dict:
    st, th = _station(sc, station_id), theta_for(sc, overrides)
    a = run(sc, st.options[0], overrides, worlds, world_id)
    b = run(sc, st.options[1], overrides, worlds, world_id)
    shared = None
    if st.month > 0:
        same = all(abs(x.net_worth_chf - y.net_worth_chf) < 1e-6 for x, y in zip(a.months[:st.month], b.months[:st.month]))
        if same:
            shared = {"until_month": st.month, "cash_chf": round(a.months[st.month - 1].closing_cash_chf, 2),
                      "net_worth_chf": round(a.months[st.month - 1].net_worth_chf, 2),
                      "note": say("Identical on both sides: left out of the comparison.", "Identique des deux côtés : n'entre pas dans la comparaison.")}
    da, db = doors_of(a, th, sc.profile.age), doors_of(b, th, sc.profile.age)
    state = lambda ok: "ouverte" if ok else "fermee"
    return {
        "station_id": st.id, "question": st.question, "world_id": world_id,
        "a": _summary(sc, a), "b": _summary(sc, b), "shared_past": shared,
        "doors": [{"key": d.key, "name": door_name(d), "rule": rule_text(d, th), "a": state(da[d.key]), "b": state(db[d.key])}
                  for d in DOORS],
        "a_catches_up_month": catches_up_month(a, b),
    }


# ------------------------------------------------------------------- carte des frontières
def _cell(sc: Scenario, st: Station, criterion: str, values: dict, worlds) -> dict:
    a = run(sc, st.options[0], values, worlds)
    b = run(sc, st.options[1], values, worlds)
    if criterion == "patrimoine":
        winner = "a" if a.net_worth_end_chf > b.net_worth_end_chf else "b"
    else:
        if criterion not in DOOR_KEYS:
            raise ValueError(say(f"Unknown criterion “{criterion}”. Criteria: patrimoine, {', '.join(DOOR_KEYS)}",
                                 f"Critère inconnu « {criterion} ». Critères : patrimoine, {', '.join(DOOR_KEYS)}"))
        th = theta_for(sc, values)
        oa = DOOR_KEYS[criterion].test(a, th, sc.profile.age)
        ob = DOOR_KEYS[criterion].test(b, th, sc.profile.age)
        winner = {(True, False): "a", (False, True): "b", (True, True): "les_deux", (False, False): "aucune"}[(oa, ob)]
    ref = b if winner == "b" else a
    return {"winner": winner, "needs_financing": ref.peak_financing_chf > 0.5}


def _linspace(lo: float, hi: float, n: int) -> list[float]:
    return [lo + (hi - lo) * i / (n - 1) for i in range(n)] if n > 1 else [lo]


def _fmt(key: str, v: float) -> str:
    a = by_key().get(key)
    unit = a.unit if a else ""
    if unit.startswith("%"):
        return f"{v:.1%}"
    return f"{v:,.0f}".replace(",", "'") + (f" {unit}" if unit else "")


def frontier(sc: Scenario, station_id: str, x: dict, y: dict, criterion: str = "patrimoine",
             overrides: dict | None = None, worlds: list[World] | None = None, scan_steps: int = 40,
             refine_steps: int = 12) -> dict:
    """Carte des frontières : x et y = {"key", "min", "max", "steps"}."""
    st, base = _station(sc, station_id), dict(overrides or {})
    th = theta_for(sc, base)
    xs, ys = _linspace(x["min"], x["max"], x["steps"]), _linspace(y["min"], y["max"], y["steps"])
    cells = [[_cell(sc, st, criterion, {**base, x["key"]: xv, y["key"]: yv}, worlds) for yv in ys] for xv in xs]

    toi = {"x": th[x["key"]], "y": th[y["key"]]}
    toi_cell = _cell(sc, st, criterion, {**base, x["key"]: toi["x"], y["key"]: toi["y"]}, worlds)
    toi["winner"] = toi_cell["winner"]

    tippings = []
    for axis, spec, other in (("x", x, y), ("y", y, x)):
        fixed = {**base, other["key"]: toi["y" if axis == "x" else "x"]}
        winner_at = lambda v: _cell(sc, st, criterion, {**fixed, spec["key"]: v}, worlds)["winner"]
        cur, best = toi[axis], None
        # Grille de balayage qui contient exactement la position de « Toi ».
        grid = sorted(set(_linspace(spec["min"], spec["max"], scan_steps)) | {cur})
        winners = [winner_at(v) for v in grid]
        for (lo, wlo), (hi, whi) in zip(zip(grid, winners), zip(grid[1:], winners[1:])):
            if wlo == whi:
                continue
            # Dichotomie : on resserre [lo, hi] jusqu'à la frontière exacte.
            for _ in range(refine_steps):
                mid = (lo + hi) / 2
                if winner_at(mid) == wlo:
                    lo = mid
                else:
                    hi = mid
            edge, beyond = ((hi, whi) if hi > cur else (lo, wlo))
            if best is None or abs(edge - cur) < abs(best["value"] - cur):
                best = {"axis": axis, "key": spec["key"], "value": edge, "winner_beyond": beyond,
                        "direction": "au-dessus" if edge > cur else "en dessous",
                        "distance": abs(edge - cur) / max(1e-9, spec["max"] - spec["min"])}
        if best:
            tippings.append(best)
    tippings.sort(key=lambda t: t["distance"])

    labels = {"a": _name(sc, st.options[0]), "b": _name(sc, st.options[1]),
              "les_deux": say("Both lines", "Les deux lignes"), "aucune": say("Neither line", "Aucune ligne")}
    rules = []
    for t in tippings:
        label = by_key()[t["key"]].label.lower() if t["key"] in by_key() else t["key"]
        above = t["direction"] == "au-dessus"
        rules.append(say(f"If {label} {'goes above' if above else 'falls below'} about {_fmt(t['key'], t['value'])}, "
                         f"{labels[t['winner_beyond']].lower()} comes out ahead (other assumptions unchanged).",
                         f"Si {label} {'dépasse' if above else 'descend sous'} environ {_fmt(t['key'], t['value'])}, "
                         f"{labels[t['winner_beyond']].lower()} l'emporte (autres hypothèses inchangées)."))
    if not tippings:
        rules.append(say(f"{labels[toi['winner']]} comes out ahead across the whole map with these assumptions.",
                         f"{labels[toi['winner']]} l'emporte sur toute la carte avec ces hypothèses."))
    return {"station_id": st.id, "criterion": criterion, "x_key": x["key"], "y_key": y["key"],
            "x_values": xs, "y_values": ys, "cells": cells, "toi": toi,
            "nearest_tipping": ({k: v for k, v in tippings[0].items() if k != "distance"} if tippings else None),
            "rules": rules, "labels": labels}
