"""What the model may propose: the search space of the stress test, read from the engine.

A world holds one crisis or two. A crisis is a type, an age and a severity. The types and the ages are the engine's
(engine/worlds.py). The severities are a grid of five levels, so that the space can be counted and scanned:
7 types x 9 ages x 5 severities = 315 single crises, and 48,825 pairs of them. 49,140 worlds per route.

Nothing here simulates anything: this module only says which worlds exist and how they are written.
"""
from __future__ import annotations

from itertools import combinations
from typing import Iterator

from engine import english
from engine import worlds as W
from engine.assumptions import by_key
from engine.i18n import say

SEVERITIES = (50, 75, 100, 125, 150)        # in percent of the crisis of the catalogue


def kinds(th: dict, horizon: int, age0: int) -> tuple[str, ...]:
    """The types of crisis: every named world of the engine that has an age. The reference world and the cautious
    world are whole worlds, not crises."""
    return tuple(world.id for world in W.WORLDS + W.EXTRA if W.default_age(th, world.id, horizon, age0) is not None)


def written(kind: str, age: int, severity: int = 100) -> str:
    """A crisis written in full: krach@24, chomage_long@27~150."""
    return f"{kind}@{age}" + ("" if severity == 100 else f"~{severity}")


def singles(th: dict, horizon: int, age0: int) -> list[str]:
    """Every single crisis of the space, written in full, in the order the engine sorts the crises of a world: by age,
    then by type."""
    low, high = W.ages(horizon, age0)
    return [written(kind, age, severity) for age in range(low, high + 1) for kind in sorted(kinds(th, horizon, age0))
            for severity in SEVERITIES]


def pairs(th: dict, horizon: int, age0: int) -> Iterator[str]:
    """Every world with two crises, under the identifier the engine gives it. The same type at the same age twice is not
    a pair: it would be a severity."""
    for first, second in combinations(singles(th, horizon, age0), 2):
        if first.partition("~")[0] != second.partition("~")[0]:
            yield f"{first}+{second}"


def worlds(th: dict, horizon: int, age0: int) -> Iterator[str]:
    """The whole space: the single crises, then the pairs."""
    yield from singles(th, horizon, age0)
    yield from pairs(th, horizon, age0)


def size(th: dict, horizon: int, age0: int) -> int:
    """How many worlds the space holds, counted and not listed."""
    low, high = W.ages(horizon, age0)
    places, levels = len(kinds(th, horizon, age0)) * (high - low + 1), len(SEVERITIES)
    one = places * levels
    return one + one * (one - 1) // 2 - places * levels * (levels - 1) // 2


def accept(asked, th: dict, horizon: int, age0: int) -> str:
    """The identifier of a world of the space, as the engine writes it. Raises the engine's own refusal (an age outside
    the junctions, three crises, an unknown type) or, for a world the engine knows but the search does not cover, says why."""
    if not isinstance(asked, str) or not asked.strip():
        raise ValueError(say("A world is written as text: type@age~severity, or two of them joined by “+”.",
                             "Un monde s'écrit en texte : type@âge~gravité, ou deux d'entre eux reliés par « + »."))
    try:
        world = W.canonical(asked.strip(), th, horizon, age0)
    except KeyError as unknown:                      # the engine's list names its seven usual worlds: the search has its own types
        known = ", ".join(kinds(th, horizon, age0))
        raise ValueError(say(f"{unknown.args[0].split('.')[0]}. Types of crisis: {known}.",
                             f"{unknown.args[0].split('.')[0]}. Types de crise : {known}.")) from None
    crises = W.crises(th, world, horizon, age0)
    if not crises:
        raise ValueError(say(f"“{asked.strip()}” is a whole world, not a crisis: the search covers worlds with one crisis or two.",
                             f"« {asked.strip()} » est un monde entier, pas une crise : la recherche porte sur les mondes à une ou deux crises."))
    for crisis in crises:
        if crisis["gravity"] not in SEVERITIES:
            levels = ", ".join(str(level) for level in SEVERITIES)
            raise ValueError(say(f"The search covers five severities: {levels}. {crisis['gravity']} is not one of them.",
                                 f"La recherche porte sur cinq gravités : {levels}. {crisis['gravity']} n'en fait pas partie."))
    return world


def severity(world: str) -> int:
    """The total severity of a world, read in its identifier: the sum of the severities of its crises (100 when none is
    written). The lower, the milder the world."""
    return sum(int(crisis.partition("~")[2] or 100) for crisis in world.split("+"))


def types(world: str) -> tuple[str, ...]:
    """The types of crisis a world combines, read in its identifier, whatever their ages and severities."""
    return tuple(sorted(crisis.partition("~")[0].partition("@")[0] for crisis in world.split("+")))


# ------------------------------------------------------------------ what Alexia says, and what the engine counts
# How the size of a crisis is said, by the quantity of the world it moves. A job loss has a length; a crash, a surge in
# prices and a fall in home prices have a size in percent; the franc has a rate. Code converts: the model never does.
_SAID = {"job_lost": "months", "student_job_lost": "months", "market_return_monthly": "percent", "cost_index": "percent",
         "house_return_monthly": "percent", "fx_chf_per_eur": "chf_per_eur"}


