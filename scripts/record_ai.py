"""Real answers of the model, recorded once and played again without it. Run from the root of the repository.

    python scripts/record_ai.py record --dry-run    what would be sent and what it would cost. Nothing is sent, no
                                                    client is built, and the key is not looked at.
    python scripts/record_ai.py check               one live call, to check everything before the rest: the first
                                                    sentence of “Ask”. Its answer is the first recording.
    python scripts/record_ai.py record              the other recordings: eleven sentences, then two stress tests.

What is recorded: for the demo route with unchanged assumptions, in English and in French, six sentences of “Ask in
your own words” and one “Find what breaks my plan”. The files go to ai/recorded/. A recording that exists is kept:
--force records it again. Each recording is played again at once, without the model, and must give the same answer.

The two live commands need ANTHROPIC_API_KEY in the environment of the terminal. The SDK reads the key when it sends
a request. This script only looks at whether it is there, and never prints it or writes it. What happened is added to
reports/ai_live.log, with the tokens and the cost of each exchange and without any key.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import date
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai import ask as asking  # noqa: E402
from ai import benchmark, cost, recordings, rehearsal, service  # noqa: E402
from ai import stress as stressing  # noqa: E402
from ai.cost import count, number, span, usd  # noqa: E402
from ai.model import MAX_TOKENS, MODEL, Live, Recorder  # noqa: E402
from ai.rehearsal import indent, settings  # noqa: E402
from engine.blocks import normalize  # noqa: E402
from engine.simulate import load_scenario  # noqa: E402
from engine.tree import Tree  # noqa: E402

SCENARIO, ROUTE = "alexia", "story_a"
LOG, DRY_RUN = recordings.LOG, ROOT / "reports" / "ai_dry_run.record.json"
MOST = 3.0                  # US dollars: past this, nothing more is recorded. The high estimate of the dry run is about 1
# The six sentences of “Ask”, the same in both languages: a crisis with a size, a route, a change at an age, two
# crises, assumptions with savings, and one that Doors cannot set.
SENTENCES = {
    "en": ["What if I lost my job for 9 months at 27?",
           "What if I did my master's first, then worked?",
           "What if I moved to Berlin at 23?",
           "A market crash of 40% at 24, then a year without a job right after my master's.",
           "With a rent of 1'500 CHF and a return of 5%, and 40'000 CHF set aside at 26.",
           "What if I had a child at 28 and moved to London?"],
    "fr": ["Et si je perdais mon emploi pendant 9 mois à 27 ans ?",
           "Et si je faisais mon master d'abord, puis un emploi ?",
           "Et si je partais à Berlin à 23 ans ?",
           "Un krach de 40 % à 24 ans, puis un an sans emploi juste après mon master.",
           "Avec un loyer de 1'500 CHF et un rendement de 5 %, et 40'000 CHF de côté à 26 ans.",
           "Et si j'avais un enfant à 28 ans et que je partais à Londres ?"],
}


def plan(only: str | None = None, lang: str | None = None, sentence: int | None = None) -> list[dict]:
    """What there is to record, in order: the sentences first, which are short, then the stress tests."""
    items = [{"kind": "ask", "language": language, "number": index, "sentence": words}
             for language in SENTENCES for index, words in enumerate(SENTENCES[language], start=1)]
    items += [{"kind": "stress", "language": language} for language in SENTENCES]
    return [item for item in items if only in (None, item["kind"]) and lang in (None, item["language"])
            and (sentence is None or item.get("number") == sentence)]


def title(item: dict) -> str:
    if item["kind"] == "ask":
        return f"ask · {item['language']} · {item['number']} · “{item['sentence']}”"
    return f"stress · {item['language']} · the demo route"


def existing(item: dict, path: list[dict]) -> dict | None:
    return recordings.find(item["kind"], item["language"], SCENARIO, path, {}, item.get("sentence"))


# ---------------------------------------------------------------------------------------------------- the dry run
def dry_run(items: list[dict], tree: Tree, path: list[dict], fallback: bool, force: bool, brief: bool) -> None:
    """Plays each exchange with a stand-in for the model, shows what would be sent, and estimates the cost."""
    measures = cost.measured(recordings.every())
    print(rehearsal.HEADING)
    print(settings(fallback))
    print(f"Estimates: {measures.get('characters_per_token', cost.CHARACTERS_PER_TOKEN)} characters per token "
          f"({'measured on the recorded answers' if 'characters_per_token' in measures else 'assumed'}); input priced as if nothing were read from the cache.\n")
    shown, written, estimates, skipped = set(), [], [], 0
    for item in items:
        if existing(item, path) is not None and not force:
            skipped += 1
            print(f"== {title(item)}\n   already recorded: kept (--force would record it again)\n")
            continue
        requests = rehearsal.stress(tree, path, {}, item["language"]) if item["kind"] == "stress" else \
            rehearsal.ask(tree, item["sentence"], path, {}, item["language"])
        estimated = cost.estimate(requests, measures)
        estimates.append(estimated)
        written.append({"what": title(item), "estimate": estimated, "requests": rehearsal.as_sent(requests, fallback)})
        print(f"== {title(item)}")
        kinds = Counter(cost.kind_of(request) for request in requests)
        for kind in ("ask", "search", "explain"):
            mine = [request for request in requests if cost.kind_of(request) == kind]
            if not mine:
                continue
            first = mine[0]
            what = {"ask": "1 request", "search": f"{kinds[kind]} to {kinds[kind] + 1} requests of the search, with the tool {stressing.TOOL}",
                    "explain": "1 to 3 requests for the explanations, one more each time the checker refuses a text"}[kind]
            print(f"   {what} · effort {first['effort']}")
            print(f"     system prompt: {number(len(first['system']))} characters" + (" (shown above)" if first["system"] in shown else ""))
            if first["output"] is not None:
                print(f"     form the answer must follow: {', '.join(first['output']['properties'])}")
            if kind == "search":
                sizes = [cost.characters(request) for request in mine]
                print(f"     the conversation grows with the results of the engine: {number(sizes[0])} characters at the first request, {number(sizes[-1])} at the last")
            if not brief:
                if first["system"] not in shown:
                    shown.add(first["system"])
                    print("     --- system prompt ---\n" + indent(first["system"]))
                    if first["tools"]:
                        print("     --- tool ---\n" + indent(json.dumps(first["tools"], ensure_ascii=False, indent=1)))
                print("     --- first message ---\n" + indent(first["messages"][0]["content"]))
        print(f"   estimate: {span(estimated['low']['input_tokens'], estimated['high']['input_tokens'])} tokens sent, "
              f"{span(estimated['low']['output_tokens'], estimated['high']['output_tokens'])} tokens answered: "
              f"{span(estimated['low']['usd'], estimated['high']['usd'], usd)}\n")
    if estimates:
        total = cost.add(estimates)
        DRY_RUN.parent.mkdir(exist_ok=True)
        DRY_RUN.write_text(json.dumps({"settings": settings(fallback), "exchanges": written, "total": total}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"TOTAL for {count(len(estimates), 'exchange')}: {span(total['low']['requests'], total['high']['requests'])} request{'' if total['high']['requests'] == 1 else 's'}, "
              f"{span(total['low']['usd'], total['high']['usd'], usd)}.")
        print(f"Ceiling, if every answer were as long as the API allows ({number(MAX_TOKENS)} tokens): {usd(total['ceiling_usd'])}.")
        print(f"Every request, word for word as the SDK would be given it: {recordings.shown(DRY_RUN)}")
    if skipped:
        print(f"{skipped} already recorded: left as {'it is' if skipped == 1 else 'they are'}.")
    print("\nNothing was sent.")


# ------------------------------------------------------------------------------------------------ the live calls
def record(item: dict, tree: Tree, path: list[dict], fallback: bool) -> tuple[dict, dict, bool]:
    """One exchange with the live model, recorded. Returns the recording, the result, and whether the recording played
    again without the model gives that same result."""
    recorder, started = Recorder(Live(fallback=fallback)), time.perf_counter()
    if item["kind"] == "ask":
        result = asking.ask(tree, item["sentence"], recorder, path, {}, item["language"])
    else:
        result = stressing.run(tree, path, recorder, {}, item["language"], benchmark.truth_for(path, {}, tree.h))
    usage: Counter = Counter()
    for turn in recorder.turns:
        usage.update(turn["reply"]["usage"])
    priced = [cost.cost(turn["reply"]["usage"], turn["reply"].get("model") or MODEL) for turn in recorder.turns]
    recording = {"kind": item["kind"], "language": item["language"], "scenario": SCENARIO, "label": ROUTE, "path": path, "assumptions": {},
                 "sentence": " ".join(item["sentence"].split()) if item["kind"] == "ask" else None, "model": MODEL,
                 "served_by": sorted({turn["reply"]["model"] for turn in recorder.turns if turn["reply"].get("model")}),
                 "recorded_at": date.today().isoformat(), "sdk": metadata.version("anthropic"),
                 "seconds": round(time.perf_counter() - started, 1), "usage": dict(usage),
                 "cost_usd": None if any(price is None for price in priced) else round(sum(priced), 6), "turns": recorder.turns}
    file = recordings.write(recording)
    kept = next(each for each in recordings.every() if each["file"] == file.name)
    try:
        same = service.replay(tree, kept) == result
    except Exception as error:                              # a replay that fails is said, and the recording stays to be looked at
        same = False
        print(f"   the replay failed: {type(error).__name__}: {recordings.scrub(error)}")
    return kept, result, same


def tell(item: dict, recording: dict, result: dict, same: bool) -> None:
    """What one exchange gave, in a few lines."""
    usage = recording["usage"]
    print(f"   {count(len(recording['turns']), 'request')} in {recording['seconds']} s · sent {number(cost.sent(usage))} tokens "
          f"({number(usage.get('cache_read_input_tokens', 0))} read from the cache, {number(usage.get('cache_creation_input_tokens', 0))} written to it) · "
          f"answered {number(usage.get('output_tokens', 0))} tokens ({number(usage.get('thinking_tokens', 0))} of thinking) · {usd(recording['cost_usd'])}")
    if recording["served_by"] != [MODEL]:
        print(f"   served by: {', '.join(recording['served_by']) or 'unknown'}")
    if item["kind"] == "ask":
        print(f"   understood: {result['understood']} · settings: {json.dumps(result['settings'], ensure_ascii=False)}")
        for crisis in (result["world"] or {}).get("crises", []):
            print(f"     crisis {crisis['id']}" + (f" · {crisis['conversion']}" if crisis["conversion"] else "") + (f" · inferred: {crisis['inferred']}" if crisis["inferred"] else ""))
        for assumption in result["assumptions"]:
            print(f"     assumption {assumption['key']} = {assumption['value']}" + (f" · {assumption['reading']}" if assumption["reading"] else ""))
        for entry in result["not_understood"]:
            print(f"     not understood: “{entry['quote']}” · {entry['reason']}")
        for entry in result["refused"]:
            print(f"     refused ({entry['what']}): {entry['reason']}")
    else:
        budget, checked = result["budget"], result["verification"]["benchmark"]
        print(f"   search: {budget['calls_used']} calls, {budget['worlds_tested']} worlds tested, stopped by: {result['stopped']}")
        for world in result["ranking"]:
            explanation = world["explanation"]
            print(f"     {world['world']}: {len(world['goals_lost'])} goals lost · explanation "
                  f"{'accepted' if explanation['accepted'] else 'REJECTED'} after {explanation['attempts'] - 1} rewrites, {explanation['verified']} figures verified")
        if checked:
            print(f"   true answer of the full scan: {checked['max_goals_lost']} goals lost at most. Found by the search: {checked['found']}")
    print(f"   written: ai/recorded/{recording['file']} · played again without the model: {'the same answer' if same else 'NOT THE SAME ANSWER'}")


def live(items: list[dict], tree: Tree, path: list[dict], fallback: bool, force: bool, command: str, most: float = MOST) -> int:
    """Records each item with the live model. Stops at the first failure: what is recorded is kept, and running the
    command again goes on from there."""
    if not os.environ.get("ANTHROPIC_API_KEY"):             # only whether it is there
        print("ANTHROPIC_API_KEY is not set in this terminal. Export it, then run this command again.\n"
              "The key is read by the SDK when it sends a request. This script never prints it and never writes it.")
        return 2
    print(settings(fallback), "\n")
    spent, done = 0.0, 0
    for item in items:
        print(f"== {title(item)}")
        if existing(item, path) is not None and not force:
            print("   already recorded: kept (--force would record it again)\n")
            continue
        if spent >= most:
            print(f"   not recorded: this command has spent {usd(spent)}, and the limit is {usd(most)} (--max-usd)\n")
            continue
        try:
            recording, result, same = record(item, tree, path, fallback)
        except Exception as error:
            told = recordings.describe(error)
            recordings.log({"command": command, "what": title(item), "ok": False, "error": told})
            print(f"   FAILED: {told['type']}" + (f" (status {told['status']})" if told["status"] else "") + f": {told['message']}")
            if told["status"] == 400 and fallback:
                print("   If the message is about “fallbacks” or the beta header, run the command again with --no-fallback.")
            if told["status"] in (401, 403) or "authentication" in told["message"].lower():
                print("   The key was refused, or it is not the key of an account that may call this model.")
            print(f"\nStopped. {done} recorded by this command, {usd(spent)} spent. What is recorded is kept; this line is in {recordings.shown(LOG)}.")
            return 1
        tell(item, recording, result, same)
        recordings.log({"command": command, "what": title(item), "ok": True, "file": recording["file"], "same_when_replayed": same,
                        "seconds": recording["seconds"], "requests": len(recording["turns"]), "usage": recording["usage"], "cost_usd": recording["cost_usd"],
                        "served_by": recording["served_by"], "stop_reasons": [turn["reply"]["stop_reason"] for turn in recording["turns"]]})
        spent, done = spent + (recording["cost_usd"] or 0), done + 1
        print()
    print(f"Done. {done} recorded by this command, {usd(spent)} spent. Log: {recordings.shown(LOG)}")
    return 0


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["check", "record"])
    parser.add_argument("--dry-run", action="store_true", help="show what would be sent and estimate the cost; send nothing")
    parser.add_argument("--brief", action="store_true", help="with --dry-run: the sizes and the estimates, without the texts")
    parser.add_argument("--force", action="store_true", help="record again what is already recorded")
    parser.add_argument("--no-fallback", action="store_true", help="send the requests without the server-side fallback, which is a beta")
    parser.add_argument("--only", choices=["ask", "stress"], help="record only the sentences, or only the stress tests")
    parser.add_argument("--lang", choices=sorted(SENTENCES), help="record only one language")
    parser.add_argument("--sentence", type=int, choices=range(1, 7), help="record only this sentence of “Ask”")
    parser.add_argument("--max-usd", type=float, default=MOST, help=f"record nothing more once this command has spent this much ({MOST:.0f} USD by default)")
    args = parser.parse_args(arguments)
    tree = Tree(load_scenario(benchmark.SCENARIO))
    path = normalize(benchmark.ROUTES[ROUTE], tree.h)
    items = plan(args.only, args.lang, args.sentence) if args.command == "record" else plan("ask", "en", 1)
    if args.dry_run:
        dry_run(items, tree, path, not args.no_fallback, args.force, args.brief)
        return 0
    return live(items, tree, path, not args.no_fallback, args.force, args.command, args.max_usd)


if __name__ == "__main__":
    sys.exit(main())
