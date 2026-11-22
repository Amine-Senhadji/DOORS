"""Les mondes nommés (w_t) : le monde de référence et quelques crises, pour « Info trafic ».

Une crise est un type et un âge : « krach@25 » est le krach du catalogue, déplacé pour commencer à 25 ans.
Sans âge, « krach » est la crise à son âge d'origine. Une variante de test peut aussi changer sa gravité :
« krach@24~133 » est le même krach, un tiers plus fort (l'écart au monde de référence est mis à l'échelle). Déplacer une crise, c'est décaler d'un nombre entier d'années
le monde du catalogue (engine/catalog.py) : aucun paramètre n'est écrit ici. Seule exception, la perte du job
étudiant : une crise de l'équipe, absente du catalogue du défi, dont la durée est une hypothèse affichée.
Aucun monde n'est présenté comme probable. Le choc du franc de type 2015 n'est pas encore écrit : le catalogue
ne contient que le mouvement inverse (S028).

Un monde peut contenir deux crises : « krach@24+chomage_long@25 ». Chacune s'écrit comme une crise seule, et l'ordre
ne compte pas. Le monde combiné est construit champ par champ et mois par mois, sur l'écart de chaque crise au monde
de référence : là où une seule crise s'écarte, sa valeur telle quelle ; là où les deux s'écartent, la somme des écarts
pour un nombre, « oui » pour un champ oui ou non. Le moteur simule ensuite ce monde : aucun résultat n'est additionné.
Un identifiant à une seule crise ne passe par aucune de ces lignes.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace

from engine.catalog import ALEXIA, SPECS, build_world, cautious, job_long, student_job
from engine import english
from engine.contract import World
from engine.i18n import say
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
MAX_CRISES = 2             # un monde contient une crise, ou deux crises combinées
FIELD_LABELS = {"market_return_monthly": "Rendement des placements, par mois", "inflation_monthly": "Inflation, par mois",
                "fx_chf_per_eur": "Cours de l'euro, en francs", "job_lost": "Perte d'emploi",
                "cost_index": "Niveau des prix (1 dans le monde de référence)", "rate_shift": "Hausse des taux d'intérêt",
                "house_return_monthly": "Évolution du prix des logements, par mois", "student_job_lost": "Job étudiant perdu"}


def name_of(world: NamedWorld) -> str:
    """Le nom d'un monde, dans la langue courante."""
    return say(english.WORLDS[world.id][0], world.name)


def combined(world_id) -> bool:
    """Un monde combiné : plusieurs crises dans le même monde, reliées par « + » (« krach@24+chomage_long@25 »)."""
    return not isinstance(world_id, dict) and "+" in str(world_id)


def terms(world_id) -> tuple:
    """Les crises écrites dans un identifiant, dans l'ordre où elles sont écrites : une seule, ou plusieurs reliées par « + »."""
    if not combined(world_id):
        return (world_id,)
    parts = tuple(part.strip() for part in str(world_id).split("+"))
    if not all(parts):
        raise ValueError(say(f"A combined world is written as two crises joined by “+”: one is missing in “{world_id}”.",
                             f"Un monde combiné s'écrit avec deux crises reliées par « + » : il en manque une dans « {world_id} »."))
    return parts


def _one_crisis(world_id) -> None:
    """Un type, un âge et une gravité se lisent crise par crise : un monde combiné est refusé là où une seule crise est attendue."""
    if combined(world_id):
        raise ValueError(say(f"“{world_id}” combines several crises: a type, an age and a severity are read one crisis at a time.",
                             f"« {world_id} » combine plusieurs crises : un type, un âge et une gravité se lisent une crise à la fois."))


def split(world_id) -> tuple[str, int | None]:
    """« krach@25 » ou { "type": "krach", "age": 25 } : le type, et l'âge demandé (None : l'âge d'origine)."""
    _one_crisis(world_id)
    if isinstance(world_id, dict):
        if "type" not in world_id:
            raise ValueError(say('A crisis is described by a type and an age: { "type": "krach", "age": 25 }.',
                                 'Une crise se décrit par un type et un âge : { "type": "krach", "age": 25 }.'))
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
        raise ValueError(say(f"The age of a crisis is a whole number of years: “{age}” is not one.",
                             f"L'âge d'une crise est un nombre entier d'années : « {age} » n'en est pas un.")) from None