def countable(value) -> bool:
    """A number one can count with: not a truth value, not a text, neither infinite nor beyond any amount of this model."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and abs(value) < 1e15


def _line(th: dict, crisis: str, horizon: int, age0: int) -> dict:
    """The one quantity a crisis moves, as the engine describes it: its field, its value, the value of the reference
    world, and for how many months."""
    lines = W.describe(th, horizon, age0, [crisis])[0]["parameters"]
    if len(lines) != 1 or lines[0]["field"] not in _SAID:
        raise ValueError(say(f"The size of “{crisis}” cannot be set in words: set its severity in percent.",
                             f"La taille de « {crisis} » ne se règle pas en mots : règle sa gravité en pour cent."))
    return lines[0]


def magnitude(th: dict, crisis: str, horizon: int, age0: int) -> tuple[float, str]:
    """The size of a crisis as Alexia would say it, read in the world the engine builds, and its unit: 6 months of
    unemployment, a fall of 30 percent, home prices 20 percent lower after two years, an euro at 1.05 francs."""
    line = _line(th, crisis, horizon, age0)
    field, value = line["field"], line["value"]
    if isinstance(value, bool):
        return float(line["months"]), "months"
    if field == "market_return_monthly":
        return round(-value * 100, 1), "percent"
    if field == "cost_index":
        return round((value - 1) * 100, 1), "percent"
    if field == "house_return_monthly":
        return round((1 - (1 + value) ** line["months"]) * 100, 1), "percent"
    return round(value, 2), "chf_per_eur"


def severity_for(kind: str, said: float, unit: str, th: dict, horizon: int, age0: int) -> int:
    """The severity of a crisis, in percent of the crisis of the catalogue, for a size given in Alexia's words: "9 months"
    of unemployment is 150 for the six-month crisis, and "a year" is 200. The engine scales the gap between the crisis
    and the reference world; this function finds the scale that gives the size asked. The engine then says whether it
    accepts it. `unit`: months, years, percent, chf_per_eur, or none when she gives a bare number."""
    line = _line(th, kind, horizon, age0)
    field, value, usual, months = line["field"], line["value"], line["reference"], line["months"]
    expected = _SAID[field]
    if not countable(said):
        raise ValueError(say("The size of a crisis is a number.", "La taille d'une crise est un nombre."))
    if unit == "years" and expected == "months":
        said, unit = said * 12, "months"                                # a length said in years
    if unit not in (expected, "none"):
        names = {"months": say("a length, in months or in years", "une durée, en mois ou en années"),
                 "percent": say("a size in percent", "une taille en pour cent"),
                 "chf_per_eur": say("a rate in francs per euro", "un cours en francs par euro")}
        name = W.name_of(next(world for world in W.WORLDS + W.EXTRA if world.id == kind))
        raise ValueError(say(f"“{name}” is set by {names[expected]}.", f"« {name} » se règle par {names[expected]}."))
    if isinstance(value, bool):
        scale = said / months
    else:
        if field == "market_return_monthly":
            target = -abs(said) / 100                                   # a fall of this size in the month
        elif field == "cost_index":
            target = 1 + abs(said) / 100                                # prices this much higher
        elif field == "house_return_monthly":
            if abs(said) >= 100:
                raise ValueError(say("Home prices cannot fall by 100 percent or more.", "Le prix des logements ne peut pas baisser de 100 pour cent ou plus."))
            target = (1 - abs(said) / 100) ** (1 / months) - 1          # the monthly fall that adds up to this size over the crisis
        else:
            target = said                                               # the euro at this rate
        scale = (target - usual) / (value - usual)
    return round(100 * scale)


def stored(assumption, said: float, unit: str) -> float:
    """The value of an assumption as the engine stores it, for a value given in Alexia's words: "5 %" is 0.05. A share is
    stored as a share and said in percent; everything else is stored as it is said. A bare number is in the unit of the
    drawer. `assumption`: an entry of engine.assumptions.ASSUMPTIONS, whose unit is the engine's own. `unit`: chf, eur,
    percent, months, years, or none."""
    family = ("percent" if assumption.unit.startswith("%") else "chf" if assumption.unit.startswith("CHF") else "eur"
              if assumption.unit.startswith("EUR") else "months" if assumption.unit.startswith("mois") else "years"
              if assumption.unit.startswith("ans") else "none")
    if not countable(said):
        raise ValueError(say("The value of an assumption is a number.", "La valeur d'une hypothèse est un nombre."))
    if unit not in (family, "none"):
        shown = by_key()[assumption.key]                                # its label and its unit, in the language of the screen
        names = {"percent": say("percent", "pour cent"), "chf": say("francs", "francs"), "eur": say("euros", "euros"),
                 "months": say("months", "mois"), "years": say("years", "ans")}
        # Only a unit of the form is named: a text that is not one of them is not written back.
        other = say(f", not in {names[unit]}", f", pas en {names[unit]}") if isinstance(unit, str) and unit in names else ""
        raise ValueError(say(f"“{shown.label}” is counted in {shown.unit}{other}.", f"« {shown.label} » se compte en {shown.unit}{other}."))
    return said / 100 if family == "percent" else float(said)


def describe(th: dict, horizon: int, age0: int) -> dict:
    """The space as it is told to the model and to the screen: the types with their names, the ages, the severities,
    and how many worlds that makes."""
    low, high = W.ages(horizon, age0)
    named = {world.id: world for world in W.WORLDS + W.EXTRA}
    said = {kind: magnitude(th, kind, horizon, age0) for kind in kinds(th, horizon, age0)}
    return {"types": [{"id": kind, "name": W.name_of(named[kind]), "description": say(english.WORLDS[kind][1], named[kind].description),
                       "usual_age": W.default_age(th, kind, horizon, age0), "usual_size": said[kind][0], "unit": said[kind][1]}
                      for kind in kinds(th, horizon, age0)],
            "ages": [low, high], "severities": list(SEVERITIES), "crises_per_world": W.MAX_CRISES, "worlds": size(th, horizon, age0)}
