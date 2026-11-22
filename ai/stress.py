"""“Find what breaks my plan”: the stress test of a route.

The model searches and writes; the engine decides.

- The model proposes worlds, one crisis or two, in the grammar of the engine, with a single tool: `test_worlds`.
- Code holds the budget: 5 calls of at most 8 worlds, so 40 worlds out of 49,140.
- The engine simulates each world. A world the engine refuses comes back with the engine's refusal.
- Code ranks what was tested: goals lost, then total severity (the mildest world that breaks as much comes first),
  then peak borrowing. The model's own conclusion is not read.
- The model then writes one or two sentences for each of the three worlds kept. Every figure of those sentences is
  checked against the engine's facts for that world (ai/checker.py); a refused text is never shown.
- The signpost to watch is the engine's sentence, never the model's.
- The engine checks the search itself: it scans every single crisis and says whether one of them is harder than what
  the model found.
"""
from __future__ import annotations

import json
import re
from collections import Counter

from ai import vocabulary as V
from ai.checker import Fact, Outcome, Quote, facts_in, rejected_label, supervise
from ai.model import Model
from engine import i18n
from engine import worlds as W
from engine.assumptions import ASSUMPTIONS, by_key
from engine.blocks import blocks_to_ops, legs_of, normalize
from engine.explore import doors_of, margins_of
from engine.i18n import say
from engine.simulate import run_ops
from engine.tree import VARIABLES, Tree

CALLS, PER_CALL, KEPT = 5, 8, 3            # the budget of the search, and how many worlds are explained
HEADLINE = 4                               # the first facts of a world are the ones the screen shows when a text is rejected
TOOL = "test_worlds"
SET_ASIDE = VARIABLES["liquidite_chf"][1]  # what Alexia has set aside in a state: cash + investments - debts

SEARCH = """You are the stress-test agent of Doors, a financial twin for a student in Switzerland. Doors simulates a ten-year \
route (studies, jobs) month by month and checks six goals. Your task is to find the worlds that break this route: the \
crises that make it lose the most goals.

How the search works
- A world holds one crisis or two. A crisis is written type@age~severity, for example krach@24 or inflation@22~150. \
Two crises are joined by "+", for example krach@24+inflation@22. The severity may be left out: it is then 100.
- You compute nothing. You propose worlds with the {tool} tool; the engine simulates each of them and tells you which \
goals are kept and which are lost. Only the engine's results count.
- The budget is fixed: {calls} calls of the tool, {per_call} worlds per call at most, so {budget} worlds out of {space}. \
Every call counts, including a call with a mistake in it. Use what each result teaches you to choose the next worlds.
- A harder world is one that loses more goals. Between two worlds that lose as many goals, the one with the lower total \
severity tells more: it is the mildest crisis that breaks as much.
- When your calls are used up, or when you judge that you have found the hardest worlds, stop. The engine ranks \
everything you tested: you do not need to write a conclusion.

How to search well
- A crisis only matters if it meets what Alexia is doing at that age. Look at the route before you choose.
- Two crises in the same world can interact. The space of pairs is far larger than the space of single crises.
- Explore first, then refine around what breaks the most."""

REMINDER = f"Use the {TOOL} tool to test worlds: nothing has been tested yet."

EXPLAIN = """You write short explanations for Doors, a financial twin for a student in Switzerland. The engine has simulated \
Alexia's ten-year route in a few hard worlds. For each world you are given, write one or two sentences, in {language}, \
that say what happens to the route in that world and why, in plain words, addressed to Alexia ({you}).

Every figure you write is checked by code against the engine's figures for that world, and a text that fails the check \
is not shown. So:
- Use only the figures listed for that world or among the common figures. Copy each one exactly as it is written, with \
its sign and its unit: {figures}. Do not round, do not abbreviate, and do not compute a \
difference, a sum, a ratio or a percentage of your own.
- Do not write {ratios} or any other ratio.
- Next to {kept}, a number of goals must be the number of goals kept or lost in that world. Next to \
{borrowed}, an amount must be the peak borrowing of that world.
- The figures of the route with no crisis are not the figures of that world. Never put the number of goals kept with no \
crisis next to {keep} in the sentence that says what happens in that world. If you want to give it, write it in a sentence \
of its own that says {no_crisis}: {example} The same holds for the peak borrowing with no crisis.
- A sentence given as a quote may be copied word for word, and only word for word.
- The screen shows the name of each world above your text: you do not have to name it. To name a world or one of its \
crises, copy the name given as a quote. The identifier of a world, the code with an "@", goes in the field "world" of \
your answer and nowhere in your text.
- Never write these words or words of their family: {banned}. Do not rank \
options and do not tell Alexia what to do: say what the engine found.
- You need few figures. A sentence with no figure is accepted."""

