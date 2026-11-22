"""Des politiques, pas des plans : le tableau de valeur.

Cadre : décision en incertitude profonde (Robust Decision Making, chemins d'adaptation, modélisation exploratoire).
Une règle à seuil est une politique au sens d'un processus de décision markovien, a(t) = π(x(t)) : arrivée à sa
date, elle lit l'état présent (ce qu'Alexia a de côté) et décide. Elle ne lit jamais la suite : c'est la
non-anticipativité, et c'est ce qui la sépare de la référence clairvoyante.

- Une politique : une date, une grandeur, un seuil, une branche (engine/tree.py, Rule). La date et la branche sont
  des données ; le seuil est calculé ici, jamais écrit.
- La référence clairvoyante d'un monde : parmi le plan et les branches des politiques, le trajet qui tient le mieux
  l'objectif visé quand on connaît le monde à l'avance. Personne ne le connaît : ce n'est jamais une recommandation.
- Le regret d'un trajet dans un monde, « le prix de ne pas savoir » : ce qui manque pour l'objectif visé, alors que
  la référence clairvoyante l'aurait eu. Nul quand l'objectif tient. C'est une lecture « satisfaire l'objectif ».
- Le choix du seuil, dans l'ordre : le plus de mondes où l'objectif tient ; le plus petit regret dans le pire monde,
  puis dans le suivant ; à égalité, la règle qui quitte le plan dans le moins de mondes. Le seuil est pris au milieu
  de la zone qui fonctionne, dont le bord bas est le point de bascule en épargne calculé par le moteur.
- Contre le surapprentissage : un seul seuil par règle, un monde laissé de côté, des variantes des mondes (âge et
  gravité décalés) comme ensemble de test, puis des variantes tirées au hasard, pour les politiques seulement.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, replace
from fractions import Fraction

from engine import i18n
from engine import worlds as W
from engine.blocks import MASTER_YEARS, PART_TIME_YEARS, destinations, normalize
from engine.explore import doors_of, margins_of
from engine.i18n import say
from engine.tree import VARIABLES, Tree, _chf, variable_label


@dataclass(frozen=True)
class Policy:
    """Une politique nommée : sa date et sa branche. Son seuil se calcule (Analysis.calibrate)."""
    id: str
    name: str
    gare_month: int
    branch_id: str


POLICIES: tuple[Policy, ...] = (
    Policy("securite", "Sécurité", 60, "emploi"),
    Policy("equilibre", "Équilibre", 72, "emploi"),
    Policy("ambition", "Ambition", 72, "master_en_travaillant"),
)
NAMES_EN = {"securite": "Safety", "equilibre": "Balance", "ambition": "Ambition"}
FIXED = "fige"                               # le plan figé : le trajet suivi sans rien changer
TARGET = "reconversion"                      # l'objectif visé : celui d'Alexia dans Data/synthetic-goals.csv
TABLE_WORLDS = ("reference", "krach@24", "chomage_6_mois@24", "chomage_long")
HIGHLIGHT = "chomage_long"                   # la colonne mise en avant : le choc long
VARIABLE = "liquidite_chf"
SEED, DRAWS, DRAW_GRAVITY = 2026, 200, (50, 150)


def policy_name(policy: Policy) -> str:
    """Le nom d'une politique, dans la langue courante."""
    return say(NAMES_EN[policy.id], policy.name)


def master_fate(path: list[dict], age0: int) -> dict:
    """Ce que devient le master sur un trajet, lu dans ses blocs : terminé, terminé en travaillant, arrêté, pas commencé."""
    progress, month, part_time, end = Fraction(0), 0, False, None
    for block in path:
        if block["block"] in ("master", "master_part_time"):
            years = MASTER_YEARS if block["block"] == "master" else PART_TIME_YEARS
            progress += Fraction(block["years"], years)
            part_time = part_time or block["block"] == "master_part_time"
            end = month + 12 * block["years"]
        month += 12 * block["years"]
    if end is None:
        return {"state": "pas_commence", "age": None}
    age = age0 + end // 12
    if progress >= 1:
        return {"state": "termine_en_travaillant" if part_time else "termine", "age": age}
    return {"state": "arrete", "age": age}


