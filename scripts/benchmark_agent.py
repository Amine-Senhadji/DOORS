"""The benchmark of the stress-test agent, from the command line. Run from the root of the repository.

    python scripts/benchmark_agent.py scan      the full scan of the three routes: 49,140 worlds each, a few minutes.
                                                Writes benchmarks/truth.json.
    python scripts/benchmark_agent.py random    random search with the agent's budget, 1,000 times per route.
                                                Writes benchmarks/random.json.
    python scripts/benchmark_agent.py report    prints what the two files say.

The measures are in ai/benchmark.py. The runs of the agent with the live model are added when a key is available;
nothing here calls a model.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai import benchmark, vocabulary  # noqa: E402
from ai.stress import CALLS, PER_CALL  # noqa: E402

RANDOM = ROOT / "benchmarks" / "random.json"


def write(file: Path, data: dict) -> None:
    file.parent.mkdir(exist_ok=True)
    file.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"written: {file.relative_to(ROOT)}")


def scan() -> None:
    route = benchmark.route_of("story_a")
    space = vocabulary.describe(route.th, route.h, route.age0)
    with ProcessPoolExecutor(max_workers=len(benchmark.ROUTES)) as pool:              # one route per process
        routes = dict(pool.map(benchmark.scan_route, benchmark.ROUTES))
    write(benchmark.TRUTH, {"scanned_on": date.today().isoformat(),
                            "space": {"worlds": space["worlds"], "types": [kind["id"] for kind in space["types"]], "ages": space["ages"],
                                      "severities": space["severities"], "crises_per_world": space["crises_per_world"]},
                            "routes": {key: routes[key] for key in benchmark.ROUTES}})
    report()


def random_search() -> None:
    truth = benchmark.load()["routes"]
    write(RANDOM, {"budget": CALLS * PER_CALL, "routes": {key: benchmark.random_search(truth[key]) for key in benchmark.ROUTES}})
    report()


def report() -> None:
    truth = benchmark.load()["routes"]
    drawn = json.loads(RANDOM.read_text(encoding="utf-8"))["routes"] if RANDOM.is_file() else {}
    for key, found in truth.items():
        print(f"\n{key}: {found['worlds']} worlds scanned in {found['seconds']} s. With no crisis: {found['calm']['goals_kept']} goals of "
              f"{found['calm']['goals_total']}.")
        print(f"  goals lost -> worlds: {found['histogram']}")
        print(f"  hardest: {found['max_goals_lost']} goals lost, in {found['hardest_count']} worlds; mildest total severity {found['least_severity']}")
        for world in found["hardest"][:3]:
            print(f"    {world['world']}  (severity {world['severity']}, peak borrowing {world['peak_financing_chf']} CHF)")
        single = found["single_crises"]
        print(f"  single crises alone: {single['max_goals_lost']} goals lost at most, in {single['hardest_count']} of {single['worlds']}")
        if key in drawn:
            print(f"  random search, {drawn[key]['budget']} worlds: finds one of the hardest in {drawn[key]['found']} of {drawn[key]['repetitions']} "
                  f"draws ({drawn[key]['exact_share']:.2%} of all possible draws)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["scan", "random", "report"])
    {"scan": scan, "random": random_search, "report": report}[parser.parse_args().command]()