# What the prompt of the explanations says in the words of the language asked for. The instructions are in English in
# both cases; the words the model must mind, and the example, are in the language it writes in. So a request for an
# English text holds no French, and a request for a French text names the French words the checker looks at.
WORDS = {
    "en": {"language": "English", "you": '"you"', "figures": "43'123 CHF, −5'145 CHF, 12 months",
           "ratios": '"double", "half", "twice", "a third"', "kept": '"keep", "hold" or "lose"', "borrowed": '"borrow" or "finance"',
           "keep": '"keep"', "no_crisis": '"with no crisis"', "example": '"With no crisis the route keeps 3 goals."',
           "banned": "chance, probability, likely, odds, risk, best, recommend, advise, guarantee"},
    "fr": {"language": "French", "you": "« tu »", "figures": "43'123 CHF, −5'145 CHF, 12 mois",
           "ratios": "« double », « moitié », « deux fois », « un tiers »", "kept": "« garder », « tenir » or « perdre », in any of their forms",
           "borrowed": "« emprunter », « emprunt » or « financer »", "keep": "« garder »", "no_crisis": "« sans crise »",
           "example": "« Sans crise, le trajet garde 3 objectifs. »",
           "banned": "chance, probabilité, probable, risque, meilleur, recommander, conseiller, garantir"},
}


def _age(month: int, age0: int) -> str:
    """A month of the route written as an age: "age 27", "27 years 3 months"."""
    years, months = age0 + month // 12, month % 12
    if not months:
        return say(f"age {years}", f"{years} ans")
    return say(f"{years} years {months} month{'' if months == 1 else 's'}", f"{years} ans et {months} mois")


class Route:
    """A route of the scenario, ready to be simulated in any world. Nothing is kept of a simulation but what is asked."""

    def __init__(self, tree: Tree, path: list[dict], overrides: dict | None = None):
        self.tree, self.scenario, self.h, self.age0 = tree, tree.sc, tree.h, tree.age0
        self.path = normalize(path, self.h)
        self.overrides = dict(overrides or {})
        self.th = tree.theta(self.overrides)
        self.ops = blocks_to_ops(self.path, self.th, self.h)
        self.calm = self.simulate("reference")
        self.calm_goals = doors_of(self.calm, self.th, self.age0)

    def simulate(self, world: str):
        return run_ops(self.scenario.profile, self.ops, self.h, self.th, W.build(self.th, world, self.h, self.age0), "trajet", world)

    def measure(self, world: str, result=None) -> dict:
        """What a world does to the route, in figures and identifiers only: the same in every language."""
        result = result or self.simulate(world)
        kept = doors_of(result, self.th, self.age0)
        return {"world": world, "severity": V.severity(world), "types": list(V.types(world)),
                "goals_kept": sum(kept.values()), "goals_total": len(kept),
                "goals_lost": [key for key, holds in kept.items() if self.calm_goals[key] and not holds],
                "peak_financing_chf": round(result.peak_financing_chf, 2), "net_worth_end_chf": round(result.net_worth_end_chf, 2)}

    def detail(self, world: str) -> dict:
        """`measure`, and for each goal lost what is missing: the amount reached and the amount asked, or when the route
        first needs financing."""
        result = self.simulate(world)
        summary, margins, missing = self.measure(world, result), margins_of(result, self.th, self.age0), []
        for goal in self.tree.doors(self.th):
            if goal["key"] in summary["goals_lost"]:
                gap = {"goal": goal["key"], "age": goal["age"]}
                if goal["whole_trip"]:
                    gap["first_financing_month"] = result.first_negative_month
                elif margins[goal["key"]] is not None:
                    gap["reached_chf"], gap["asked_chf"] = (round(amount, 2) for amount in margins[goal["key"]])
                missing.append(gap)
        return {**summary, "missing": missing}

    def name(self, world: str) -> str:
        """The name of a world in the current language, each crisis with its age: "Market crash at 24 + long unemployment at 25"."""
        names = [crisis["name"] for crisis in W.crises(self.th, world, self.h, self.age0)]
        return " + ".join(name if i == 0 else name[0].lower() + name[1:] for i, name in enumerate(names))

    def goals(self) -> dict[str, dict]:
        """The six goals in the current language, by key."""
        return {goal["key"]: goal for goal in self.tree.doors(self.th)}

    def shown(self, summary: dict) -> dict:
        """A summary with the names the screen needs, in the current language."""
        goals = self.goals()
        return {**summary, "name": self.name(summary["world"]), "crises": W.crises(self.th, summary["world"], self.h, self.age0),
                "goals_lost_names": [goals[key]["name"] for key in summary["goals_lost"]]}