class Analysis:
    """Les politiques d'un trajet : leurs branches, leurs seuils, ce qu'elles donnent dans chaque monde."""

    def __init__(self, tree: Tree, path: list[dict], overrides: dict | None = None, target: str = TARGET,
                 policies: tuple[Policy, ...] = POLICIES):
        self.t, self.overrides, self.target, self.policies = tree, overrides, target, policies
        self.path = normalize(path, tree.h)
        self.th = tree.theta(overrides)
        self.read = VARIABLES[VARIABLE][1]
        self.branch = {p.id: self._branch(p) for p in policies}

    def _branch(self, policy: Policy) -> dict:
        if policy.gare_month not in self.t.gares:
            raise ValueError(say(f"No junction at month {policy.gare_month}. Junctions: {list(self.t.gares)}",
                                 f"Pas de gare au mois {policy.gare_month}. Gares : {list(self.t.gares)}"))
        choices = destinations(self.path, policy.gare_month, self.t.h, self.t.age0)
        found = next((b for b in choices if b["id"] == policy.branch_id and b["available"] and not b["on_path"]), None)
        if found is None:
            raise ValueError(say(f"The “{policy_name(policy)}” policy takes the branch “{policy.branch_id}” at "
                                 f"{self.t.age(policy.gare_month)}: this route does not offer it at that junction.",
                                 f"La politique « {policy.name} » prend la branche « {policy.branch_id} » à "
                                 f"{self.t.age(policy.gare_month)} ans : ce trajet ne la propose pas à cette gare."))
        return found

    # ------------------------------------------------------------------ un trajet dans un monde
    def run(self, option: str, world_id: str):
        """Le plan (FIXED), ou le plan quitté par la branche d'une politique à sa date."""
        if option == FIXED:
            return self.t.trip(self.path, world_id, self.overrides)[0]
        policy = next(p for p in self.policies if p.id == option)
        return self.t.fork(self.path, policy.gare_month, self.branch[option]["path"], world_id, self.overrides, None)

    def level(self, policy: Policy, world_id: str) -> float:
        """L'état que la politique lit à sa date : ce qu'Alexia a de côté. Rien d'autre, et rien de la suite."""
        return self.read(self.t.trip(self.path, world_id, self.overrides)[1][policy.gare_month])

    def decide(self, policy: Policy, threshold: float | None, world_id: str) -> tuple[bool, str]:
        """a = π(x) : la branche si l'épargne lue est sous le seuil, sinon le plan."""
        applies = threshold is not None and self.level(policy, world_id) < threshold
        return applies, policy.id if applies else FIXED

    def follow(self, policy: Policy | None, threshold: float | None, world_id: str):
        """Le trajet que donne une ligne du tableau dans un monde : le plan, ou la politique qui décide à sa date."""
        return self.run(FIXED if policy is None else self.decide(policy, threshold, world_id)[1], world_id)

    def bands(self, policy: Policy | None, threshold: float | None, worlds: tuple[str, ...]) -> dict:
        """Les trois bandes d'une ligne : pire monde testé parmi les colonnes, central, prudent."""
        return self.t.bands({w: self.follow(policy, threshold, w) for w in worlds}, self.follow(policy, threshold, "reference"),
                            self.follow(policy, threshold, "prudent"), self.th)

    def holds(self, run) -> bool:
        return doors_of(run, self.th, self.t.age0)[self.target]

    def value(self, run) -> tuple[float, float]:
        """Ce que le trajet atteint pour l'objectif visé, et ce que l'objectif demande."""
        return margins_of(run, self.th, self.t.age0)[self.target]

    def _reached(self, run) -> float:
        value, required = self.value(run)
        return min(value, required)

    def clairvoyant(self, world_id: str) -> str:
        """La référence clairvoyante : l'option qui tient le mieux l'objectif visé, le monde étant connu à l'avance.
        À égalité : le plan, puis la branche prise le plus tard. Ce n'est pas une action possible."""
        options = [FIXED] + [p.id for p in sorted(self.policies, key=lambda p: -p.gare_month)]
        best = max(self._reached(self.run(o, world_id)) for o in options)
        return next(o for o in options if self._reached(self.run(o, world_id)) >= best - 1e-9)

    def regret(self, run, world_id: str) -> float:
        """Le prix de ne pas savoir : ce qui manque pour l'objectif visé, alors que la référence clairvoyante l'aurait eu."""
        return round(max(0.0, self._reached(self.run(self.clairvoyant(world_id), world_id)) - self._reached(run)), 2)

    # ------------------------------------------------------------------ le choix du seuil
    def calibrate(self, policy: Policy, worlds: tuple[str, ...]) -> dict:
        """Le seuil d'une politique, choisi sur les mondes donnés. Un seul seuil : il ne peut que couper la liste des
        mondes rangés par épargne. On essaie chaque coupure, on garde la zone qui gagne, on prend son milieu."""
        level = {w: self.level(policy, w) for w in worlds}
        cuts: list[float | None] = [None] + sorted(set(level.values()))        # None : la règle ne s'applique jamais

        def score(cut: float | None):
            applied = [w for w in worlds if cut is not None and level[w] <= cut]
            runs = {w: self.run(policy.id if w in applied else FIXED, w) for w in worlds}
            kept = sum(self.holds(runs[w]) for w in worlds)
            regrets = sorted((self.regret(runs[w], w) for w in worlds), reverse=True)
            return (kept, tuple(-r for r in regrets), -len(applied)), applied, kept, regrets
        best = max(cuts, key=lambda cut: score(cut)[0])
        _, applied, kept, regrets = score(best)
        answer = {"worlds": list(worlds), "levels_chf": {w: round(level[w], 2) for w in worlds}, "applies_in": applied,
                  "kept": kept, "worst_regret_chf": regrets[0], "threshold_chf": None, "zone": None}
        if best is None:
            return answer
        above = [value for value in level.values() if value > best]
        # Le point de bascule en épargne : dans les mondes où rester sur le plan tient l'objectif (en dessous, même eux
        # le perdent) ; si la règle s'applique partout, dans le plus exigeant des mondes testés.
        staying = [w for w in worlds if w not in applied and self.holds(self.run(FIXED, w))] or list(worlds)
        tips = [self.t.tipping_level(self.path, policy.gare_month, self.path, w, self.target, self.overrides) for w in staying]
        edge = max((t for t in tips if t is not None), default=None)
        if above:
            high = min(above)
            low = max(best, edge) if edge is not None and edge <= high else best
            threshold = min(max(round((low + high) / 2, -2), math.floor(best / 100) * 100 + 100), math.floor(high / 100) * 100)
        else:
            # Toutes les épargnes testées sont sous le seuil : la zone n'a pas de bord haut, on prend son bord bas.
            high, low = None, max(best, edge) if edge is not None else best
            threshold = math.floor(low / 100) * 100 + (0 if low > best and low % 100 == 0 else 100)
        answer["threshold_chf"] = float(threshold)
        answer["zone"] = {"low_chf": round(low, 2), "high_chf": None if high is None else round(high, 2), "tipping_chf": edge}
        return answer

    # ------------------------------------------------------------------ une case du tableau
    def cell(self, policy: Policy | None, threshold: float | None, world_id: str) -> dict:
        applies, option = (False, FIXED) if policy is None else self.decide(policy, threshold, world_id)
        run = self.run(option, world_id)
        value, required = self.value(run)
        path = self.path if option == FIXED else self.branch[option]["path"]
        return {**self.t.summary(run, self.th, detailed=False), "applies": applies, "option": option,
                "observed_chf": None if policy is None else round(self.level(policy, world_id), 2),
                "master": master_fate(path, self.t.age0), "target_holds": self.holds(run),
                "target_value_chf": round(value, 2), "target_required_chf": round(required, 2),
                "regret_chf": self.regret(run, world_id), "path": path}

    def rule(self, policy: Policy, threshold: float | None) -> dict:
        age, label, branch = self.t.age(policy.gare_month), variable_label(VARIABLE), self.branch[policy.id]
        taken = branch["label"][0].lower() + branch["label"][1:]
        text = (say(f"At {age}, if you have less than {_chf(threshold)} {label}: {taken}.",
                    f"À {age} ans, si tu as moins de {_chf(threshold)} {label} : {taken}.")
                if threshold is not None else
                say(f"At {age}: no threshold serves the goal in the tested worlds.",
                    f"À {age} ans : aucun seuil ne sert l'objectif dans les mondes testés."))
        return {"gare_month": policy.gare_month, "age": age, "variable": VARIABLE, "variable_label": label,
                "threshold_chf": threshold, "branch_id": policy.branch_id, "branch_label": branch["label"], "text": text}


