"""Les mondes nommés (w_t) : le monde de référence et quelques crises, pour « Info trafic ».

Une crise est un type et un âge : « krach@25 » est le krach du catalogue, déplacé pour commencer à 25 ans.
Sans âge, « krach » est la crise à son âge d'origine. Une variante de test peut aussi changer sa gravité :
« krach@24~133 » est le même krach, un tiers plus fort (l'écart au monde de référence est mis à l'échelle). Déplacer une crise, c'est décaler d'un nombre entier d'années
le monde du catalogue (engine/catalog.py) : aucun paramètre n'est écrit ici. Seule exception, la perte du job
étudiant : une crise de l'équipe, absente du catalogue du défi, dont la durée est une hypothèse affichée.
Aucun monde n'est présenté comme probable. Le choc du franc de type 2015 n'est pas encore écrit : le catalogue
ne contient que le mouvement inverse (S028).
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace

from engine.catalog import ALEXIA, SPECS, build_world, cautious, job_long, student_job
from engine.contract import World
from engine.simulate import reference_world

AGE0 = ALEXIA.profile.age


@dataclass(frozen=True)
class NamedWorld:
    id: str                         # le type de la crise
    catalog_id: str | None          # le scénario du catalogue du défi dont il reprend les modificateurs
    name: str
    description: str
    mods: tuple = ()                # pour une crise de l'équipe, absente du catalogue : ses modificateurs
    movable: bool = True            # une crise a un âge et une gravité ; un monde entier (référence, prudent) n'en a pas


WORLDS: tuple[NamedWorld, ...] = (
    NamedWorld("reference", None, "Monde de référence",
               "Rien d'exceptionnel : rendement moyen des placements, prix stables, pas de perte d'emploi."),
    NamedWorld("krach", "S065", "Krach des marchés", "Les placements chutent brutalement, en un mois."),
    NamedWorld("chomage_6_mois", "S014", "Six mois de chômage", "Perte d'emploi pendant six mois, pour qui a un emploi à ce moment-là."),
    NamedWorld("perte_job_etudiant", None, "Perte du job étudiant",
               "Le job étudiant s'arrête pendant quelques mois, sans indemnité, pour qui étudie avec un job à ce moment-là.",
               mods=(student_job(60),)),
    NamedWorld("inflation", "S101", "Poussée d'inflation", "Les prix montent, sans rattrapage des salaires."),
    NamedWorld("crise_immobiliere", "S108", "Crise immobilière", "Le prix des logements baisse pendant deux ans."),
    NamedWorld("franc_faible", "S028", "Franc plus faible",
               "Le franc s'affaiblit face à l'euro. Le choc inverse, de type 2015, n'est pas encore écrit dans le moteur."),
)
WORLD_IDS = tuple(w.id for w in WORLDS)
# Des types en plus, qu'on peut demander par leur nom mais qui ne sont pas testés par défaut ni affichés dans « Info trafic ».
EXTRA: tuple[NamedWorld, ...] = (
    NamedWorld("chomage_long", None, "Chômage long",
               "Perte d'emploi pendant douze mois, pour qui a un emploi à ce moment-là : une seule crise, longue.",
               mods=(job_long(48),)),
)
EXTRA += (
    NamedWorld("prudent", None, "Monde prudent",
               "Le monde de référence, avec un rendement des placements plus bas chaque année. Ni une crise, ni une prévision.",
               mods=(cautious(),), movable=False),
)
GRAVITY = (25, 300)        # la gravité d'une variante, en pour cent de celle du catalogue
FIELD_LABELS = {"market_return_monthly": "Rendement des placements, par mois", "inflation_monthly": "Inflation, par mois",
                "fx_chf_per_eur": "Cours de l'euro, en francs", "job_lost": "Perte d'emploi",
                "cost_index": "Niveau des prix (1 dans le monde de référence)", "rate_shift": "Hausse des taux d'intérêt",
                "house_return_monthly": "Évolution du prix des logements, par mois", "student_job_lost": "Job étudiant perdu"}


def split(world_id) -> tuple[str, int | None]:
    """« krach@25 » ou { "type": "krach", "age": 25 } : le type, et l'âge demandé (None : l'âge d'origine)."""
    if isinstance(world_id, dict):
        if "type" not in world_id:
            raise ValueError("Une crise se décrit par un type et un âge : { \"type\": \"krach\", \"age\": 25 }.")
        kind, age = str(world_id["type"]), world_id.get("age")
    else:
        kind, _, age = str(world_id).partition("~")[0].partition("@")
        age = age or None
    if age is None:
        return kind, None
    try:
        if float(age) != int(float(age)):
            raise ValueError
        return kind, int(float(age))
    except (TypeError, ValueError):
        raise ValueError(f"L'âge d'une crise est un nombre entier d'années : « {age} » n'en est pas un.") from None


