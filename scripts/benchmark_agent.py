"""The benchmark of the stress-test agent, from the command line. Run from the root of the repository.

    python scripts/benchmark_agent.py scan      the full scan of the three routes: 49,140 worlds each, a few minutes.
                                                Writes benchmarks/truth.json.
    python scripts/benchmark_agent.py random    random search with the agent's budget, 1,000 times per route.
                                                Writes benchmarks/random.json.
    python scripts/benchmark_agent.py live      the agent with the live model: 10 whole stress tests per route, 30 in
                                                all. Writes benchmarks/agent.json after each run.
    python scripts/benchmark_agent.py live --dry-run
                                                what the runs would send and what they would cost. Nothing is sent,
                                                no client is built, and the key is not looked at.
    python scripts/benchmark_agent.py report    prints what the files say.

The measures are in ai/benchmark.py. Only `live` calls the model, and only without --dry-run. It needs
ANTHROPIC_API_KEY in the environment of the terminal: the SDK reads it when it sends a request, and this script only
looks at whether it is there. A run that is done is kept: running `live` again does the runs that are missing or that
failed, so nothing is paid twice. --fresh starts over.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from datetime import date, datetime
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai import benchmark, cost, recordings, rehearsal, vocabulary  # noqa: E402
from ai.cost import count, number, span, usd  # noqa: E402
from ai.model import MAX_TOKENS, MODEL  # noqa: E402
from ai.stress import CALLS, PER_CALL  # noqa: E402
from engine.simulate import load_scenario  # noqa: E402
from engine.tree import Tree  # noqa: E402

RANDOM = ROOT / "benchmarks" / "random.json"
DRY_RUN = ROOT / "reports" / "ai_dry_run.benchmark.json"
RUNS, PARALLEL = 10, 3
MOST = 15.0                 # US dollars: past this, no new run is started. The high estimate of the dry run is about 10


def write(file: Path, data: dict, quiet: bool = False) -> None:
    file.parent.mkdir(exist_ok=True)
    draft = file.with_suffix(".tmp")
    draft.write_text(recordings.scrub(json.dumps(data, ensure_ascii=False, indent=1)) + "\n", encoding="utf-8")
    draft.replace(file)                             # the file is whole at every moment, even if a run is interrupted
    if not quiet:
        print(f"written: {recordings.shown(file)}")


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


# ------------------------------------------------------------------------------------------ the agent, live
def kept(file: Path | None = None) -> dict:
    """The runs already made, by route. Empty when the file does not exist yet."""
    file = file or benchmark.AGENT
    saved = json.loads(file.read_text(encoding="utf-8")) if file.is_file() else {}
    return {key: list(saved.get("routes", {}).get(key, {}).get("runs", [])) for key in benchmark.ROUTES}


def missing(runs: dict, wanted: int, routes: list[str]) -> list[tuple[str, int]]:
    """The runs still to make, a round of every route at a time: a run that failed is to be made again."""
    done = {(key, each["run"]) for key in runs for each in runs[key] if "error" not in each}
    return [(key, each) for each in range(wanted) for key in routes if (key, each) not in done]


def save(runs: dict, wanted: int, file: Path | None = None) -> dict:
    """Writes the runs and what they measure. Returns what was written."""
    truth = benchmark.load()["routes"]
    routes = {}
    for key in benchmark.ROUTES:
        mine = sorted(runs.get(key, []), key=lambda each: each["run"])
        if mine:
            routes[key] = {"summary": benchmark.summary(key, mine, truth[key]), "runs": mine}
    done = [each for key in routes for each in routes[key]["runs"] if "error" not in each]
    priced = [each["cost_usd"] for each in done]
    data = {"model": MODEL, "sdk": metadata.version("anthropic"), "updated": datetime.now().isoformat(timespec="seconds"),
            "budget": CALLS * PER_CALL, "runs_asked_per_route": wanted,
            "languages": "The explanations of a run are in one language: English for even runs, French for odd ones. The search is held in English.",
            "total": {"runs": len(done), "found": sum(each["found"] for each in done), "requests": sum(each["requests"] for each in done),
                      "seconds": round(sum(each["seconds"] for each in done), 1),
                      "cost_usd": None if any(price is None for price in priced) else round(sum(priced), 6),
                      "explanations": benchmark.rewrites([explanation for each in done for explanation in each["explanations"]])},
            "routes": routes}
    write(file or benchmark.AGENT, data, quiet=True)
    return data


def told(run: dict, truth: dict) -> str:
    """One run in one line."""
    head = f"{run['route']} #{run['run']} ({run['language']})"
    if "error" in run:
        error = run["error"]
        return f"{head}: FAILED {error['type']}" + (f" (status {error['status']})" if error["status"] else "") + f": {error['message']}"
    rewrites = "/".join(str(explanation["rewrites"]) if explanation["accepted"] else "rejected" for explanation in run["explanations"]) or "none"
    return (f"{head}: {'FOUND' if run['found'] else 'not found'}, {run['goals_lost']} goals lost at best (the most is {truth['max_goals_lost']}) · "
            f"{run['worlds_tested']} worlds in {run['calls_used']} calls · rewrites per explanation: {rewrites} · {run['requests']} requests, "
            f"{run['seconds']} s, {usd(run['cost_usd'])}")


def projected(made: list[dict], left: int, parallel: int) -> dict | None:
    """What the runs left would cost and how long they would take, at the price and the pace of the runs already made:
    the most direct estimate there is. None before any run is made."""
    made = [each for each in made if "error" not in each and each.get("cost_usd") is not None]
    if not made:
        return None
    costs, seconds = [each["cost_usd"] for each in made], [each["seconds"] for each in made]
    mean = sum(costs) / len(costs)
    return {"runs_made": len(made), "usd_a_run": mean, "least_usd_a_run": min(costs), "most_usd_a_run": max(costs), "seconds_a_run": sum(seconds) / len(seconds),
            "runs_left": left, "usd": mean * left, "least_usd": min(costs) * left, "most_usd": max(costs) * left,
            "minutes": sum(seconds) / len(seconds) * left / max(1, parallel) / 60}


def live_dry_run(todo: list[tuple[str, int]], fallback: bool, brief: bool, made: list[dict] = (), parallel: int = PARALLEL) -> None:
    measures = cost.measured(recordings.every())
    tree = Tree(load_scenario(benchmark.SCENARIO))
    print(rehearsal.HEADING)
    print(rehearsal.settings(fallback))
    print(f"Estimates: {measures.get('characters_per_token', cost.CHARACTERS_PER_TOKEN)} characters per token "
          f"({'measured on the recorded answers' if 'characters_per_token' in measures else 'assumed'}); input priced as if nothing were read from the cache.")
    if measures.get("answers"):
        print("Tokens of one answer, measured on the recorded answers: "
              + "; ".join(f"{kind} {seen['least']} to {seen['most']}" for kind, seen in measures["answers"].items()) + ".")
    print()
    estimates, written, rehearsed = [], [], {}
    for key, each in todo:
        lang = benchmark.language_of(each)
        if (key, lang) not in rehearsed:                    # one rehearsal per route and language: the runs of a kind send the same first request
            requests = rehearsal.stress(tree, benchmark.ROUTES[key], None, lang)
            rehearsed[key, lang] = (requests, cost.estimate(requests, measures))
            written.append({"what": f"{key} · {lang}", "estimate": rehearsed[key, lang][1], "requests": rehearsal.as_sent(requests, fallback)})
        estimates.append(rehearsed[key, lang][1])
    for (key, lang), (requests, estimated) in rehearsed.items():
        left = sum(1 for route, each in todo if route == key and benchmark.language_of(each) == lang)
        search = [request for request in requests if cost.kind_of(request) == "search"]
        print(f"== {key} · explanations in {lang} · {count(left, 'run')} to make")
        print(f"   each run: {len(search)} to {len(search) + 1} requests of the search (effort {search[0]['effort']}), then 1 to 3 for the explanations")
        print(f"   each run: {span(estimated['low']['input_tokens'], estimated['high']['input_tokens'])} tokens sent, "
              f"{span(estimated['low']['output_tokens'], estimated['high']['output_tokens'])} answered: {span(estimated['low']['usd'], estimated['high']['usd'], usd)}")
        if not brief and (key, lang) == next(iter(rehearsed)):
            print("     --- system prompt of the search ---\n" + rehearsal.indent(search[0]["system"]))
            print("     --- tool ---\n" + rehearsal.indent(json.dumps(search[0]["tools"], ensure_ascii=False, indent=1)))
            print("     --- first message ---\n" + rehearsal.indent(search[0]["messages"][0]["content"]))
            print("     (the other routes and the explanations are in the file named below)")
        print()
    if not estimates:
        print("Every run asked for is already made: nothing to send.")
        return
    total, measured = cost.add(estimates), projected(list(made), len(todo), parallel)
    DRY_RUN.parent.mkdir(exist_ok=True)
    DRY_RUN.write_text(json.dumps({"settings": rehearsal.settings(fallback), "runs_to_make": len(todo), "examples": written, "total": total,
                                   "from_the_runs_already_made": measured}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"TOTAL for {count(len(todo), 'run')}: {span(total['low']['requests'], total['high']['requests'])} requests, "
          f"{span(total['low']['usd'], total['high']['usd'], usd)}.")
    print(f"Ceiling, if every answer were as long as the API allows ({number(MAX_TOKENS)} tokens): {usd(total['ceiling_usd'])}.")
    print(f"One rehearsed run per route and language, word for word as the SDK would be given it: {recordings.shown(DRY_RUN)}")
    if measured:
        print(f"\nMeasured on the {count(measured['runs_made'], 'run')} already made: {usd(measured['usd_a_run'])} a run on average "
              f"(from {usd(measured['least_usd_a_run'])} to {usd(measured['most_usd_a_run'])}), {measured['seconds_a_run']:.0f} s a run.")
        print(f"At that price, the {count(measured['runs_left'], 'run')} left: about {usd(measured['usd'])} (from {usd(measured['least_usd'])} to "
              f"{usd(measured['most_usd'])}), and about {measured['minutes']:.0f} minutes with {parallel} at a time.")
    print("\nNothing was sent.")


def live(wanted: int, parallel: int, fallback: bool, routes: list[str], fresh: bool, dry: bool, brief: bool, most: float = MOST) -> int:
    runs = {key: [] for key in benchmark.ROUTES} if fresh else kept()
    todo = missing(runs, wanted, routes)
    if dry:
        live_dry_run(todo, fallback, brief, [each for key in runs for each in runs[key]], parallel)
        return 0
    if not os.environ.get("ANTHROPIC_API_KEY"):             # only whether it is there
        print("ANTHROPIC_API_KEY is not set in this terminal. Export it, then run this command again.\n"
              "The key is read by the SDK when it sends a request. This script never prints it and never writes it.")
        return 2
    truth = benchmark.load()["routes"]
    made = sum(len([each for each in runs[key] if "error" not in each]) for key in runs)
    print(rehearsal.settings(fallback))
    print(f"{count(len(todo), 'run')} to make, {made} already made and kept. {parallel} at a time. The file is written after each run: "
          f"{recordings.shown(benchmark.AGENT)}")
    print(f"No new run is started once this command has spent {usd(most)} (--max-usd): the runs under way are let to finish.\n")
    if not todo:
        report()
        return 0
    failed, refused, spent, capped = 0, False, 0.0, False
    parallel, queue, under_way = max(1, parallel), deque(todo), set()
    with ProcessPoolExecutor(max_workers=parallel) as pool:
        while queue or under_way:
            # A run is handed over only when a place is free and nothing says to stop: never more than `parallel` are paid for at once.
            while queue and len(under_way) < parallel and not capped:
                key, each = queue.popleft()
                under_way.add(pool.submit(benchmark.live_run, (key, each, fallback)))
            if not under_way:
                break
            finished, under_way = wait(under_way, return_when=FIRST_COMPLETED)
            for done in finished:
                run = done.result()
                runs[run["route"]] = [each for each in runs[run["route"]] if each["run"] != run["run"]] + [run]
                save(runs, wanted)
                print(told(run, truth[run["route"]]), flush=True)
                spent += run.get("cost_usd") or 0
                if "error" in run:
                    failed += 1
                    recordings.log({"command": "benchmark live", "what": f"{run['route']} #{run['run']}", "ok": False, "error": run["error"]})
                    if run["error"]["status"] in (400, 401, 403):                   # every other run would fail the same way: stop here
                        refused = True
                capped = capped or refused or spent >= most
    data = save(runs, wanted)
    recordings.log({"command": "benchmark live", "what": f"{len(todo)} runs asked", "ok": not failed, "failed": failed, "spent_usd": round(spent, 6),
                    "runs_made_in_all": data["total"]["runs"], "found": data["total"]["found"], "cost_usd": data["total"]["cost_usd"],
                    "seconds": data["total"]["seconds"]})
    print()
    if capped and not refused:
        print(f"Stopped: this command has spent {usd(spent)}, and the limit is {usd(most)}. Run it again with a higher --max-usd to make the rest.")
    if refused:
        print("Stopped: the API refused the request itself. The runs under way were let to finish; nothing more was sent.")
        if fallback:
            print("If the message is about “fallbacks” or the beta header, run the command again with --no-fallback.")
    print(f"{count(data['total']['runs'], 'run')} made in all, {failed} failed in this command, {usd(spent)} spent by this command. "
          f"Cost of all the runs made: {usd(data['total']['cost_usd'])}.")
    if failed:
        print("Run the command again to make the runs that failed: the ones that are made are kept.")
    report()
    return 1 if failed else 0


def report() -> None:
    truth = benchmark.load()["routes"]
    drawn = json.loads(RANDOM.read_text(encoding="utf-8"))["routes"] if RANDOM.is_file() else {}
    agent = json.loads(benchmark.AGENT.read_text(encoding="utf-8")) if benchmark.AGENT.is_file() else {"routes": {}}
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
        if key in agent["routes"] and not agent["routes"][key]["summary"]["runs"]:
            print(f"  the agent ({agent['model']}): no run made yet, {agent['routes'][key]['summary']['failed']} failed")
        elif key in agent["routes"]:
            mine = agent["routes"][key]["summary"]
            explained = mine["explanations"]
            print(f"  the agent ({agent['model']}), {mine['budget']} worlds: finds one of the hardest in {mine['found']} of {mine['runs']} runs"
                  + (f" ({mine['share_found']:.0%})" if mine["runs"] else "") + f"; best found per run, goals lost -> runs: {mine['best_goals_lost']}")
            if mine["mean_severity_gap"] is not None:
                print(f"    when found: {mine['mean_severity_gap']:.1f} points of total severity above the mildest of the hardest worlds, on average")
            print(f"    explanations: {explained['accepted']} of {explained['count']} accepted by the checker; rewrites -> explanations: "
                  f"{explained['accepted_after_rewrites']}; rejected after three attempts: {explained['rejected']}")
            print(f"    {mine['requests']} requests, {mine['seconds']} s, {usd(mine['cost_usd'])}" + (f"; {mine['failed']} runs failed" if mine["failed"] else ""))
    if agent["routes"] and agent["total"]["runs"]:
        total = agent["total"]
        print(f"\nThe agent in all: {total['found']} of {total['runs']} runs find one of the hardest worlds. Explanations: {total['explanations']['accepted']} of "
              f"{total['explanations']['count']} accepted, rewrites -> explanations: {total['explanations']['accepted_after_rewrites']}. "
              f"{total['requests']} requests, {usd(total['cost_usd'])}.")


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["scan", "random", "live", "report"])
    parser.add_argument("--runs", type=int, default=RUNS, help=f"live: whole stress tests per route ({RUNS} by default)")
    parser.add_argument("--parallel", type=int, default=PARALLEL, help=f"live: runs made at the same time ({PARALLEL} by default)")
    parser.add_argument("--route", choices=sorted(benchmark.ROUTES), action="append", help="live: only this route (may be given several times)")
    parser.add_argument("--dry-run", action="store_true", help="live: show what would be sent and estimate the cost; send nothing")
    parser.add_argument("--brief", action="store_true", help="with --dry-run: the sizes and the estimates, without the texts")
    parser.add_argument("--fresh", action="store_true", help="live: start over, without the runs already made")
    parser.add_argument("--no-fallback", action="store_true", help="live: send the requests without the server-side fallback, which is a beta")
    parser.add_argument("--max-usd", type=float, default=MOST, help=f"live: start no new run once this command has spent this much ({MOST:.0f} USD by default)")
    args = parser.parse_args(arguments)
    if args.command == "live":
        return live(args.runs, args.parallel, not args.no_fallback, args.route or list(benchmark.ROUTES), args.fresh, args.dry_run, args.brief, args.max_usd)
    {"scan": scan, "random": random_search, "report": report}[args.command]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