def _scratch(tree: Tree, path: list[dict], overrides: dict | None) -> Analysis:
    """Un arbre jetable, pour tester un monde de plus sans garder sa vie mois par mois en mémoire."""
    return Analysis(Tree(tree.sc), path, overrides)


def validate(tree: Tree, path: list[dict], overrides: dict | None, worlds: tuple[str, ...], thresholds: dict[str, float | None]) -> dict:
    """Contre le surapprentissage : un monde laissé de côté, des variantes des mondes, puis des variantes tirées au hasard."""
    main, th, age0, h = Analysis(tree, path, overrides), tree.theta(overrides), tree.age0, tree.h
    left_out = {}
    for policy in POLICIES:
        rows = []
        for out in worlds:
            found = main.calibrate(policy, tuple(w for w in worlds if w != out))["threshold_chf"]
            applies, option = main.decide(policy, found, out)
            run = main.run(option, out)
            rows.append({"world_id": out, "threshold_chf": found, "applies": applies, "target_holds": main.holds(run),
                         "regret_chf": main.regret(run, out)})
        left_out[policy.id] = rows

    # Les variantes : chaque crise du tableau un an plus tôt, un an plus tard, moins forte, plus forte ; et le choc long
    # après la dernière date de décision, que nulle règle sur l'épargne ne peut voir venir.
    low, high = W.ages(h, age0)
    ids: list[str] = []
    for world in worlds:
        kind = W.named(world).id
        age = W.split(world)[1] or W.default_age(th, kind, h, age0)
        if age is None:
            continue
        for candidate in ([f"{kind}@{a}" for a in (age - 1, age + 1) if low <= a <= high]
                          + [f"{kind}@{age}~{g}" for g in (67, 133)] + ([f"{kind}@{high - 2}"] if kind == HIGHLIGHT else [])):
            variant = W.canonical(candidate, th, h, age0)
            if variant not in ids and variant not in worlds:
                ids.append(variant)
    variants = []
    for variant in ids:
        a = _scratch(tree, path, overrides)
        cells = {FIXED: a.cell(None, None, variant), **{p.id: a.cell(p, thresholds[p.id], variant) for p in POLICIES}}
        keep = ("doors_open", "doors_total", "peak_financing_chf", "applies", "target_holds", "regret_chf", "master")
        variants.append({"world": W.describe(th, h, age0, [variant])[0], "clairvoyant": a.clairvoyant(variant),
                         "cells": {row: {k: c[k] for k in keep} for row, c in cells.items()}})

    # Les variantes tirées au hasard : pour les politiques seulement, jamais pour le plan figé. Graine fixe.
    draw = random.Random(SEED)
    kinds = [W.named(w).id for w in worlds if W.default_age(th, W.named(w).id, h, age0) is not None]
    kept, applied, reachable = {p.id: 0 for p in POLICIES}, {p.id: 0 for p in POLICIES}, 0
    for _ in range(DRAWS):
        variant = W.canonical(f"{draw.choice(kinds)}@{draw.randint(low, high)}~{draw.randint(*DRAW_GRAVITY)}", th, h, age0)
        a = _scratch(tree, path, overrides)
        reachable += a.holds(a.run(a.clairvoyant(variant), variant))
        for policy in POLICIES:
            applies, option = a.decide(policy, thresholds[policy.id], variant)
            kept[policy.id] += a.holds(a.run(option, variant))
            applied[policy.id] += applies
    drawn = {"seed": SEED, "draws": DRAWS, "types": kinds, "ages": [low, high], "gravity": list(DRAW_GRAVITY),
             "kept": kept, "applied": applied, "clairvoyant_kept": reachable}
    return {"leave_one_out": left_out, "variants": variants, "random": drawn}


