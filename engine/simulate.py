"""Boucle de simulation, chargement des scénarios JSON et mondes de référence.

Usage en ligne de commande (reproduit un scénario et imprime le registre d'un mois) :
    python -m engine.simulate engine/scenarios/alexia.json master --month 6
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import replace
from pathlib import Path

from engine.i18n import say
from engine.assumptions import defaults
from engine.contract import (ASSET_ACCOUNTS, Line, MonthRecord, Operation, Profile, Scenario,
                             SimulationResult, State, Station, World)
from engine.transition import monthly_rate, transition, validate

_TERM = re.compile(r"^\s*(\$[a-z_0-9]+|-?\d+(?:\.\d+)?)\s*$")


def resolve(value, th: dict[str, float]):
    """Un paramètre peut être un nombre, un texte, ou une référence à une hypothèse :
    "$salaire_apres_master" ou "24+$recherche_emploi_mois". Cela permet à la carte des
    frontières de faire varier une hypothèse sans réécrire le scénario."""
    if isinstance(value, bool) or not isinstance(value, str) or "$" not in value:
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value
    total = 0.0
    for term in value.split("+"):
        if not _TERM.match(term):
            raise ValueError(say(f"Invalid expression: “{value}”", f"Expression invalide : « {value} »"))
        term = term.strip()
        if term.startswith("$"):
            key = term[1:]
            if key not in th:
                raise ValueError(say(f"Missing assumption: “{key}” (used in “{value}”)",
                                     f"Hypothèse manquante : « {key} » (utilisée dans « {value} »)"))
            total += th[key]
        else:
            total += float(term)
    return total


def materialize(line: Line, th: dict[str, float]) -> tuple[Operation, ...]:
    ops = tuple(Operation(op.kind, int(round(resolve(op.start, th))), int(round(resolve(op.end, th))),
                          {k: resolve(v, th) for k, v in op.params.items()}) for op in line.operations)
    validate(ops)
    return ops


def load_scenario(path: str | Path) -> Scenario:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    lines = tuple(Line(l["id"], l["name"], tuple(Operation(o["kind"], o["start"], o["end"], o.get("params", {}))
                                                  for o in l["operations"])) for l in d["lines"])
    stations = tuple(Station(s["id"], s["month"], s["question"], tuple(s["options"]), tuple(s["axes"]))
                     for s in d.get("stations", []))
    return Scenario(Profile(**d["profile"]), d["horizon_months"], lines, stations,
                    d.get("assumption_overrides", {}))


def theta_for(scenario: Scenario, overrides: dict[str, float] | None = None) -> dict[str, float]:
    th = defaults()
    th.update(scenario.assumption_overrides)
    th.update(overrides or {})
    return th


def reference_world(th: dict[str, float], horizon: int) -> list[World]:
    """Monde de référence : rien d'exceptionnel, rendement moyen, taux de change constant."""
    w = World(market_return_monthly=monthly_rate(th["rendement_placements_annuel"]),
              inflation_monthly=0.0, fx_chf_per_eur=th["fx_initial"], job_lost=False,
              house_return_monthly=monthly_rate(th["hausse_prix_logement_annuelle"]))
    return [w] * horizon


def world_with_job_loss(th: dict[str, float], horizon: int, start: int, months: int) -> list[World]:
    """Monde de référence avec une perte d'emploi de `months` mois à partir du mois `start`."""
    return [replace(w, job_lost=start <= t < start + months) for t, w in enumerate(reference_world(th, horizon))]


def initial_state(profile: Profile, th: dict[str, float]) -> State:
    return State(month=0, age=float(profile.age), cash={"CHF": float(profile.cash_chf), "EUR": 0.0},
                 fx_chf_per_eur=th["fx_initial"])


def cash_chf(x: State) -> float:
    return x.cash.get("CHF", 0.0) + x.cash.get("EUR", 0.0) * x.fx_chf_per_eur


def debt_chf(x: State) -> float:
    return sum(l.principal_chf for l in x.loans) + x.overdraft_chf


def net_worth_chf(x: State) -> float:
    return cash_chf(x) + x.placements_chf + x.pilier2_chf + x.logement_chf - debt_chf(x)


def mortgage_chf(x: State) -> float:
    return sum(l.principal_chf for l in x.loans if l.id == "hypotheque")


def run_from(profile: Profile, x: State, ops: tuple[Operation, ...], until: int, th: dict[str, float],
             worlds: list[World], snapshots: tuple[int, ...] = ()) -> tuple[State, list[MonthRecord], dict[int, State]]:
    """Continue depuis un état : simule les mois x.month à until − 1, sans refaire le passé.

    F est pure et déterministe : reprendre à l'état atteint au mois G donne exactement les mêmes mois que la
    simulation complète. C'est ce qui permet de calculer l'arbre des trajets à la demande, gare par gare.
    `snapshots` : les mois (des gares) dont on garde l'état, pour repartir de là plus tard.
    Les opérations et le monde sont indexés en mois absolus, comptés depuis le départ.
    """
    if len(worlds) < until:
        raise ValueError(say(f"The world covers {len(worlds)} months, {until} are needed.",
                             f"Le monde couvre {len(worlds)} mois, il en faut {until}."))
    months: list[MonthRecord] = []
    states: dict[int, State] = {x.month: x} if x.month in snapshots else {}
    for t in range(x.month, until):
        opening = cash_chf(x)
        x, flows = transition(x, ops, worlds[t], th)
        months.append(MonthRecord(
            month=t, age=profile.age + t / 12, opening_cash_chf=opening, closing_cash_chf=cash_chf(x),
            placements_chf=x.placements_chf, pilier2_chf=x.pilier2_chf, debt_chf=debt_chf(x),
            net_worth_chf=net_worth_chf(x), flows=flows,
            flags=(["financement_necessaire"] if x.overdraft_chf > 0 else [])
                  + (["proprietaire"] if x.logement_chf > 0 else []),
            logement_chf=x.logement_chf, hypotheque_chf=mortgage_chf(x), overdraft_chf=x.overdraft_chf))
        if x.month in snapshots:
            states[x.month] = x
    return x, months, states