def gravity(world_id) -> int:
    """La gravité demandée, en pour cent de celle du catalogue : « krach@24~133 » → 133. Sans mention : 100."""
    asked = world_id.get("gravite") if isinstance(world_id, dict) else (str(world_id).partition("~")[2] or None)
    if asked is None:
        return 100
    try:
        value = int(float(asked))
    except (TypeError, ValueError):
        raise ValueError(f"La gravité d'une crise est un nombre, en pour cent : « {asked} » n'en est pas un.") from None
    if not GRAVITY[0] <= value <= GRAVITY[1]:
        raise ValueError(f"La gravité d'une crise se règle de {GRAVITY[0]} à {GRAVITY[1]} % : {value} % est refusé.")
    return value


def named(world_id) -> NamedWorld:
    kind = split(world_id)[0]
    world = next((w for w in WORLDS + EXTRA if w.id == kind), None)
    if world is None:
        raise KeyError(f"Monde « {kind} » pas encore disponible. Mondes : {list(WORLD_IDS)}")
    return world


def _original(th: dict, world: NamedWorld, percent: int = 100) -> list[World]:
    """La crise telle que le catalogue l'écrit, à son âge d'origine, sur toute la durée du catalogue.
    `percent` : sa gravité. L'écart au monde de référence est mis à l'échelle : une grandeur chiffrée s'écarte
    plus ou moins ; une crise « oui ou non » (perte d'emploi) dure plus ou moins longtemps."""
    mods = next(s for s in SPECS if s.id == world.catalog_id).world_int if world.catalog_id is not None else world.mods
    built = build_world(th, mods)
    if percent == 100:
        return built
    k, reference, out = percent / 100, reference_world(th, len(built)), list(built)
    for field in fields(World):
        gap = [t for t in range(len(built)) if getattr(built[t], field.name) != getattr(reference[t], field.name)]
        if not gap:
            continue
        if isinstance(getattr(reference[0], field.name), bool):
            keep = set(range(gap[0], min(len(built), gap[0] + max(1, round(len(gap) * k)))))
            for t in range(gap[0], len(built)):
                normal = getattr(reference[t], field.name)
                out[t] = replace(out[t], **{field.name: (not normal) if t in keep else normal})
        else:
            for t in gap:
                normal = getattr(reference[t], field.name)
                out[t] = replace(out[t], **{field.name: normal + k * (getattr(built[t], field.name) - normal)})
    return out


def _first_gap(th: dict, built: list[World], horizon: int) -> int | None:
    reference = reference_world(th, len(built))
    return next((t for t in range(min(horizon, len(built))) if built[t] != reference[t]), None)


def default_age(th: dict, world_id, horizon: int, age0: int = AGE0) -> int | None:
    """L'âge d'origine d'une crise : l'année de vie où elle commence dans le catalogue. None pour le monde de référence."""
    world = named(world_id)
    start = _first_gap(th, _original(th, world), horizon) if world.movable else None
    return None if start is None else age0 + start // 12


def ages(horizon: int, age0: int = AGE0) -> tuple[int, int]:
    """Les âges où une crise peut commencer : ceux des gares, de la première à la dernière."""
    return age0 + 1, age0 + horizon // 12 - 1