def _case(a: Analysis, thresholds: dict[str, float | None], worlds: tuple[str, ...]) -> dict:
    """Le tableau d'une Alexia : ses cases, sa référence clairvoyante, ses bandes, et l'écart entre chaque politique et le plan figé."""
    cells = {FIXED: {w: a.cell(None, None, w) for w in worlds},
             **{p.id: {w: a.cell(p, thresholds[p.id], w) for w in worlds} for p in POLICIES}}
    seer = {}
    for w in worlds:
        option = a.clairvoyant(w)
        cell = a.cell(None, None, w) if option == FIXED else a.cell(next(p for p in POLICIES if p.id == option), math.inf, w)
        seer[w] = {**{k: cell[k] for k in ("doors_open", "doors_total", "peak_financing_chf", "master", "target_holds",
                                           "target_value_chf", "target_required_chf")},
                   "option": option, "label": say("Stay on the plan", "Rester sur le plan") if option == FIXED else a.branch[option]["label"]}
    # L'écart entre la politique et le plan figé, monde par monde : ce que lire son état, puis décider, change pour cette Alexia.
    gap = {}
    for p in POLICIES:
        gap[p.id] = {}
        for w in worlds:
            ours, plan = cells[p.id][w], cells[FIXED][w]
            gap[p.id][w] = {"doors_more": ours["doors_open"] - plan["doors_open"],
                            "financing_difference_chf": round(ours["peak_financing_chf"] - plan["peak_financing_chf"], 2),
                            "regret_difference_chf": round(ours["regret_chf"] - plan["regret_chf"], 2),
                            "target_saved": ours["target_holds"] and not plan["target_holds"]}
    return {"start_cash_chf": a.t.sc.profile.cash_chf, "cells": cells, "clairvoyant": seer, "gap": gap,
            "bands": {FIXED: a.bands(None, None, worlds), **{p.id: a.bands(p, thresholds[p.id], worlds) for p in POLICIES}}}


