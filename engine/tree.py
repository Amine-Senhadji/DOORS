"""L'arbre des trajets : un trajet dans chaque monde, les branches d'une gare, les chemins d'adaptation.

Tout ici ne fait qu'appeler le moteur. L'arbre est calculé à la demande : un trajet est simulé une fois par
monde, l'état atteint à chaque gare est gardé, et une branche repart de cet état sans refaire le passé
(engine/simulate.py, run_from). tests/test_tree.py vérifie qu'une branche ainsi calculée est exactement
le même trajet simulé depuis le départ.

Vocabulaire (docs/ARCHITECTURE.md) : une gare est un point de décision, une fois par an ; une porte est ouverte
ou fermée dans un monde ; aucun monde n'est dit probable, aucune branche n'est dite meilleure.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, replace

from engine import english, i18n
from engine import worlds as W
from engine.assumptions import by_key
from engine.blocks import blocks_to_ops, destinations, legs_of, normalize
from engine.contract import Category, Flow, Scenario, SimulationResult, State
from engine.explore import DOORS, door_age, door_name, doors_of, margins_of, rule_text
from engine.i18n import say
from engine.simulate import (cash_chf, debt_chf, initial_state, net_worth_chf, resume, run_from, run_with_states, summarize,
                             theta_for)



def horizon_text() -> str:
    """Jusqu'où la flexibilité regarde : une des branches d'ici, ou le trajet avec un seul changement plus tard."""
    return say("changing route at most once", "en changeant de route au plus une fois")


def variable_label(variable: str) -> str:
    """Le nom d'une grandeur lue par une règle, dans la langue courante."""
    return say("set aside (cash + investments − debts)", VARIABLES[variable][0])
TIP_RANGE = (-100_000, 1_000_000)      # où chercher un point de bascule en épargne, en CHF


def _chf(value: float) -> str:
    """Un montant au format suisse, comme l'écran l'écrit : 50'100 CHF."""
    return ("−" if round(value) < 0 else "") + f"{abs(round(value)):,}".replace(",", "'") + " CHF"


# Les grandeurs qu'une règle ou un signal peut lire dans l'état atteint à une gare : un nom, et la façon de la lire.
VARIABLES = {
    "liquidite_chf": ("de côté (cash + placements − dettes)", lambda x: cash_chf(x) + x.placements_chf - debt_chf(x)),
}


def observe(x: State, value: float) -> tuple[State, dict[str, float]]:
    """Le jumeau qui apprend : remplace ce qu'Alexia a de côté dans l'état simulé (cash + placements − dettes) par la valeur
    qu'elle constate. S'il y a plus que prévu : le découvert est remboursé d'abord, le reste va sur le compte. S'il y a moins :
    on prend sur le compte, puis sur les placements, puis c'est un découvert. Rend le nouvel état et l'écart par compte."""
    delta = value - VARIABLES["liquidite_chf"][1](x)
    cash, placements, overdraft = dict(x.cash), x.placements_chf, x.overdraft_chf
    moves = {"cash": 0.0, "placements": 0.0, "dette": 0.0}
    if delta > 0:
        repaid = min(delta, overdraft)
        overdraft, moves["dette"] = overdraft - repaid, -repaid
        cash["CHF"] = cash.get("CHF", 0.0) + delta - repaid
        moves["cash"] = delta - repaid
    else:
        need = -delta
        for currency, rate in (("CHF", 1.0), ("EUR", x.fx_chf_per_eur)):
            taken = min(need, max(0.0, cash.get(currency, 0.0) * rate))
            cash[currency] = cash.get(currency, 0.0) - taken / rate
            moves["cash"] -= taken
            need -= taken
        sold = min(need, max(0.0, placements))
        placements, moves["placements"], need = placements - sold, -sold, need - sold
        overdraft, moves["dette"] = overdraft + need, need
    return replace(x, cash=cash, placements_chf=placements, overdraft_chf=overdraft), moves


@dataclass(frozen=True)
class Rule:
    """Une règle adaptative, écrite comme une donnée : à cette gare, si cette grandeur est sous ce seuil, prendre cette branche.

    La décision ne regarde que l'état atteint à la gare, jamais la suite. Comme c'est une donnée (gare, grandeur,
    seuil, branche), on pourra plus tard chercher le seuil automatiquement sur beaucoup de mondes.
    """
    gare_month: int
    variable: str
    threshold_chf: float
    branch_id: str

    def applies(self, x: State) -> bool:
        return VARIABLES[self.variable][1](x) < self.threshold_chf