def harder(summary: dict) -> tuple:
    """The order of the ranking: more goals lost first; then the lower total severity, the mildest world that breaks as
    much; then the higher peak borrowing. The identifier settles what is left, so that the order never depends on chance."""
    return -len(summary["goals_lost"]), summary["severity"], -summary["peak_financing_chf"], summary["world"]


def rank(summaries, kept: int = KEPT) -> list[dict]:
    """The worlds that break the route, hardest first, without the same combination of types twice. A world that loses
    no goal breaks nothing: it is not ranked."""
    ranked, seen = [], set()
    for summary in sorted(summaries, key=harder):
        if summary["goals_lost"] and tuple(summary["types"]) not in seen:
            seen.add(tuple(summary["types"]))
            ranked.append(summary)
    return ranked[:kept]


# ------------------------------------------------------------------------------------------------------- the search
def _tool() -> dict:
    return {"name": TOOL, "strict": True,
            "description": (f"Simulate the route in up to {PER_CALL} worlds. For each world the engine returns the goals kept, the goals lost "
                            "and the peak borrowing, and for each goal lost what is missing. Call it to test the worlds you expect to break the "
                            f"route. Each call uses one of your {CALLS} calls."),
            "input_schema": {"type": "object", "additionalProperties": False, "required": ["worlds"],
                             "properties": {"worlds": {"type": "array", "items": {"type": "string"},
                                                       "description": (f"World identifiers, {PER_CALL} at most, for example "
                                                                       '["krach@24", "inflation@22~150", "krach@24+inflation@22"].')}}}}


def _brief(route: Route) -> str:
    """What the model is told before it searches: the route, the goals with no crisis, and the space of worlds."""
    goals, space = route.goals(), V.describe(route.th, route.h, route.age0)
    margins = margins_of(route.calm, route.th, route.age0)
    lines = ["The route to test"]
    lines += [f"- {leg['name']}, from {_age(leg['from_month'], route.age0)} to {_age(leg['to_month'], route.age0)}"
              for leg in legs_of(route.path, route.th, route.h)]
    # What Alexia changed, as the drawer shows it: the name of the assumption, its unit, her value and the engine's own.
    names, engine, started = by_key(), {assumption.key: assumption for assumption in ASSUMPTIONS}, route.tree.theta(None)
    written = lambda key, value: Fact.number(V.shown(engine[key], value), "").written()
    changed = [f"- {names[key].label} [{names[key].unit}]: {written(key, value)} (the engine starts from {written(key, started[key])})"
               for key, value in sorted(route.overrides.items()) if key in engine and V.countable(value)]
    lines += ["", "Assumptions changed by Alexia" + ("" if changed else ": none"), *changed, "",
              f"The six goals. With no crisis the route keeps {sum(route.calm_goals.values())} of {len(route.calm_goals)}."]
    for key, goal in goals.items():
        when = "over the whole route" if goal["whole_trip"] else f"at {goal['age']}"
        state = "kept with no crisis" if route.calm_goals[key] else "not kept even with no crisis, so no crisis can make the route lose it"
        reached = "" if goal["whole_trip"] or margins[key] is None else f" ({round(margins[key][0])} CHF for {round(margins[key][1])} CHF asked)"
        lines.append(f"- {goal['name']} ({when}): {state}{reached}. {goal['rule']}")
    lines += ["", "The types of crisis"]
    lines += [f"- {kind['id']}: {kind['name']}. {kind['description']}" for kind in space["types"]]
    lines += ["", f"Ages: {space['ages'][0]} to {space['ages'][1]}. Severities: {', '.join(map(str, space['severities']))} "
                  "(100 is the crisis as the catalogue writes it; a job loss lasts longer or shorter, a market or price move goes deeper or less deep).",
              f"The space holds {space['worlds']} worlds. You have {CALLS} calls of at most {PER_CALL} worlds."]
    return "\n".join(lines)