def fragile_tree(tree: Tree, overrides: dict | None) -> Tree:
    """La même Alexia, avec moins d'épargne au départ (hypothèse « epargne_depart_fragile »). Rien d'autre ne change."""
    amount = float(tree.theta(overrides)["epargne_depart_fragile"])
    trees = tree.__dict__.setdefault("_fragile_trees", {})
    if amount not in trees:
        trees[amount] = Tree(replace(tree.sc, profile=replace(tree.sc.profile, cash_chf=amount)))
    return trees[amount]


def view(tree: Tree, path: list[dict], overrides: dict | None = None, mondes=None) -> dict:
    """Le tableau de valeur : le plan figé et les trois politiques en lignes, les mondes en colonnes.
    Deux fois : pour Alexia, et pour Alexia fragile. La politique est la même, avec les mêmes seuils : seul l'état change."""
    th = tree.theta(overrides)
    worlds = W.asked(mondes if mondes is not None else TABLE_WORLDS, th, tree.h, tree.age0)
    for world in worlds:
        # Les variantes de test du tableau déplacent et dosent une crise à la fois : un monde combiné n'y entre pas.
        if W.combined(world):
            raise ValueError(say(f"The value table keeps one crisis per world: “{world}” combines two.",
                                 f"Le tableau de valeur garde une crise par monde : « {world} » en combine deux."))
    key = (json.dumps(path, sort_keys=True), json.dumps(overrides or {}, sort_keys=True), worlds, i18n.current())
    cache = tree.__dict__.setdefault("_policy_views", {})
    if key in cache:
        return cache[key]
    a = Analysis(tree, path, overrides)
    found = {p.id: a.calibrate(p, worlds) for p in POLICIES}
    thresholds = {p.id: found[p.id]["threshold_chf"] for p in POLICIES}
    checks = validate(tree, a.path, overrides, worlds, thresholds)
    rows = [{"id": FIXED, "name": say("Fixed plan", "Plan figé"), "rule": None, "calibration": None, "leave_one_out": None}]
    rows += [{"id": p.id, "name": policy_name(p), "rule": a.rule(p, thresholds[p.id]), "calibration": found[p.id],
              "leave_one_out": checks["leave_one_out"][p.id]} for p in POLICIES]
    base = _case(a, thresholds, worlds)
    door = next(d for d in tree.doors(th) if d["key"] == a.target)
    described = W.describe(th, tree.h, tree.age0, list(worlds))
    cache[key] = {
        "path": a.path, "target": {**door, "required_chf": base["cells"][FIXED][worlds[0]]["target_required_chf"]},
        "worlds": [{**w, "highlight": w["type"] == HIGHLIGHT} for w in described],
        "policies": rows, **base,
        "fragile": _case(Analysis(fragile_tree(tree, overrides), a.path, overrides), thresholds, worlds),
        "validation": {"variants": checks["variants"], "random": checks["random"]}}
    return cache[key]