def gravity(world_id) -> int:
    """La gravité demandée, en pour cent de celle du catalogue : « krach@24~133 » → 133. Sans mention : 100."""
    _one_crisis(world_id)
    asked = world_id.get("gravite") if isinstance(world_id, dict) else (str(world_id).partition("~")[2] or None)
    if asked is None:
        return 100
    try:
        value = int(float(asked))
    except (TypeError, ValueError):
        raise ValueError(say(f"The severity of a crisis is a number, in percent: “{asked}” is not one.",
                             f"La gravité d'une crise est un nombre, en pour cent : « {asked} » n'en est pas un.")) from None
    if not GRAVITY[0] <= value <= GRAVITY[1]:
        raise ValueError(say(f"The severity of a crisis can be set from {GRAVITY[0]} to {GRAVITY[1]}%: {value}% is refused.",
                             f"La gravité d'une crise se règle de {GRAVITY[0]} à {GRAVITY[1]} % : {value} % est refusé."))
    return value


def named(world_id) -> NamedWorld:
    kind = split(world_id)[0]
    world = next((w for w in WORLDS + EXTRA if w.id == kind), None)
    if world is None:
        raise KeyError(say(f"World “{kind}” not available yet. Worlds: {list(WORLD_IDS)}",
                           f"Monde « {kind} » pas encore disponible. Mondes : {list(WORLD_IDS)}"))
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


def _crisis_ids(world_id, th: dict, horizon: int, age0: int = AGE0) -> tuple[str, ...]:
    """Les crises d'un monde, chacune écrite en entier (« krach@23 », même à son âge d'origine), rangées par âge de début
    puis par type. Aucune pour un monde entier (référence, prudent). Dans un monde combiné, sont refusés : plus de deux
    crises, un monde entier, et deux fois le même type au même âge (ce serait une gravité, pas deux crises)."""
    parts = terms(world_id)
    in_full = lambda kind, age, percent: f"{kind}@{age}" + ("" if percent == 100 else f"~{percent}")
    if len(parts) == 1:
        one = canonical(parts[0], th, horizon, age0)
        home = default_age(th, named(one).id, horizon, age0)
        return () if home is None else (in_full(named(one).id, split(one)[1] or home, gravity(one)),)
    if len(parts) > MAX_CRISES:
        raise ValueError(say(f"A world holds at most {MAX_CRISES} crises: “{world_id}” has {len(parts)}.",
                             f"Un monde contient au plus {MAX_CRISES} crises : « {world_id} » en a {len(parts)}."))
    found = []
    for part in parts:
        world = named(part)
        home = default_age(th, world.id, horizon, age0)
        if home is None:
            raise ValueError(say(f"“{name_of(world)}” is a whole world, not a crisis: it cannot be combined with one.",
                                 f"« {world.name} » est un monde entier, pas une crise : il ne se combine pas avec une crise."))
        one = canonical(part, th, horizon, age0)               # l'âge et la gravité sont vérifiés comme pour une crise seule
        age = split(one)[1] or home
        found.append((age, world.id, in_full(world.id, age, gravity(one))))
    if len({(age, kind) for age, kind, _ in found}) < len(found):
        raise ValueError(say(f"A world cannot hold the same crisis twice at the same age (“{world_id}”): "
                             "that would be a severity, not two crises.",
                             f"Un monde ne peut pas contenir deux fois la même crise au même âge (« {world_id} ») : "
                             "ce serait une gravité, pas deux crises."))
    return tuple(one for _, _, one in sorted(found))