class Tree:
    """L'arbre d'un scénario. Garde en mémoire les trajets déjà simulés, par monde et par jeu d'hypothèses."""

    def __init__(self, scenario: Scenario):
        self.sc = scenario
        self.h = scenario.horizon_months
        self.age0 = scenario.profile.age
        self.gares = tuple(range(12, self.h, 12))
        self._full: dict[tuple, tuple[SimulationResult, dict[int, State]]] = {}
        self._branch: dict[tuple, SimulationResult] = {}
        self._seen: dict[tuple, tuple[SimulationResult, dict[int, State]]] = {}
        self._tips: dict[tuple, float | None] = {}
        self._zones: dict[tuple, dict | None] = {}

    # ------------------------------------------------------------------ simulation
    def theta(self, overrides: dict | None) -> dict:
        return theta_for(self.sc, overrides)

    def asked(self, mondes, overrides: dict | None) -> tuple[str, ...]:
        """Les mondes à tester, sous leur identifiant : « krach », « krach@25 » pour un krach déplacé à 25 ans, ou
        « krach@24+chomage_long@25 » pour deux crises dans le même monde."""
        return W.asked(mondes, self.theta(overrides), self.h, self.age0)

    def world(self, th: dict, world_id: str):
        return W.build(th, world_id, self.h, self.age0)

    @staticmethod
    def _key(path: list[dict], world_id: str, overrides: dict | None) -> tuple:
        return json.dumps(path, sort_keys=True), world_id, json.dumps(overrides or {}, sort_keys=True)

    def age(self, month: int) -> float:
        age = self.age0 + month / 12
        return int(age) if age == int(age) else round(age, 2)

    def trip(self, path: list[dict], world_id: str, overrides: dict | None) -> tuple[SimulationResult, dict[int, State]]:
        """Un trajet entier dans un monde, et l'état atteint à chaque gare. `path` est déjà sous forme canonique."""
        key = self._key(path, world_id, overrides)
        if key not in self._full:
            th = self.theta(overrides)
            self._full[key] = run_with_states(self.sc.profile, blocks_to_ops(path, th, self.h), self.h, th,
                                              self.world(th, world_id), "trajet", world_id, snapshots=self.gares)
            self._branch[key] = self._full[key][0]
        return self._full[key]

    def branch(self, parent: list[dict], gare_month: int, path: list[dict], world_id: str, overrides: dict | None) -> SimulationResult:
        """Le trajet `path`, qui quitte `parent` à une gare : on repart de l'état du parent à cette gare."""
        key = self._key(path, world_id, overrides)
        if key not in self._branch:
            if gare_month == 0 or not parent:
                return self.trip(path, world_id, overrides)[0]
            th = self.theta(overrides)
            past, states = self.trip(parent, world_id, overrides)
            self._branch[key] = resume(self.sc.profile, past.months[:gare_month], states[gare_month],
                                       blocks_to_ops(path, th, self.h), self.h, th, self.world(th, world_id), "trajet", world_id)
        return self._branch[key]

    def observed(self, path: list[dict], gare_month: int, value: float, new_path: list[dict], world_id: str,
                 overrides: dict | None, keep: bool = True) -> tuple[SimulationResult, dict[int, State]]:
        """Le trajet `new_path` à partir de la gare, en repartant de ce qu'Alexia a vraiment de côté, pas de l'état simulé.
        Le passé reste celui du trajet `path` ; l'écart est écrit dans le registre du premier mois, pour que chaque franc
        reste comptabilisé. Rend aussi l'état atteint aux gares suivantes. `keep` : garder le résultat en mémoire."""
        key = (*self._key(new_path, world_id, overrides), json.dumps(path, sort_keys=True), gare_month, float(value))
        if key not in self._seen:
            th = self.theta(overrides)
            past, states = self.trip(path, world_id, overrides)
            x, moves = observe(states[gare_month], value)
            answer = self._continue(past, states[gare_month], x, moves, new_path, world_id, th,
                                    "Écart entre l'épargne constatée et l'épargne simulée", "observation")
            if not keep:
                return answer
            self._seen[key] = answer
        return self._seen[key]

    def _continue(self, past: SimulationResult, simulated: State, x: State, moves: dict[str, float], new_path: list[dict],
                  world_id: str, th: dict, label: str, rule: str) -> tuple[SimulationResult, dict[int, State]]:
        """La suite d'un trajet depuis un état qui n'est pas l'état simulé. L'écart, compte par compte, est écrit dans le
        registre du premier mois : chaque franc reste comptabilisé, et les identités comptables tiennent."""
        gare = x.month
        _, months, later = run_from(self.sc.profile, x, blocks_to_ops(new_path, th, self.h), self.h, th,
                                    self.world(th, world_id), snapshots=self.gares)
        first = months[0]
        first.opening_cash_chf = cash_chf(simulated)
        first.flows = [Flow(gare, label, Category.PONCTUEL, account, amount, "CHF", amount, rule)
                       for account, amount in moves.items() if abs(amount) > 1e-9] + first.flows
        return summarize(past.months[:gare] + months, "trajet", world_id), later

    def with_cushion(self, path: list[dict], gare_month: int, cash_chf_asked: float, world_id: str,
                     overrides: dict | None) -> SimulationResult:
        """Le trajet depuis une gare, avec exactement ce coussin sur le compte : aucun placement, aucun découvert.
        Sert à mettre une règle répandue à l'épreuve (« trois mois de dépenses de côté suffisent »)."""
        th = self.theta(overrides)
        past, states = self.trip(path, world_id, overrides)
        simulated = states[gare_month]
        x = replace(simulated, cash={"CHF": float(cash_chf_asked)}, placements_chf=0.0, overdraft_chf=0.0)
        moves = {"cash": cash_chf_asked - cash_chf(simulated), "placements": -simulated.placements_chf, "dette": -simulated.overdraft_chf}
        return self._continue(past, simulated, x, moves, path, world_id, th,
                              "Coussin mis à l'épreuve, à la place de l'épargne simulée", "regle_coussin_mois")[0]

    def tipping_level(self, path: list[dict], gare_month: int, new_path: list[dict], world_id: str, door_key: str,
                      overrides: dict | None) -> float | None:
        """Le point de bascule en épargne : la plus petite épargne à la gare, à 100 CHF près, avec laquelle le trajet
        `new_path` tient la porte dans ce monde. Trouvé par dichotomie, en interrogeant le moteur avec une épargne
        constatée. None si aucune épargne ne suffit."""
        key = (*self._key(new_path, world_id, overrides), json.dumps(path, sort_keys=True), gare_month, door_key)
        if key not in self._tips:
            th = self.theta(overrides)

            def holds(x: float) -> bool:
                run = self.observed(path, gare_month, float(x), new_path, world_id, overrides, keep=False)[0]
                return doors_of(run, th, self.age0)[door_key]
            low, high = TIP_RANGE
            if not holds(high):
                self._tips[key] = None
            elif holds(low):
                self._tips[key] = float(low)
            else:
                while high - low > 100:
                    middle = (low + high) // 200 * 100
                    low, high = (low, middle) if holds(middle) else (middle, high)
                self._tips[key] = float(high)
        return self._tips[key]

    def zone(self, path: list[dict], gare_month: int, door_key: str, tested: tuple[str, ...], overrides: dict | None) -> dict | None:
        """La zone des seuils qui fonctionnent à une gare, pour une porte : au-dessus de l'épargne des mondes où le trajet
        la perd, sans dépasser celle des mondes où il la tient, et pas en dessous du point de bascule calculé par le moteur.
        Le seuil est pris au milieu de cette zone, pas au bord. None si aucun seuil ne sépare les mondes testés."""
        key = (json.dumps(path, sort_keys=True), gare_month, door_key, tested, json.dumps(overrides or {}, sort_keys=True))
        if key not in self._zones:
            th, read = self.theta(overrides), VARIABLES["liquidite_chf"][1]
            runs = {w: self.trip(path, w, overrides) for w in tested}
            level = {w: read(runs[w][1][gare_month]) for w in tested}
            keeps = {w: doors_of(runs[w][0], th, self.age0)[door_key] for w in tested}
            lost, held = [level[w] for w in tested if not keeps[w]], [level[w] for w in tested if keeps[w]]
            self._zones[key] = None
            if lost and held and max(lost) < min(held):
                low, high = max(lost), min(held)
                # Le bord bas : le point de bascule dans les mondes où le trajet tient la porte. En dessous, même eux la perdent.
                tips = [self.tipping_level(path, gare_month, path, w, door_key, overrides) for w in tested if keeps[w]]
                edge = max((t for t in tips if t is not None), default=None)
                edge = edge if edge is not None and edge <= high else None
                low = max(low, edge) if edge is not None else low
                threshold = round((low + high) / 2, -2)
                if max(lost) < threshold <= high:
                    self._zones[key] = {"low_chf": round(low, 2), "high_chf": round(high, 2), "tipping_chf": edge,
                                        "threshold_chf": threshold}
        return self._zones[key]

    def _obs(self, observation, path: list[dict]) -> tuple[int, float] | None:
        """Une épargne constatée, { gare_month, value_chf } : la gare où Alexia regarde ses comptes, et ce qu'elle y a de côté."""
        if observation is None:
            return None
        try:
            gare, value = int(observation["gare_month"]), float(observation["value_chf"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(say("Observed savings are described by a junction (gare_month) and an amount (value_chf).",
                                 "Une épargne constatée se décrit par une gare (gare_month) et un montant (value_chf).")) from error
        if not path or gare not in self.gares or not math.isfinite(value):
            raise ValueError(say(f"Observed savings are given at a junction of the route, after the departure. Junctions: {list(self.gares)}",
                                 f"Une épargne constatée se donne à une gare du trajet, après le départ. Gares : {list(self.gares)}"))
        return gare, value

    def lived(self, path: list[dict], world_id: str, overrides: dict | None,
              obs: tuple[int, float] | None) -> tuple[SimulationResult, dict[int, State]]:
        """Le trajet tel qu'il est vécu : simulé jusqu'à la gare de l'épargne constatée, puis continué depuis cette épargne.
        Sans épargne constatée, c'est le trajet simulé."""
        if obs is None:
            return self.trip(path, world_id, overrides)
        gare, value = obs
        result, later = self.observed(path, gare, value, path, world_id, overrides)
        simulated = self.trip(path, world_id, overrides)[1]
        states = {g: x for g, x in simulated.items() if g < gare}
        states[gare] = observe(simulated[gare], value)[0]
        states.update({g: x for g, x in later.items() if g > gare})
        return result, states

    def fork(self, path: list[dict], gare_month: int, new_path: list[dict], world_id: str, overrides: dict | None,
             obs: tuple[int, float] | None) -> SimulationResult:
        """Une branche qui quitte le trajet vécu à une gare. Avant la gare de l'épargne constatée, rien ne change ;
        à cette gare, la branche repart de l'épargne constatée ; après, de l'état du trajet vécu."""
        if new_path == path:
            return self.lived(path, world_id, overrides, obs)[0]
        if obs is None or gare_month < obs[0]:
            return self.branch(path, gare_month, new_path, world_id, overrides)
        if gare_month == obs[0]:
            return self.observed(path, gare_month, obs[1], new_path, world_id, overrides)[0]
        key = (*self._key(new_path, world_id, overrides), json.dumps(path, sort_keys=True), obs, gare_month)
        if key not in self._seen:
            th = self.theta(overrides)
            past, states = self.lived(path, world_id, overrides, obs)
            self._seen[key] = resume(self.sc.profile, past.months[:gare_month], states[gare_month],
                                     blocks_to_ops(new_path, th, self.h), self.h, th, self.world(th, world_id),
                                     "trajet", world_id), {}
        return self._seen[key][0]

    # ------------------------------------------------------------------ mises en forme
    def summary(self, r: SimulationResult, th: dict, detailed: bool) -> dict:
        states, margins = doors_of(r, th, self.age0), margins_of(r, th, self.age0)
        word = lambda ok: "ouverte" if ok else "fermee"
        if detailed:
            doors = {key: {"state": word(ok),
                           "value_chf": None if margins[key] is None else round(margins[key][0], 2),
                           "required_chf": None if margins[key] is None else round(margins[key][1], 2)}
                     for key, ok in states.items()}
        else:
            doors = {key: word(ok) for key, ok in states.items()}
        return {"doors": doors, "doors_open": sum(states.values()), "doors_total": len(states),
                "first_negative_month": r.first_negative_month,
                "financing_months": [m.month for m in r.months if "financement_necessaire" in m.flags],
                "peak_financing_chf": round(r.peak_financing_chf, 2), "net_worth_end_chf": round(r.net_worth_end_chf, 2)}

    def bands(self, runs: dict[str, SimulationResult], central: SimulationResult, prudent: SimulationResult, th: dict) -> dict:
        """Trois bandes pour un résultat, sans probabilité. « Pire monde testé » : le moins favorable des mondes testés,
        chiffre par chiffre, avec le monde d'où il vient (aucun, si tous les mondes donnent le même). « Central » : le monde
        de référence. « Prudent » : la référence avec un rendement des placements plus bas. Rien n'est promis par ces bandes."""
        seen = {w: self.summary(r, th, detailed=True) for w, r in runs.items()}

        def worst(read, pick) -> dict:
            values = {w: read(s) for w, s in seen.items()}
            at = pick(values, key=values.get)
            return {"value": values[at], "world_id": None if len(set(values.values())) == 1 else at}
        out = {"pire": {"doors_open": worst(lambda s: s["doors_open"], min),
                        "peak_financing_chf": worst(lambda s: s["peak_financing_chf"], max),
                        "net_worth_end_chf": worst(lambda s: s["net_worth_end_chf"], min)}}
        whole = {"central": self.summary(central, th, detailed=True), "prudent": self.summary(prudent, th, detailed=True)}
        for name, s in whole.items():
            out[name] = {k: {"value": s[k], "world_id": "reference" if name == "central" else "prudent"}
                         for k in ("doors_open", "peak_financing_chf", "net_worth_end_chf")}
        doors = {}
        for door in DOORS:
            states = {w: s["doors"][door.key] for w, s in seen.items()}
            closed = [w for w, d in states.items() if d["state"] == "fermee"]
            if all(d["value_chf"] is not None for d in states.values()):
                at = min(states, key=lambda w: states[w]["value_chf"])
                low = {**states[at], "world_id": None if len({d["value_chf"] for d in states.values()}) == 1 else at}
            else:
                at = closed[0] if closed else next(iter(states))
                low = {**states[at], "world_id": at if closed and len(closed) < len(states) else None}
            doors[door.key] = {"pire": low, "central": whole["central"]["doors"][door.key], "prudent": whole["prudent"]["doors"][door.key]}
        out["doors"] = doors
        out["doors_total"] = len(DOORS)
        out["prudent_points"] = round(th["prudent_ecart_rendement"] * 100, 2)
        return out

    def doors(self, th: dict) -> list[dict]:
        out, assumptions = [], by_key()
        for door in DOORS:
            age = door_age(door, th, self.age0, self.h)
            origin = assumptions.get(door.source_key) if door.source_key else None
            out.append({"key": door.key, "name": door_name(door), "rule": rule_text(door, th),
                        "age": None if age is None else self.age(round((age - self.age0) * 12)),
                        "month": None if age is None else round((age - self.age0) * 12), "whole_trip": age is None,
                        "kind": origin.kind if origin else "regle",
                        "source": origin.source if origin else say(english.DOOR_ORIGIN, "Règle du moteur (engine/explore.py)")})
        return out

    @staticmethod
    def _state(x: State) -> dict:
        return {"cash_chf": round(cash_chf(x), 2), "placements_chf": round(x.placements_chf, 2),
                "debt_chf": round(debt_chf(x), 2), "net_worth_chf": round(net_worth_chf(x), 2),
                "liquidite_chf": round(VARIABLES["liquidite_chf"][1](x), 2), "status": x.status, "location": x.location}

    # ------------------------------------------------------------------ /path
    def path_view(self, path: list[dict], world_id: str = "reference", overrides: dict | None = None, mondes=None,
                  observation: dict | None = None) -> dict:
        path, th, tested = normalize(path, self.h), self.theta(overrides), self.asked(mondes, overrides)
        world_id = W.canonical(world_id, th, self.h, self.age0)
        obs = self._obs(observation, path)
        shown = self.lived(path, world_id, overrides, obs)[0]
        return {"world_id": world_id, "path": path, "legs": legs_of(path, th, self.h), "doors": self.doors(th),
                "by_world": {w: self.summary(self.lived(path, w, overrides, obs)[0], th, detailed=True) for w in tested},
                "bands": self.bands({w: self.lived(path, w, overrides, obs)[0] for w in tested},
                                    self.lived(path, "reference", overrides, obs)[0], self.lived(path, "prudent", overrides, obs)[0], th),
                "observation": self._observation(path, obs, overrides, mondes, tested),
                "months": i18n.months(asdict(shown)["months"])}

    # ------------------------------------------------------------------ /node
    def _branches(self, path: list[dict], gare_month: int, overrides: dict | None, tested: tuple[str, ...],
                  obs: tuple[int, float] | None = None) -> list[dict]:
        """Les branches d'une gare, chacune avec ses tronçons et ce qu'elle donne dans chaque monde testé.
        Avec une épargne constatée (`obs`), les branches quittent le trajet vécu, pas le trajet simulé."""
        th, out = self.theta(overrides), []
        run = lambda branch_path, w: self.fork(path, gare_month, branch_path, w, overrides, obs)
        for b in destinations(path, gare_month, self.h, self.age0):
            branch = {"id": b["id"], "label": b["label"], "available": b["available"], "reason": b["reason"],
                      "on_path": b["on_path"], "path": b["path"]}
            if b["available"]:
                branch["legs"] = legs_of(b["path"], th, self.h, gare_month)
                branch["by_world"] = {w: self.summary(run(b["path"], w), th, detailed=False) for w in tested}
            out.append(branch)
        return out

    def node_view(self, path: list[dict], gare_month: int = 0, overrides: dict | None = None, mondes=None,
                  observation: dict | None = None) -> dict:
        """`observation` : ce qu'Alexia a vraiment de côté à une gare, { gare_month, value_chf }. À cette gare, les branches
        repartent de cette valeur ; aux gares suivantes, du trajet vécu depuis."""
        path = normalize(path, self.h) if path else []
        th, tested = self.theta(overrides), self.asked(mondes, overrides)
        obs = self._obs(observation, path)
        branches = self._branches(path, gare_month, overrides, tested, obs)
        open_branches = [b for b in branches if b["available"]]
        first = tested[0]

        def score(b):
            s = b["by_world"][first]
            return s["doors_open"], -s["peak_financing_chf"], s["net_worth_end_chf"]
        for b in open_branches:
            # Non dominée : aucune autre branche ne fait au moins aussi bien sur les trois critères, et mieux sur l'un.
            b["non_dominated"] = not any(all(x >= y for x, y in zip(score(o), score(b))) and score(o) != score(b)
                                         for o in open_branches if o is not b)

        # L'état à la gare, dans chaque monde. `avant_le_choc` : la crise de ce monde n'a pas encore commencé à cet âge
        # (None pour le monde de référence). Après le choc, l'état de la gare porte déjà sa trace.
        # Un monde combiné a deux crises : `avant_le_choc` dit qu'aucune n'a commencé, et `crises` dit où en est chacune
        # (à venir, en cours, passée). L'état d'une gare est celui du début du mois : une crise qui commence ce mois-là est à venir.
        if path and gare_month:
            state = {w: self._state(self.lived(path, w, overrides, obs)[1][gare_month]) for w in tested}
        else:
            state = {w: self._state(initial_state(self.sc.profile, th)) for w in tested}
        for w in tested:
            start = W.shock_start(th, w, self.h, self.age0)
            state[w]["avant_le_choc"] = None if start is None else gare_month <= start
            state[w]["choc_month"], state[w]["choc_age"] = start, None if start is None else self.age(start)
            if W.combined(w):
                state[w]["crises"] = [{**crisis, "status": "a_venir" if gare_month <= crisis["from_month"]
                                       else "en_cours" if gare_month < crisis["to_month"] else "passee"}
                                      for crisis in W.crises(th, w, self.h, self.age0)]

        # Flexibilité : une des branches d'ici, ou le trajet suivi avec un seul changement à une gare suivante.
        reachable = [b["by_world"] for b in open_branches]
        if path:
            for later in (g for g in self.gares if g > gare_month):
                reachable += [b["by_world"] for b in self._branches(path, later, overrides, tested, obs)
                              if b["available"] and not b["on_path"]]
        by_door = {}
        for door in DOORS:
            open_in = [w for w in tested if any(trip[w]["doors"][door.key] == "ouverte" for trip in reachable)]
            by_door[door.key] = {"possible": bool(open_in), "robust": len(open_in) == len(tested), "worlds_open": open_in}

        staying = next((b for b in open_branches if b["on_path"]), None)
        best = []
        for w in tested:
            top = max(open_branches, key=lambda b: (b["by_world"][w]["doors_open"], b["on_path"]))
            more = None if staying is None else top["by_world"][w]["doors_open"] - staying["by_world"][w]["doors_open"]
            best.append({"world_id": w, "branch_id": top["id"], "doors_open": top["by_world"][w]["doors_open"],
                         "doors_more_than_staying": more})
        return {"gare_month": gare_month, "age": self.age(gare_month), "worlds": list(tested), "state_by_world": state,
                "observation": self._observation(path, obs, overrides, mondes, tested),
                "branches": branches,
                "flexibility": {"horizon": horizon_text(), "doors_total": len(DOORS),
                                "robust": [k for k, d in by_door.items() if d["robust"]],
                                "possible": [k for k, d in by_door.items() if d["possible"] and not d["robust"]],
                                "by_door": by_door},
                "best_by_world": best, "matters": self._matters(open_branches, tested)}

    def _observation(self, path, obs, overrides, mondes, tested) -> dict | None:
        """Ce que le moteur simulait à la gare, ce qu'Alexia y constate, et de quel côté de chaque seuil elle se trouve.
        Les seuils sont ceux du trajet simulé : c'est à eux que la valeur constatée se compare."""
        if obs is None:
            return None
        gare_month, observed_chf = obs
        read = VARIABLES["liquidite_chf"][1]
        signals, done = [], set()
        doors = {d["key"]: d["name"] for d in self.doors(self.theta(overrides))}
        for world in self.pathways_view(path, 0, overrides, mondes)["by_world"].values():
            for row in world["doors"]:
                sign = row["signpost"]
                if sign and sign["gare_month"] == gare_month and row["key"] not in done:
                    done.add(row["key"])
                    below = observed_chf < sign["threshold_chf"]
                    limit, name, age = _chf(sign["threshold_chf"]), doors[row["key"]], self.age(gare_month)
                    if below:
                        text = say(f"With {_chf(observed_chf)} set aside at {age}, you are below the threshold of {limit}: "
                                   f"that is the side where this route no longer holds “{name}”.",
                                   f"Avec {_chf(observed_chf)} de côté à {age} ans, tu es sous le seuil de {limit} : "
                                   f"c'est le côté où ce trajet ne tient plus « {name} ».")
                    else:
                        text = say(f"With {_chf(observed_chf)} set aside at {age}, you are above the threshold of {limit}: "
                                   f"that is the side where this route holds “{name}”.",
                                   f"Avec {_chf(observed_chf)} de côté à {age} ans, tu es au-dessus du seuil de {limit} : "
                                   f"c'est le côté où ce trajet tient « {name} ».")
                    signals.append({"door": row["key"], "threshold_chf": sign["threshold_chf"], "side": "sous" if below else "au_dessus",
                                    "text": text})
        return {"gare_month": gare_month, "age": self.age(gare_month), "value_chf": observed_chf, "signals": signals,
                "simulated_chf": {w: round(read(self.trip(path, w, overrides)[1][gare_month]), 2) for w in tested}}

    @staticmethod
    def _matters(branches: list[dict], tested: tuple[str, ...]) -> bool:
        """Une gare compte si deux de ses branches ne donnent pas les mêmes portes, dans au moins un monde."""
        return any(b["by_world"][w]["doors"] != branches[0]["by_world"][w]["doors"] for b in branches for w in tested)

    # ------------------------------------------------------------------ /pathways
    def pathways_view(self, path: list[dict], gare_month: int = 0, overrides: dict | None = None, mondes=None,
                      observation: dict | None = None) -> dict:
        path, th, tested = normalize(path, self.h), self.theta(overrides), self.asked(mondes, overrides)
        obs = self._obs(observation, path)
        doors = self.doors(th)
        staying = {w: self.summary(self.lived(path, w, overrides, obs)[0], th, detailed=False) for w in tested}
        stops = [g for g in (0,) + self.gares if g >= gare_month]
        branches_at = {g: [b for b in self._branches(path, g, overrides, tested, obs) if b["available"]] for g in stops}

        by_world = {}
        for w in tested:
            rows = []
            for door in doors:
                holds = staying[w]["doors"][door["key"]] == "ouverte"
                row = {"key": door["key"], "holds": holds, "tipping": None, "no_return": None, "last_transfer": None, "signpost": None}
                if not holds:
                    # Point de bascule : le moment où le trajet cesse de tenir la porte, si l'on reste dessus.
                    tipping = staying[w]["first_negative_month"] if door["whole_trip"] else door["month"]
                    row["tipping"] = {"month": tipping, "age": self.age(tipping)}
                    # Dernière correspondance utile : la gare la plus tardive, avant, où une branche garde la porte ouverte.
                    for g in sorted((g for g in stops if g < max(tipping, 1)), reverse=True):
                        saving = next((b for b in branches_at[g] if not b["on_path"]
                                       and b["by_world"][w]["doors"][door["key"]] == "ouverte"), None)
                        if saving:
                            row["last_transfer"] = {"gare_month": g, "age": self.age(g), "branch_id": saving["id"], "label": saving["label"]}
                            break
                    # Point de non-retour : la première gare à partir de laquelle plus aucune branche ne l'ouvre.
                    after = row["last_transfer"]["gare_month"] + 12 if row["last_transfer"] else gare_month
                    row["no_return"] = {"gare_month": after, "age": self.age(after)}
                    row["signpost"] = self._signpost(path, door, row["last_transfer"], staying, overrides, tested, obs)
                rows.append(row)
            by_world[w] = {"doors": rows}

        gares = [{"gare_month": g, "age": self.age(g), "branches": len(branches_at[g]),
                  "matters": self._matters(branches_at[g], tested)} for g in stops]
        return {"gare_month": gare_month, "worlds": list(tested), "by_world": by_world, "gares": gares,
                "observation": self._observation(path, obs, overrides, mondes, tested)}

    def _signpost(self, path, door, last_transfer, staying, overrides, tested, obs=None) -> dict | None:
        """Le signal à surveiller : à la dernière correspondance utile, le niveau de liquidité (cash + placements − dettes)
        qui sépare les mondes où le trajet tient la porte de ceux où il la perd. Sans seuil net : pas de signal."""
        if not last_transfer or last_transfer["gare_month"] == 0:
            return None
        g = last_transfer["gare_month"]
        read = VARIABLES["liquidite_chf"][1]
        level = {w: read(self.lived(path, w, overrides, obs)[1][g]) for w in tested}
        lost = [level[w] for w in tested if staying[w]["doors"][door["key"]] == "fermee"]
        held = [level[w] for w in tested if staying[w]["doors"][door["key"]] == "ouverte"]
        if not lost or not held or max(lost) >= min(held):
            return None
        if obs is None:
            # Le seuil est au milieu de la zone qui fonctionne, dont le bord bas est le point de bascule calculé par le moteur.
            zone = self.zone(path, g, door["key"], tested, overrides)
            if zone is None:
                return None
            threshold = zone["threshold_chf"]
        else:
            threshold = round((max(lost) + min(held)) / 2, -2)
            if not max(lost) < threshold <= min(held):
                return None
        if threshold >= 0:
            text = say(f"If you have less than {_chf(threshold)} set aside (cash + investments − debts) at {self.age(g)}, "
                       f"this route no longer holds “{door['name']}”.",
                       f"Si tu as moins de {_chf(threshold)} de côté (cash + placements − dettes) à {self.age(g)} ans, "
                       f"ce trajet ne tient plus « {door['name']} ».")
        else:
            text = say(f"If your debts exceed your cash and investments by more than {_chf(-threshold)} at {self.age(g)}, "
                       f"this route no longer holds “{door['name']}”.",
                       f"Si tes dettes dépassent ton cash et tes placements de plus de {_chf(-threshold)} à {self.age(g)} ans, "
                       f"ce trajet ne tient plus « {door['name']} ».")
        return {"variable": "liquidite_chf", "threshold_chf": threshold, "direction": "sous", "gare_month": g, "text": text}

    # ------------------------------------------------------------------ /adaptive
    def default_rule(self, path: list[dict], overrides: dict | None = None, mondes=None) -> tuple[Rule, str] | None:
        """La règle par défaut d'un trajet : son premier signal à surveiller, et la branche de sa dernière correspondance utile.
        Rend aussi la porte que ce signal annonce. None si le trajet n'a aucun signal."""
        for world in self.pathways_view(path, 0, overrides, mondes)["by_world"].values():
            for row in world["doors"]:
                if row["signpost"]:
                    sign = row["signpost"]
                    return Rule(sign["gare_month"], sign["variable"], sign["threshold_chf"], row["last_transfer"]["branch_id"]), row["key"]
        return None

    def adaptive_view(self, path: list[dict], rule: dict | None = None, door: str | None = None,
                      overrides: dict | None = None, mondes=None, observation: dict | None = None) -> dict:
        """Plan figé contre plan adaptatif. Le plan figé suit le trajet sans changement ; le plan adaptatif applique la règle :
        arrivé à la gare, il lit l'état, et prend la branche si la grandeur est sous le seuil. Un résultat par monde testé."""
        path, th, tested = normalize(path, self.h), self.theta(overrides), self.asked(mondes, overrides)
        if rule is None:
            found = self.default_rule(path, overrides, mondes)
            if found is None:
                raise ValueError(say("This route has no signpost: there is no default rule. Give a rule "
                                     "(gare_month, variable, threshold_chf, branch_id).",
                                     "Ce trajet n'a pas de signal à surveiller : il n'y a pas de règle par défaut. Donne une règle "
                                     "(gare_month, variable, threshold_chf, branch_id)."))
            the_rule, door = found[0], door or found[1]
        else:
            try:
                the_rule = Rule(int(rule["gare_month"]), str(rule["variable"]), float(rule["threshold_chf"]), str(rule["branch_id"]))
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(say("A rule is described by a junction (gare_month), a quantity (variable), a threshold (threshold_chf) "
                                     "and a branch (branch_id).",
                                     "Une règle se décrit par une gare (gare_month), une grandeur (variable), un seuil (threshold_chf) "
                                     "et une branche (branch_id).")) from error
        if the_rule.variable not in VARIABLES:
            raise ValueError(say(f"Unknown quantity “{the_rule.variable}”. Quantities: {sorted(VARIABLES)}",
                                 f"Grandeur inconnue « {the_rule.variable} ». Grandeurs : {sorted(VARIABLES)}"))
        if the_rule.gare_month not in self.gares:
            raise ValueError(say(f"No junction at month {the_rule.gare_month}. Junctions: {list(self.gares)}",
                                 f"Pas de gare au mois {the_rule.gare_month}. Gares : {list(self.gares)}"))
        if door is not None and door not in {d.key for d in DOORS}:
            raise ValueError(say(f"Unknown station “{door}”. Stations: {[d.key for d in DOORS]}",
                                 f"Porte inconnue « {door} ». Portes : {[d.key for d in DOORS]}"))
        choices = destinations(path, the_rule.gare_month, self.h, self.age0)
        branch = next((b for b in choices if b["id"] == the_rule.branch_id and b["available"] and not b["on_path"]), None)
        if branch is None:
            open_ids = [b["id"] for b in choices if b["available"] and not b["on_path"]]
            raise ValueError(say(f"At this junction, the branch “{the_rule.branch_id}” does not exist or is not open. Branches: {open_ids}",
                                 f"À cette gare, la branche « {the_rule.branch_id} » n'existe pas ou n'est pas ouverte. Branches : {open_ids}"))
        read = VARIABLES[the_rule.variable][1]
        # Le jumeau qui apprend : les deux plans suivent le trajet vécu, et la règle lit l'épargne constatée.
        # Une épargne constatée après la gare de la règle arrive trop tard pour elle : la règle garde l'état simulé.
        obs = self._obs(observation, path)
        if obs is not None and obs[0] > the_rule.gare_month:
            obs = None

        by_world = {}
        for w in tested:
            fixed_run, states = self.lived(path, w, overrides, obs)
            x = states[the_rule.gare_month]
            applies = the_rule.applies(x)                      # la décision ne regarde que l'état à la gare
            adaptive_run = self.fork(path, the_rule.gare_month, branch["path"], w, overrides, obs) if applies else fixed_run
            fixed, adaptive = self.summary(fixed_run, th, detailed=False), self.summary(adaptive_run, th, detailed=False)
            keys = list(fixed["doors"])
            by_world[w] = {
                "fixed": fixed,
                "adaptive": {**adaptive, "applies": applies, "observed_chf": round(read(x), 2),
                             "path": branch["path"] if applies else path},
                "saved": {"doors_reopened": [k for k in keys if fixed["doors"][k] == "fermee" and adaptive["doors"][k] == "ouverte"],
                          "doors_lost": [k for k in keys if fixed["doors"][k] == "ouverte" and adaptive["doors"][k] == "fermee"],
                          "financing_avoided_chf": round(fixed["peak_financing_chf"] - adaptive["peak_financing_chf"], 2),
                          "net_worth_difference_chf": round(adaptive["net_worth_end_chf"] - fixed["net_worth_end_chf"], 2)}}

        kept = {d.key: {"fixed": sum(by_world[w]["fixed"]["doors"][d.key] == "ouverte" for w in tested),
                        "adaptive": sum(by_world[w]["adaptive"]["doors"][d.key] == "ouverte" for w in tested)} for d in DOORS}
        age = self.age(the_rule.gare_month)
        label, taken = variable_label(the_rule.variable), branch["label"][0].lower() + branch["label"][1:]
        return {"path": path,
                "rule": {"gare_month": the_rule.gare_month, "age": age, "variable": the_rule.variable, "variable_label": label,
                         "threshold_chf": the_rule.threshold_chf, "branch_id": branch["id"], "branch_label": branch["label"],
                         "text": say(f"At {age}, if you have less than {_chf(the_rule.threshold_chf)} {label}: {taken}.",
                                     f"À {age} ans, si tu as moins de {_chf(the_rule.threshold_chf)} {label} : {taken}.")},
                "target_door": door, "worlds": list(tested), "by_world": by_world,
                "observation": None if obs is None else {"gare_month": obs[0], "age": self.age(obs[0]), "value_chf": obs[1]},
                "summary": {"worlds": len(tested), "doors_kept": kept,
                            "applies_in": [w for w in tested if by_world[w]["adaptive"]["applies"]]}}