def canonical(world_id, th: dict, horizon: int, age0: int = AGE0) -> str:
    """L'identifiant d'un monde : son type seul à l'âge d'origine, sinon « type@âge ». Refuse un âge hors des gares."""
    world, (_, age), percent = named(world_id), split(world_id), gravity(world_id)
    original = default_age(th, world.id, horizon, age0)
    strength = "" if percent == 100 else f"~{percent}"
    if original is None and (age is not None or strength):
        raise ValueError(f"« {world.name} » n'a ni âge ni gravité : ce n'est pas une crise.")
    if age is None or age == original:
        return world.id + strength
    low, high = ages(horizon, age0)
    if not low <= age <= high:
        raise ValueError(f"L'âge d'une crise se règle de {low} à {high} ans : {age} ans est refusé.")
    return f"{world.id}@{age}{strength}"


def build(th: dict, world_id, horizon: int, age0: int = AGE0) -> list[World]:
    """Le monde demandé, mois par mois, avec les hypothèses en cours. À un autre âge que celui d'origine, c'est le même
    monde décalé d'un nombre entier d'années : avant, le monde de référence ; au-delà du catalogue, son dernier mois."""
    world, (_, age) = named(world_id), split(world_id)
    built = _original(th, world, gravity(world_id))
    original = default_age(th, world.id, horizon, age0)
    if age is None or original is None or age == original:
        return built[:horizon]
    canonical(world_id, th, horizon, age0)
    shift, reference = (age - original) * 12, reference_world(th, horizon)
    return [reference[t] if t < shift else built[min(t - shift, len(built) - 1)] for t in range(horizon)]


def shock_start(th: dict, world_id, horizon: int, age0: int = AGE0) -> int | None:
    """Le premier mois où ce monde s'écarte du monde de référence. None pour le monde de référence."""
    return _first_gap(th, build(th, world_id, horizon, age0), horizon)


def asked(mondes, th: dict | None = None, horizon: int | None = None, age0: int = AGE0) -> tuple[str, ...]:
    """Les mondes à tester : tous par défaut, ou une liste. Chaque élément est un nom (« krach », « krach@25 ») ou
    un type et un âge ({ "type": "krach", "age": 25 }). Le tirage au hasard viendra plus tard."""
    if mondes is None:
        return WORLD_IDS
    if isinstance(mondes, dict):
        raise KeyError("Le tirage au hasard de mondes n'est pas encore disponible : mondes nommés seulement.")
    if th is None or horizon is None:
        for world_id in mondes:
            named(world_id)
        return tuple(mondes)
    out: list[str] = []
    for world_id in mondes:
        world = canonical(world_id, th, horizon, age0)
        if world not in out:
            out.append(world)
    if not out:
        raise ValueError("Il faut au moins un monde à tester.")
    return tuple(out)


def describe(th: dict, horizon: int, age0: int, mondes=None) -> list[dict]:
    """Chaque monde, avec ce qui le distingue du monde de référence, lu mois par mois dans ses données.
    `mondes` : les mondes à décrire, avec l'âge choisi pour chaque crise (tous, à leur âge d'origine, par défaut)."""
    reference, out = reference_world(th, horizon), []
    low, high = ages(horizon, age0)
    for world_id in asked(mondes, th, horizon, age0):
        world, age = named(world_id), split(world_id)[1]
        built, parameters = build(th, world_id, horizon, age0), []
        for field in fields(World):
            months = [t for t in range(horizon) if getattr(built[t], field.name) != getattr(reference[t], field.name)]
            if months:
                first, last = months[0], months[-1]
                parameters.append({"field": field.name, "label": FIELD_LABELS.get(field.name, field.name),
                                   "from_month": first, "to_month": last + 1, "months": len(months),
                                   "from_age": age0 + first / 12, "to_age": age0 + (last + 1) / 12,
                                   "value": getattr(built[last], field.name), "reference": getattr(reference[last], field.name)})
        original = default_age(th, world.id, horizon, age0)
        out.append({"id": world_id, "type": world.id, "name": world.name, "description": world.description,
                    "gravity": gravity(world_id),
                    "catalog_id": world.catalog_id, "age": age if age is not None else original, "default_age": original,
                    "adjustable": original is not None, "min_age": low, "max_age": high, "parameters": parameters})
    return out