def summarize(months: list[MonthRecord], line_id: str = "ligne", world_id: str = "reference") -> SimulationResult:
    """Le résumé d'une vie entière, à partir de ses mois : le passé compte autant que la suite."""
    liquidity = [months[0].opening_cash_chf] + [m.closing_cash_chf - m.overdraft_chf for m in months]
    first_neg = next((m.month for m in months if "financement_necessaire" in m.flags), None)
    return SimulationResult(line_id, world_id, months, min(liquidity), first_neg,
                            max(0.0, -min(liquidity)), months[-1].net_worth_chf)


def run_ops(profile: Profile, ops: tuple[Operation, ...], horizon: int, th: dict[str, float],
            worlds: list[World] | None = None, line_id: str = "ligne",
            world_id: str = "reference") -> SimulationResult:
    return run_with_states(profile, ops, horizon, th, worlds, line_id, world_id)[0]


def run_with_states(profile: Profile, ops: tuple[Operation, ...], horizon: int, th: dict[str, float],
                    worlds: list[World] | None = None, line_id: str = "ligne", world_id: str = "reference",
                    snapshots: tuple[int, ...] = ()) -> tuple[SimulationResult, dict[int, State]]:
    """Une vie entière depuis le départ, et l'état atteint à chacun des mois demandés (les gares)."""
    validate(ops)
    worlds = worlds or reference_world(th, horizon)
    _, months, states = run_from(profile, initial_state(profile, th), ops, horizon, th, worlds, snapshots)
    return summarize(months, line_id, world_id), states


def resume(profile: Profile, past: list[MonthRecord], x: State, ops: tuple[Operation, ...], horizon: int,
           th: dict[str, float], worlds: list[World] | None = None, line_id: str = "ligne",
           world_id: str = "reference") -> SimulationResult:
    """La vie entière d'un trajet qui bifurque : les mois déjà vécus jusqu'à la gare, puis la suite depuis l'état x."""
    validate(ops)
    if len(past) != x.month:
        raise ValueError(say(f"The past holds {len(past)} months, the state resumes at month {x.month}.",
                             f"Le passé compte {len(past)} mois, l'état reprend au mois {x.month}."))
    worlds = worlds or reference_world(th, horizon)
    _, months, _ = run_from(profile, x, ops, horizon, th, worlds)
    return summarize(past + months, line_id, world_id)


def truncate(ops: tuple[Operation, ...], month: int) -> tuple[Operation, ...]:
    """Les opérations telles qu'elles se sont déroulées avant une gare : ce qui commence après disparaît, le reste s'y arrête."""
    return tuple(Operation(op.kind, op.start, min(op.end, month), op.params) for op in ops if op.start < month)


def run(scenario: Scenario, line_id: str, overrides: dict[str, float] | None = None,
        worlds: list[World] | None = None, world_id: str = "reference") -> SimulationResult:
    line = next((l for l in scenario.lines if l.id == line_id), None)
    if line is None:
        raise ValueError(say(f"Unknown line “{line_id}”. Lines: {[l.id for l in scenario.lines]}",
                             f"Ligne inconnue « {line_id} ». Lignes : {[l.id for l in scenario.lines]}"))
    th = theta_for(scenario, overrides)
    return run_ops(scenario.profile, materialize(line, th), scenario.horizon_months, th,
                   worlds, line_id, world_id)


def _main() -> None:
    ap = argparse.ArgumentParser(description="Rejoue une ligne d'un scénario et imprime le registre d'un mois.")
    ap.add_argument("scenario")
    ap.add_argument("line")
    ap.add_argument("--month", type=int, default=0)
    args = ap.parse_args()
    sc = load_scenario(args.scenario)
    r = run(sc, args.line)
    print(f"{sc.profile.name} · ligne « {args.line} » · monde {r.world_id} · {sc.horizon_months} mois")
    print(f"  Patrimoine final : {r.net_worth_end_chf:>12,.2f} CHF")
    print(f"  Financement max  : {r.peak_financing_chf:>12,.2f} CHF"
          + (f" (premier besoin au mois {r.first_negative_month})" if r.first_negative_month is not None else ""))
    mo = r.months[args.month]
    print(f"\nRegistre du mois {mo.month} (âge {mo.age:.1f})")
    print(f"  {'Cash début':<52}{mo.opening_cash_chf:>12,.2f}")
    for f in mo.flows:
        print(f"  {f.account:<11}{f.label:<41}{f.amount_chf:>+12,.2f}")
    print(f"  {'Cash fin':<52}{mo.closing_cash_chf:>12,.2f}")
    print(f"  {'Patrimoine':<52}{mo.net_worth_chf:>12,.2f}")


if __name__ == "__main__":
    _main()