def canonical(world_id, th: dict, horizon: int, age0: int = AGE0) -> str:
    """L'identifiant d'un monde : son type seul à l'âge d'origine, sinon « type@âge ». Refuse un âge hors des gares.
    Un monde combiné : ses deux crises, chacune écrite avec son âge, rangées par âge de début puis par type."""
    if combined(world_id):
        return "+".join(_crisis_ids(world_id, th, horizon, age0))
    world, (_, age), percent = named(world_id), split(world_id), gravity(world_id)
    original = default_age(th, world.id, horizon, age0)
    strength = "" if percent == 100 else f"~{percent}"
    if original is None and (age is not None or strength):
        raise ValueError(say(f"“{name_of(world)}” has neither an age nor a severity: it is not a crisis.",
                             f"« {world.name} » n'a ni âge ni gravité : ce n'est pas une crise."))
    if age is None or age == original:
        return world.id + strength
    low, high = ages(horizon, age0)
    if not low <= age <= high:
        raise ValueError(say(f"The age of a crisis can be set from {low} to {high}: {age} is refused.",
                             f"L'âge d'une crise se règle de {low} à {high} ans : {age} ans est refusé."))
    return f"{world.id}@{age}{strength}"


def _combine(reference: list[World], first: list[World], second: list[World]) -> list[World]:
    """Deux crises dans le même monde, champ par champ et mois par mois, par leur écart au monde de référence.
    Une seule s'écarte : sa valeur, telle quelle. Les deux s'écartent : la somme des écarts pour un nombre (deux baisses
    du même mois s'additionnent), « oui » pour un champ oui ou non (deux pertes d'emploi qui se chevauchent n'en font qu'une)."""
    out = []
    for normal, a, b in zip(reference, first, second):
        if a == normal:
            out.append(b)
        elif b == normal:
            out.append(a)
        else:
            month = {}
            for field in fields(World):
                usual, x, y = (getattr(w, field.name) for w in (normal, a, b))
                if x == usual:
                    month[field.name] = y
                elif y == usual:
                    month[field.name] = x
                else:
                    month[field.name] = (not usual) if isinstance(usual, bool) else usual + (x - usual) + (y - usual)
            out.append(World(**month))
    return out


def build(th: dict, world_id, horizon: int, age0: int = AGE0) -> list[World]:
    """Le monde demandé, mois par mois, avec les hypothèses en cours. À un autre âge que celui d'origine, c'est le même
    monde décalé d'un nombre entier d'années : avant, le monde de référence ; au-delà du catalogue, son dernier mois.
    Un monde combiné : ses deux crises, construites chacune comme une crise seule, puis réunies (voir _combine)."""
    if combined(world_id):
        first, second = (build(th, one, horizon, age0) for one in _crisis_ids(world_id, th, horizon, age0))
        return _combine(reference_world(th, horizon), first, second)
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
        raise KeyError(say("Random draws of worlds are not available yet: named worlds only.",
                           "Le tirage au hasard de mondes n'est pas encore disponible : mondes nommés seulement."))
    if th is None or horizon is None:
        for world_id in mondes:
            for part in terms(world_id):
                named(part)
        return tuple(mondes)
    out: list[str] = []
    for world_id in mondes:
        world = canonical(world_id, th, horizon, age0)
        if world not in out:
            out.append(world)
    if not out:
        raise ValueError(say("At least one world to test is needed.", "Il faut au moins un monde à tester."))
    return tuple(out)


def crises(th: dict, world_id, horizon: int, age0: int = AGE0) -> list[dict]:
    """Les crises d'un monde, une par une, rangées par âge de début : le type, l'âge, la gravité, le nom écrit avec l'âge,
    et les mois où la crise s'écarte du monde de référence (`to_month` : le premier mois où elle ne s'en écarte plus).
    Aucune pour un monde entier (référence, prudent)."""
    reference, out = reference_world(th, horizon), []
    for one in _crisis_ids(world_id, th, horizon, age0):
        world, built, percent, age = named(one), build(th, one, horizon, age0), gravity(one), split(one)[1]
        months = [t for t in range(horizon) if built[t] != reference[t]]
        name = say(f"{name_of(world)} at {age}", f"{world.name} à {age} ans")
        if percent != 100:
            name += say(f", severity {percent}%", f", gravité {percent} %")
        out.append({"id": one, "type": world.id, "name": name, "age": age, "gravity": percent,
                    "from_month": months[0], "to_month": months[-1] + 1,
                    "from_age": age0 + months[0] / 12, "to_age": age0 + (months[-1] + 1) / 12})
    return out