def _told(route: Route, detail: dict) -> dict:
    """One tested world as the tool tells it to the model: names for the reader, figures as the engine gave them."""
    goals = route.goals()
    missing = []
    for gap in detail["missing"]:
        told = {"goal": goals[gap["goal"]]["name"]}
        if "reached_chf" in gap:
            told.update(at_age=gap["age"], reached_chf=round(gap["reached_chf"]), asked_chf=round(gap["asked_chf"]))
        elif gap.get("first_financing_month") is not None:
            told["financing_needed_from"] = _age(gap["first_financing_month"], route.age0)
        missing.append(told)
    return {"world": detail["world"], "name": route.name(detail["world"]), "goals_kept": detail["goals_kept"],
            "goals_lost": [goals[key]["name"] for key in detail["goals_lost"]], "peak_borrowing_chf": round(detail["peak_financing_chf"]),
            "net_worth_at_the_end_chf": round(detail["net_worth_end_chf"]), "missing": missing}


def _test(route: Route, arguments, tested: dict[str, dict], number: int) -> tuple[dict, dict]:
    """One call of the tool. Returns what the model is told, and the record of the call for the screen."""
    worlds = arguments.get("worlds") if isinstance(arguments, dict) else None
    record = {"call": number, "asked": [], "tested": [], "already_tested": [], "refused": [], "not_tested": []}
    if not isinstance(worlds, list):
        problem = f"{TOOL} takes a list of world identifiers: {{\"worlds\": [\"krach@24\", ...]}}."
        record["refused"].append({"asked": json.dumps(arguments, ensure_ascii=False, default=str)[:200], "reason": problem})
        return {"error": problem, "calls_left": CALLS - number, "worlds_tested_so_far": len(tested)}, record
    record["asked"] = [str(world) for world in worlds]
    told = []
    for asked in worlds[:PER_CALL]:
        try:
            world = V.accept(asked, route.th, route.h, route.age0)
        except (ValueError, KeyError) as refusal:
            record["refused"].append({"asked": str(asked), "reason": str(refusal.args[0])})
            continue
        if world in tested:
            record["already_tested"].append(world)
        else:
            tested[world] = {**route.detail(world), "call": number}
            record["tested"].append(world)
        told.append(_told(route, tested[world]))
    record["not_tested"] = [str(world) for world in worlds[PER_CALL:]]
    answer = {"tested": told, "refused": record["refused"], "calls_left": CALLS - number, "worlds_tested_so_far": len(tested)}
    if record["not_tested"]:
        answer["not_tested"] = {"worlds": record["not_tested"], "reason": f"A call tests {PER_CALL} worlds at most."}
    return answer, record


def _is_the_tool(name) -> bool:
    """`test_worlds`, and the near misses a model may write: "test-worlds", "testWorlds", "test_world"."""
    return re.sub(r"[^a-z]", "", str(name).lower()).rstrip("s") == TOOL.replace("_", "").rstrip("s")


