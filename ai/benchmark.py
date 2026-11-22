"""The benchmark of the stress-test agent: does the search find the hardest world, and at what cost?

The true answer comes from a full scan, made offline: every world of the space, 49,140 per route, simulated by the
engine. It is kept in benchmarks/truth.json for three routes: the demo route, ten years of work, and ten years in
Berlin. The agent has 40 simulations. Three things are measured over several runs: how often it finds the hardest
world or one as hard, how many simulations it used, and how far the severity of what it found is from the mildest
of the hardest worlds. Random search with the same budget is the yardstick.

Nothing here calls a model: `play` takes whatever model it is given, and the tests give it a script.
"""
from __future__ import annotations

import json
import math
import random
import time
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable

from ai import vocabulary as V
from ai.model import Model
from ai.stress import CALLS, PER_CALL, Route, harder, rank, search
from engine.blocks import normalize
from engine.simulate import load_scenario
from engine.tree import Tree

ROOT = Path(__file__).resolve().parents[1]
TRUTH = ROOT / "benchmarks" / "truth.json"
SCENARIO = ROOT / "engine" / "scenarios" / "alexia.json"
ROUTES = {
    "story_a": [{"block": "job", "years": 5}, {"block": "master", "years": 2}, {"block": "job", "years": 3}],     # the demo route
    "work_only": [{"block": "job", "years": 10}],
    "berlin": [{"block": "job_abroad", "years": 10}],
}
LISTED = 40                 # how many of the hardest worlds are written in the file, mildest first
SEED, REPETITIONS = 2026, 1000


def route_of(key: str) -> Route:
    return Route(Tree(load_scenario(SCENARIO)), ROUTES[key])


def scan(route: Route, worlds: Iterable[str] | None = None) -> dict:
    """Simulates every world given, the whole space by default, and returns the true answer: the largest number of
    goals a world makes the route lose, how many worlds reach it, and the mildest of them."""
    started = time.perf_counter()
    histogram: Counter = Counter()
    most, hardest = 0, []
    for world in worlds if worlds is not None else V.worlds(route.th, route.h, route.age0):
        summary = route.measure(world)
        lost = len(summary["goals_lost"])
        histogram[lost] += 1
        if lost > most:
            most, hardest = lost, []
        if lost == most and lost:
            hardest.append(summary)
    hardest.sort(key=harder)
    return {"path": route.path, "worlds": sum(histogram.values()),
            "calm": {"goals_kept": sum(route.calm_goals.values()), "goals_total": len(route.calm_goals)},
            "max_goals_lost": most, "histogram": {str(lost): histogram[lost] for lost in sorted(histogram)},
            "hardest_count": len(hardest), "least_severity": hardest[0]["severity"] if hardest else None,
            "hardest": hardest[:LISTED], "seconds": round(time.perf_counter() - started, 1)}


def scan_route(key: str) -> tuple[str, dict]:
    """The full scan of one route of the benchmark. A function of its own, so that the routes can be scanned side by side."""
    route = route_of(key)
    single = scan(route, V.singles(route.th, route.h, route.age0))
    return key, {**scan(route), "single_crises": {name: single[name] for name in ("worlds", "max_goals_lost", "hardest_count", "least_severity")}
                                                 | {"hardest": rank(single["hardest"])}}


def load() -> dict:
    """The true answers kept in the repository. Empty when the scan has never been run."""
    return json.loads(TRUTH.read_text(encoding="utf-8")) if TRUTH.is_file() else {"routes": {}}


def truth_for(path: list[dict], overrides: dict | None = None, horizon: int = 120) -> dict | None:
    """The true answer for a route, when it is a route of the benchmark with unchanged assumptions. None otherwise:
    the screen then only has what the engine checks while Alexia waits."""
    if overrides:
        return None
    path = normalize(path, horizon)
    for key, truth in load()["routes"].items():
        if truth["path"] == path:
            return {"route": key, **{name: truth[name] for name in ("worlds", "max_goals_lost", "hardest_count", "least_severity")},
                    "hardest": truth["hardest"][:3]}
    return None


# --------------------------------------------------------------------------------------------------- the measures
def measure(found: dict, truth: dict) -> dict:
    """One run of the search against the true answer. `found`: what `ai.stress.search` returns."""
    tested = list(found["tested"].values())
    most = max((len(summary["goals_lost"]) for summary in tested), default=0)
    best = min((summary for summary in tested if len(summary["goals_lost"]) == most), key=harder, default=None)
    hit = most >= truth["max_goals_lost"] > 0
    return {"found": hit, "goals_lost": most, "world": best["world"] if best and most else None,
            "worlds_tested": len(tested), "calls_used": len(found["calls"]), "stopped": found["stopped"],
            "severity_gap": best["severity"] - truth["least_severity"] if hit else None,
            "tokens": {key: value for key, value in found["usage"].items()}}


def play(key: str, model_for: Callable[[int], Model], runs: int, truth: dict | None = None) -> dict:
    """Runs the search `runs` times on a route, each time with the model `model_for(run)` gives, and measures each run
    against the true answer. Only the search is run: the explanations are not part of what is measured."""
    truth = truth if truth is not None else load()["routes"][key]
    route = route_of(key)
    each = [measure(search(route, model_for(number)), truth) for number in range(runs)]
    found = sum(run["found"] for run in each)
    gaps = [run["severity_gap"] for run in each if run["found"]]
    return {"route": key, "runs": runs, "found": found, "share_found": found / runs if runs else None,
            "budget": CALLS * PER_CALL, "space": truth["worlds"], "max_goals_lost": truth["max_goals_lost"],
            "mean_worlds_tested": sum(run["worlds_tested"] for run in each) / runs if runs else None,
            "share_of_space_tested": sum(run["worlds_tested"] for run in each) / runs / truth["worlds"] if runs else None,
            "mean_severity_gap": sum(gaps) / len(gaps) if gaps else None, "each": each}


def random_search(truth: dict, budget: int = CALLS * PER_CALL, repetitions: int = REPETITIONS, seed: int = SEED) -> dict:
    """The yardstick: `budget` worlds drawn at random from the space, with no model, `repetitions` times. Only how many
    goals each world loses matters, so the draw is made on the counts of the scan. `exact_share`: the same quantity
    computed and not drawn, the share of all possible draws that hold one of the hardest worlds."""
    counts = {int(lost): count for lost, count in truth["histogram"].items()}
    space, most = sum(counts.values()), truth["max_goals_lost"]
    # Worlds in a row, hardest first: a drawn position gives the number of goals that world loses.
    limits, upto = [], 0
    for lost in sorted(counts, reverse=True):
        upto += counts[lost]
        limits.append((upto, lost))
    draw, best_drawn = random.Random(seed), Counter()
    for _ in range(repetitions):
        first = min(draw.sample(range(space), budget))                # the hardest world drawn is the one nearest the front
        best_drawn[next(lost for limit, lost in limits if first < limit)] += 1
    hardest = counts.get(most, 0) if most else 0
    return {"budget": budget, "repetitions": repetitions, "seed": seed, "space": space, "max_goals_lost": most,
            "hardest_count": hardest, "found": best_drawn[most] if most else 0,
            "share_found": best_drawn[most] / repetitions if most else 0.0,
            "exact_share": 1 - math.comb(space - hardest, budget) / math.comb(space, budget),
            "best_goals_lost": {str(lost): best_drawn[lost] for lost in sorted(best_drawn)}}