def _describe_combined(th: dict, world_id: str, horizon: int, age0: int) -> dict:
    """Un monde à deux crises, décrit comme les autres. Son nom dit chaque crise avec son âge. Ses paramètres sont lus mois
    par mois dans ses données : une ligne par période continue, et une nouvelle ligne quand la seconde crise s'ajoute à la
    première sur le même nombre. Il n'a pas d'âge réglable : chaque crise garde le sien."""
    reference, built = reference_world(th, horizon), build(th, world_id, horizon, age0)
    each = crises(th, world_id, horizon, age0)
    alone = [build(th, crisis["id"], horizon, age0) for crisis in each]
    parameters = []
    for field in fields(World):
        label = say(english.WORLD_FIELDS.get(field.name, field.name), FIELD_LABELS.get(field.name, field.name))
        months, acting = [], None
        for t in range(horizon + 1):
            here = None                 # qui agit sur ce champ ce mois-ci ; None : le champ est celui du monde de référence
            if t < horizon and getattr(built[t], field.name) != getattr(reference[t], field.name):
                usual = getattr(reference[t], field.name)
                here = True if isinstance(usual, bool) else tuple(getattr(w[t], field.name) != usual for w in alone)
            if months and here != acting:
                first, last = months[0], months[-1]
                parameters.append({"field": field.name, "label": label, "from_month": first, "to_month": last + 1,
                                   "months": len(months), "from_age": age0 + first / 12, "to_age": age0 + (last + 1) / 12,
                                   "value": getattr(built[last], field.name), "reference": getattr(reference[last], field.name)})
                months = []
            if here is not None:
                months.append(t)
            acting = here
    parameters.sort(key=lambda line: line["from_month"])
    told = list(dict.fromkeys(say(english.WORLDS[crisis["type"]][1], named(crisis["id"]).description) for crisis in each))
    low, high = ages(horizon, age0)
    names = [crisis["name"] if i == 0 else crisis["name"][0].lower() + crisis["name"][1:] for i, crisis in enumerate(each)]
    return {"id": world_id, "type": world_id, "name": " + ".join(names),
            "description": " ".join([say("Two crises in the same world.", "Deux crises dans le même monde.")] + told),
            "gravity": None, "catalog_id": None, "age": each[0]["age"], "default_age": None, "adjustable": False,
            "min_age": low, "max_age": high, "parameters": parameters, "crises": each}


def describe(th: dict, horizon: int, age0: int, mondes=None) -> list[dict]:
    """Chaque monde, avec ce qui le distingue du monde de référence, lu mois par mois dans ses données.
    `mondes` : les mondes à décrire, avec l'âge choisi pour chaque crise (tous, à leur âge d'origine, par défaut).
    Un monde combiné porte en plus ses crises une par une (`crises`)."""
    reference, out = reference_world(th, horizon), []
    low, high = ages(horizon, age0)
    for world_id in asked(mondes, th, horizon, age0):
        if combined(world_id):
            out.append(_describe_combined(th, world_id, horizon, age0))
            continue
        world, age = named(world_id), split(world_id)[1]
        built, parameters = build(th, world_id, horizon, age0), []
        for field in fields(World):
            months = [t for t in range(horizon) if getattr(built[t], field.name) != getattr(reference[t], field.name)]
            if months:
                first, last = months[0], months[-1]
                parameters.append({"field": field.name, "label": say(english.WORLD_FIELDS.get(field.name, field.name), FIELD_LABELS.get(field.name, field.name)),
                                   "from_month": first, "to_month": last + 1, "months": len(months),
                                   "from_age": age0 + first / 12, "to_age": age0 + (last + 1) / 12,
                                   "value": getattr(built[last], field.name), "reference": getattr(reference[last], field.name)})
        original = default_age(th, world.id, horizon, age0)
        out.append({"id": world_id, "type": world.id, "name": name_of(world),
                    "description": say(english.WORLDS[world.id][1], world.description),
                    "gravity": gravity(world_id),
                    "catalog_id": world.catalog_id, "age": age if age is not None else original, "default_age": original,
                    "adjustable": original is not None, "min_age": low, "max_age": high, "parameters": parameters})
    return out