def search(route: Route, model: Model) -> dict:
    """The conversation where the model proposes worlds and the engine answers. The conversation only grows: nothing
    already said is rewritten. Returns the worlds tested, the calls, why the search stopped, and the tokens used."""
    with i18n.use("en"):                # the search is held in English whatever the language of the screen: none of it is shown
        space = V.size(route.th, route.h, route.age0)
        system = SEARCH.format(tool=TOOL, calls=CALLS, per_call=PER_CALL, budget=CALLS * PER_CALL, space=space)
        tools, messages = [_tool()], [{"role": "user", "content": _brief(route)}]
        tested: dict[str, dict] = {}
        calls: list[dict] = []
        usage: Counter = Counter()
        reminded, stopped = False, None
        while stopped is None:
            reply = model.reply(system=system, messages=messages, tools=tools, output=None, effort="medium")
            usage.update({key: value for key, value in reply.usage.items() if isinstance(value, (int, float))})
            if reply.stop_reason == "refusal":                           # read before anything else of the answer
                stopped = "refusal"
                break
            if reply.content:                                            # an answer with nothing in it is not a turn of the conversation
                messages.append({"role": "assistant", "content": list(reply.content)})
            asked = reply.tool_calls()
            if not asked:
                if calls or reminded:
                    stopped = "model" if calls else "no_call"
                else:                                                    # a model may answer without calling: one reminder, never two
                    reminded = True
                    messages.append({"role": "user", "content": REMINDER})
                continue
            results = []
            for call in asked:
                if len(calls) >= CALLS:
                    answer = {"error": f"The budget is used up: {CALLS} calls. This call was not run."}
                elif not _is_the_tool(call.get("name")):
                    calls.append({"call": len(calls) + 1, "asked": [], "tested": [], "already_tested": [], "not_tested": [],
                                  "refused": [{"asked": str(call.get("name")), "reason": f"Unknown tool. The only tool is {TOOL}."}]})
                    answer = {"error": f"Unknown tool. The only tool is {TOOL}.", "calls_left": CALLS - len(calls)}
                else:
                    answer, record = _test(route, call.get("input"), tested, len(calls) + 1)
                    calls.append(record)
                results.append({"type": "tool_result", "tool_use_id": call.get("id"), "content": json.dumps(answer, ensure_ascii=False),
                                **({"is_error": True} if "error" in answer else {})})
            messages.append({"role": "user", "content": results})
            if len(calls) >= CALLS:
                stopped = "budget"
    return {"tested": tested, "calls": calls, "stopped": stopped, "usage": dict(usage), "messages": messages}


