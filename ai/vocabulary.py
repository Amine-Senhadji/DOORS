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


def describe(th: dict, horizon: int, age0: int) -> dict:
    """The space as it is told to the model and to the screen: the types with their names, the ages, the severities,
    and how many worlds that makes."""
    low, high = W.ages(horizon, age0)
    named = {world.id: world for world in W.WORLDS + W.EXTRA}
    return {"types": [{"id": kind, "name": W.name_of(named[kind]), "description": say(english.WORLDS[kind][1], named[kind].description),
                       "usual_age": W.default_age(th, kind, horizon, age0)} for kind in kinds(th, horizon, age0)],
            "ages": [low, high], "severities": list(SEVERITIES), "crises_per_world": W.MAX_CRISES, "worlds": size(th, horizon, age0)}