# -------------------------------------------------------------------------------------------- the facts of a world
def common_facts(route: Route) -> list[Fact | Quote]:
    """What every explanation may use: the route, the goals, and what happens with no crisis."""
    goals, margins = route.goals(), margins_of(route.calm, route.th, route.age0)
    states = route.tree.trip(route.path, "reference", route.overrides)[1]
    facts: list[Fact | Quote] = [
        Fact.count(len(goals), say("Goals in all", "Objectifs en tout")),
        # The figures of the route with no crisis carry their role: they are checked in the sentences that say "with no crisis".
        Fact.count(sum(route.calm_goals.values()), say("Goals kept with no crisis", "Objectifs gardés sans crise"), None, "kept_calm"),
        Fact.count(0, say("Goals lost with no crisis", "Objectifs perdus sans crise")),
        Fact.chf(route.calm.peak_financing_chf, say("Peak borrowing with no crisis", "Emprunt maximal sans crise"), None, "borrowed_calm"),
        Fact.chf(route.calm.net_worth_end_chf, say("Net worth at the end with no crisis", "Patrimoine à la fin sans crise")),
        Fact.age(route.age0, say("Start of the route", "Départ du trajet")),
        Fact.age(route.age0 + route.h // 12, say("End of the route", "Fin du trajet"))]
    for leg in legs_of(route.path, route.th, route.h):
        start, length = leg["from_month"], leg["to_month"] - leg["from_month"]
        if start % 12 == 0:
            facts.append(Fact.age(route.age0 + start // 12, say(f"{leg['name']}: start", f"{leg['name']} : début")))
        if length % 12 == 0:
            facts.append(Fact.years(length // 12, say(f"{leg['name']}: length", f"{leg['name']} : durée")))
        else:
            facts.append(Fact.months(length, say(f"{leg['name']}: length", f"{leg['name']} : durée")))
    for key, goal in goals.items():
        if not goal["whole_trip"]:
            facts.append(Fact.age(goal["age"], say(f"{goal['name']}: age", f"{goal['name']} : âge")))
            if margins[key] is not None:
                facts.append(Fact.chf(margins[key][1], say(f"{goal['name']}: amount asked", f"{goal['name']} : montant demandé")))
                facts.append(Fact.chf(margins[key][0], say(f"{goal['name']}: amount reached with no crisis", f"{goal['name']} : montant atteint sans crise")))
    for month in route.tree.gares:
        age = route.age0 + month // 12
        facts.append(Fact.chf(SET_ASIDE(states[month]), say(f"Set aside at {age} with no crisis", f"De côté à {age} ans sans crise")))
    return facts


def world_facts(route: Route, world: str) -> list[Fact | Quote]:
    """What the explanation of one world may use: the figures the engine gave for that world, each with where it comes
    from. Three of them carry their role: the goals kept, the goals lost, the peak borrowing. The first four are the
    headline of the world: goals kept, goals lost, peak borrowing, net worth at the end."""
    result, states = route.tree.trip(route.path, world, route.overrides)
    summary, goals, margins = route.measure(world, result), route.goals(), margins_of(result, route.th, route.age0)
    crises = W.crises(route.th, world, route.h, route.age0)
    facts: list[Fact | Quote] = [
        Fact.count(summary["goals_kept"], say("Goals kept in this world", "Objectifs gardés dans ce monde"), world, "kept"),
        Fact.count(len(summary["goals_lost"]), say("Goals lost in this world", "Objectifs perdus dans ce monde"), world, "lost"),
        Fact.chf(result.peak_financing_chf, say("Peak borrowing in this world", "Emprunt maximal dans ce monde"), world, "borrowed"),
        Fact.chf(result.net_worth_end_chf, say("Net worth at the end in this world", "Patrimoine à la fin dans ce monde"), world),
        Fact.count(len(crises), say("Crises in this world", "Crises dans ce monde"), world)]
    facts.append(Quote(route.name(world), say("Name of this world", "Nom de ce monde"), world))
    for crisis in crises:
        facts.append(Quote(crisis["name"], say("Name of the crisis", "Nom de la crise"), world))      # "Six months of unemployment at 24"
        facts.append(Fact.age(crisis["age"], say(f"{crisis['name']}: start", f"{crisis['name']} : début"), world))
        if crisis["to_month"] < route.h:
            facts.append(Fact.months(crisis["to_month"] - crisis["from_month"], say(f"{crisis['name']}: length", f"{crisis['name']} : durée"), world))
        if crisis["gravity"] != 100:
            facts.append(Fact.percent(crisis["gravity"], say(f"{crisis['name']}: severity", f"{crisis['name']} : gravité"), world))
    for line in W.describe(route.th, route.h, route.age0, [world])[0]["parameters"]:
        label, until_the_end = line["label"], line["to_month"] >= route.h
        if not until_the_end:
            facts.append(Fact.months(line["months"], say(f"{label}: length", f"{label} : durée"), world))
        if isinstance(line["value"], bool):
            continue
        during = say(f"{label}, during the crisis", f"{label}, pendant la crise")
        usual = say(f"{label}, in the reference world", f"{label}, dans le monde de référence")
        if line["field"].endswith("_monthly"):
            facts += [Fact.percent(round(line["value"] * 100, 1), during, world), Fact.percent(round(line["reference"] * 100, 1), usual, world)]
        else:
            facts += [Fact.number(round(line["value"], 2), during, world), Fact.number(round(line["reference"], 2), usual, world)]
    for key in summary["goals_lost"]:
        if not goals[key]["whole_trip"] and margins[key] is not None:
            facts.append(Fact.chf(margins[key][0], say(f"{goals[key]['name']}: amount reached in this world",
                                                      f"{goals[key]['name']} : montant atteint dans ce monde"), world))
    for month in route.tree.gares:
        age = route.age0 + month // 12
        facts.append(Fact.chf(SET_ASIDE(states[month]), say(f"Set aside at {age} in this world", f"De côté à {age} ans dans ce monde"), world))
    needing = [month.month for month in result.months if "financement_necessaire" in month.flags]
    if needing:
        facts.append(Fact.months(len(needing), say("Months with a financing need in this world", "Mois avec un besoin de financement dans ce monde"), world))
    # The notes of the ledger: a line of amount 0 is an explanation of the engine. Notes that differ only by a number
    # ("11 months contributed", "10 months contributed") are counted together, and the first one is given as a quote.
    notes: dict[str, list[str]] = {}
    for month in result.months:
        for flow in month.flows:
            if flow.amount_chf == 0:
                notes.setdefault(re.sub(r"\d+", "#", flow.label), []).append(i18n.ledger(flow.label))
    for labels in notes.values():
        origin = say("Note of the ledger", "Note du registre")
        facts.append(Quote(labels[0], origin, world))
        facts += facts_in(labels[0], origin, world)
        facts.append(Fact.months(len(labels), say(f"Months with the note “{labels[0]}”", f"Mois avec la note « {labels[0]} »"), world))
    return facts


# ----------------------------------------------------------------------------------------------- the explanations
def _schema(worlds: list[str]) -> dict:
    return {"type": "object", "additionalProperties": False, "required": ["explanations"],
            "properties": {"explanations": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["world", "text"],
                "properties": {"world": {"type": "string", "enum": worlds}, "text": {"type": "string"}}}}}}


def _listed(facts: list[Fact | Quote]) -> list[str]:
    """Facts as the model is shown them: where each comes from, then the figure as it must be copied."""
    quoted = {fact.origin for fact in facts if isinstance(fact, Quote)}
    lines = []
    for fact in facts:
        if isinstance(fact, Quote):
            lines.append(f"- {fact.origin} ({say('quote', 'citation')}): “{fact.text}”")
        elif fact.origin not in quoted:                 # the numbers of a quoted sentence are shown once, inside the sentence
            lines.append(f"- {fact.origin}: {fact.written()}")
    return list(dict.fromkeys(lines))


def explain(route: Route, model: Model, ranked: list[dict], lang: str) -> tuple[dict[str, Outcome], dict[str, list], dict]:
    """One or two sentences per world, written by the model and checked against the facts of that world. Returns what
    became of each text, the facts of each world, and the tokens used."""
    usage: Counter = Counter()
    with i18n.use(lang):
        worlds = [summary["world"] for summary in ranked]
        if not worlds:                                  # nothing breaks the route among what was tested: nothing to explain
            return {}, {}, dict(usage)
        common, facts = common_facts(route), {world: world_facts(route, world) for world in worlds}
        system = EXPLAIN.format(**WORDS[lang])
        asked = [say("Explain these worlds, one or two sentences each.", "Explique ces mondes, une ou deux phrases pour chacun."), ""]
        for summary in ranked:
            asked += [f"{say('World', 'Monde')} {summary['world']}: {route.name(summary['world'])}", *_listed(facts[summary["world"]]), ""]
        asked += [say("Figures common to every world", "Chiffres communs à tous les mondes"), *_listed(common)]
        messages: list[dict] = []

        def write(feedback: dict[str, str] | None) -> dict[str, str]:
            if feedback is None:
                messages.append({"role": "user", "content": "\n".join(asked)})
            else:
                again = [say("The checker refused these texts. Write them again, and only them.",
                             "Le contrôleur a refusé ces textes. Récris-les, et seulement eux."), ""]
                for world, refusal in feedback.items():
                    again += [f"{say('World', 'Monde')} {world}", refusal, ""]
                messages.append({"role": "user", "content": "\n".join(again).strip()})
            reply = model.reply(system=system, messages=messages, tools=[], output=_schema(worlds), effort="medium")
            usage.update({key: value for key, value in reply.usage.items() if isinstance(value, (int, float))})
            if reply.stop_reason == "refusal":                           # nothing of a declined answer goes into the conversation
                return {}
            if reply.content:
                messages.append({"role": "assistant", "content": list(reply.content)})
            try:
                written = json.loads(reply.text())["explanations"]
                return {item["world"]: item["text"] for item in written if isinstance(item.get("text"), str)}
            except (ValueError, KeyError, TypeError, AttributeError):        # not the JSON that was asked: no text at all
                return {}

        identifiers = [crisis["id"] for world in worlds for crisis in W.crises(route.th, world, route.h, route.age0)] + worlds
        outcomes = supervise(write, facts, common, identifiers, lang)
    return outcomes, facts, dict(usage)


# ---------------------------------------------------------------------------------- what the engine adds on its own
def signposts(route: Route, world: str, lost: list[str]) -> list[dict]:
    """The signposts to watch for the goals lost in a world: the engine's own sentences, computed between this world
    and the reference world. None may exist: the list is then empty."""
    rows = route.tree.pathways_view(route.path, 0, route.overrides, ["reference", world])["by_world"][world]["doors"]
    goals = route.goals()
    return [{"goal": row["key"], "name": goals[row["key"]]["name"], "text": row["signpost"]["text"], "age": route.tree.age(row["signpost"]["gare_month"]),
             "threshold_chf": row["signpost"]["threshold_chf"], "last_transfer": row["last_transfer"]}
            for row in rows if row["key"] in lost and row["signpost"]]


def verify(route: Route, best: dict | None) -> dict:
    """The engine checks the search as far as it can while Alexia waits: it simulates every single crisis of the space
    and says whether one of them is harder than what the model found, or as hard and milder."""
    measured = [route.measure(world) for world in V.singles(route.th, route.h, route.age0)]
    most = max(len(summary["goals_lost"]) for summary in measured)
    hardest = rank(summary for summary in measured if len(summary["goals_lost"]) == most)      # the mildest of each type, hardest first
    found = len(best["goals_lost"]) if best else 0
    return {"scanned": len(measured), "max_goals_lost": most, "hardest": [route.shown(summary) for summary in hardest],
            "harder_than_found": most > found,
            "as_hard_and_milder": bool(best) and most == found and bool(hardest) and hardest[0]["severity"] < best["severity"]}


def run(tree: Tree, path: list[dict], model: Model, overrides: dict | None = None, lang: str | None = None,
        truth: dict | None = None) -> dict:
    """The whole stress test of a route. `truth`: for a route of the benchmark, the answer of the full scan made
    offline (ai/benchmark.py); the result then says whether the search found a world as hard."""
    lang = lang or i18n.current()
    route = Route(Tree(tree.sc), path, overrides)      # a tree of its own: nothing of this search stays in the application's memory
    found = search(route, model)
    ranked = rank(found["tested"].values())
    outcomes, facts, usage = explain(route, model, ranked, lang)
    with i18n.use(lang):
        ranking = []
        for summary in ranked:
            world, outcome = summary["world"], outcomes[summary["world"]]
            ranking.append({**route.shown(summary), "explanation": outcome.as_dict(),
                            "facts": [{"origin": fact.origin, "written": fact.text if isinstance(fact, Quote) else fact.written(),
                                       "quote": isinstance(fact, Quote), "headline": index < HEADLINE}
                                      for index, fact in enumerate(facts[world])],
                            "signposts": signposts(route, world, summary["goals_lost"])})
        best = ranked[0] if ranked else None
        checked = {"single_crises": verify(route, best), "benchmark": None}
        if truth is not None:
            checked["benchmark"] = {**truth, "found": bool(best) and len(best["goals_lost"]) >= truth["max_goals_lost"]}
        tested = [route.shown(summary) for summary in found["tested"].values()]
        space = V.describe(route.th, route.h, route.age0)
        return {"path": route.path, "language": lang, "model": model.name, "space": space,
                "budget": {"calls": CALLS, "worlds_per_call": PER_CALL, "worlds": CALLS * PER_CALL, "calls_used": len(found["calls"]),
                           "worlds_tested": len(tested)},
                "calm": {"goals_kept": sum(route.calm_goals.values()), "goals_total": len(route.calm_goals),
                         "peak_financing_chf": round(route.calm.peak_financing_chf, 2), "net_worth_end_chf": round(route.calm.net_worth_end_chf, 2)},
                "calls": found["calls"], "tested": tested, "ranking": ranking, "verification": checked, "stopped": found["stopped"],
                "rejected_label": rejected_label(),
                "usage": {key: found["usage"].get(key, 0) + usage.get(key, 0) for key in sorted(set(found["usage"]) | set(usage))}}
