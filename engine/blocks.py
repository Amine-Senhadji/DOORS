"""Des blocs de vie aux opérations du moteur, et les branches proposées à chaque gare de correspondance.

Un trajet est une suite de blocs qui couvre toute la période, par exemple :
    [{"block": "master", "years": 2}, {"block": "job", "years": 8}]
`blocks_to_ops` le traduit en opérations (a_t). Un bloc que le moteur ne sait pas traduire lève une erreur
claire : il n'est jamais approximé en silence.

`destinations` donne, pour un trajet et une gare, les branches entre lesquelles on choisit à cette gare.
Elles dépendent de la situation à ce moment : en études, en emploi en Suisse, ou à Berlin.
"""
from __future__ import annotations

from fractions import Fraction
from math import ceil

from engine.contract import Operation

MASTER_YEARS = 2          # Data/scenario-assumptions.csv (AS-P00001-01) : study_duration_years = 2
PART_TIME_YEARS = 3       # le même master en travaillant : scénario S002 du catalogue, durée choisie par l'équipe
PART_TIME_RATE = 0.6      # taux d'activité pendant un master en travaillant (S002)

BLOCKS: dict[str, dict] = {
    "master": {"name": "Master", "catalog_ids": ["S001"]},
    "master_part_time": {"name": "Master en travaillant", "catalog_ids": ["S002"]},
    "job": {"name": "Emploi à Lausanne", "catalog_ids": ["S011"]},
    "job_abroad": {"name": "Emploi à Berlin", "catalog_ids": ["S023"]},
}
STUDIES = ("master", "master_part_time")
# Blocs et options connus du cahier des charges, mais que le moteur ne sait pas encore traduire.
NOT_YET = {"phd": "le doctorat", "internship": "l'année de stage", "independent": "l'activité indépendante",
           "startup": "la création d'entreprise", "pause": "la pause"}
CITIES = {"job": {"lausanne"}, "job_abroad": {"berlin"}}
REFUSED_CITIES = {"london": "Londres", "singapore": "Singapour"}


def normalize(path: list[dict], horizon_months: int) -> list[dict]:
    """Contrôle un trajet et le rend sous sa forme canonique : blocs connus, années entières, période couverte."""
    if not isinstance(path, list) or not path:
        raise ValueError("Un trajet est une liste d'au moins un bloc.")
    out: list[dict] = []
    for i, raw in enumerate(path, start=1):
        if not isinstance(raw, dict) or "block" not in raw:
            raise ValueError(f"Bloc n° {i} : il se décrit par un type (block) et une durée en années (years).")
        block, years, options = raw["block"], raw.get("years"), dict(raw.get("options") or {})
        if block in NOT_YET:
            raise ValueError(f"Bloc n° {i} : le moteur ne sait pas encore traduire {NOT_YET[block]} (« {block} »).")
        if block not in BLOCKS:
            raise ValueError(f"Bloc n° {i} : type inconnu « {block} ». Blocs : {sorted(BLOCKS)}")
        if isinstance(years, bool) or not isinstance(years, int) or years < 1:
            raise ValueError(f"Bloc n° {i} (« {block} ») : la durée est un nombre entier d'années, au moins 1.")
        city = options.pop("city", None)
        if city in REFUSED_CITIES:
            raise ValueError(f"Bloc n° {i} : {REFUSED_CITIES[city]} est refusé, le moteur ne connaît que le franc et l'euro. "
                             "L'étranger, c'est Berlin.")
        if city is not None and city not in CITIES.get(block, ()):
            raise ValueError(f"Bloc n° {i} (« {block} ») : la ville « {city} » n'est pas encore traduite par le moteur.")
        if options:
            raise ValueError(f"Bloc n° {i} (« {block} ») : option inconnue {sorted(options)}.")
        if out and out[-1]["block"] == block:
            out[-1]["years"] += years                 # deux blocs identiques qui se suivent n'en font qu'un
        else:
            out.append({"block": block, "years": years})
    total = 12 * sum(b["years"] for b in out)
    if total != horizon_months:
        raise ValueError(f"Le trajet couvre {total // 12} ans : il en faut {horizon_months // 12}.")
    return out


def _walk(path: list[dict]):
    """Chaque bloc avec la situation au moment où il commence : mois, avancement du master, lieu, mois travaillés."""
    month, progress, abroad, worked, before = 0, Fraction(0), False, 0, None
    for b in path:
        yield b, {"start": month, "end": month + 12 * b["years"], "progress": progress, "abroad": abroad,
                  "worked": worked, "before": before}
        if b["block"] == "master":
            progress += Fraction(b["years"], MASTER_YEARS)
        elif b["block"] == "master_part_time":
            progress += Fraction(b["years"], PART_TIME_YEARS)
        abroad = b["block"] == "job_abroad"
        before = b["block"]
        month += 12 * b["years"]
        # `worked` est mis à jour par blocks_to_ops, qui connaît la durée de la recherche d'emploi.


def _search_months(th: dict, facts: dict) -> int:
    """Les mois de recherche avant un emploi en Suisse, selon ce qui précède."""
    if facts["before"] == "master":
        return int(th["recherche_emploi_mois"] if facts["progress"] >= 1 else th["recherche_apres_arret_mois"])
    if facts["before"] == "job_abroad":
        return int(th["recherche_emploi_mois"])      # au retour de l'étranger
    return 0                                         # au départ, ou quand un emploi en suit un autre


def _translate(path: list[dict], th: dict) -> tuple[list[Operation], list[dict]]:
    ops: list[Operation] = []
    legs: list[dict] = []
    worked = 0
    for b, f in _walk(path):
        s, e, kind = f["start"], f["end"], b["block"]
        seniority = {"anciennete_mois": worked} if worked else {}
        master = f["progress"] >= 1
        leg = {"block": kind, "name": BLOCKS[kind]["name"], "from_month": s, "to_month": e, "catalog_ids": BLOCKS[kind]["catalog_ids"]}
        if kind in STUDIES and f["abroad"]:
            ops.append(Operation("demenager", s, s + 1, {"lieu": "CH", "cout_chf": th["cout_demenagement"]}))
        if kind == "master":
            ops.append(Operation("etudier", s, e, {"job_net_mensuel": th["job_net_mensuel"], "taxe_semestre": th["taxe_semestre"]}))
        elif kind == "master_part_time":
            ops.append(Operation("etudier", s, e, {"job_net_mensuel": 0.0, "taxe_semestre": th["taxe_semestre"]}))
            ops.append(Operation("travailler", s, e, {"salaire_brut_mensuel": th["salaire_sans_master"],
                                                      "taux_activite": PART_TIME_RATE, **seniority}))
            worked += e - s
        elif kind == "job":
            if f["abroad"]:
                ops.append(Operation("demenager", s, s + 1, {"lieu": "CH", "cout_chf": th["cout_demenagement"]}))
            start = min(e, s + _search_months(th, f))
            if start > s:
                ops.append(Operation("chercher_emploi", s, start))
                legs.append({"block": "recherche", "name": "Recherche d'emploi", "from_month": s, "to_month": start, "catalog_ids": []})
                leg = {**leg, "from_month": start}
            ops.append(Operation("travailler", start, e, {
                "salaire_brut_mensuel": th["salaire_apres_master" if master else "salaire_sans_master"],
                "depenses_mensuelles": th["depenses_emploi_apres_master" if master else "depenses_emploi_sans_master"],
                **seniority}))
            worked += e - start
        elif kind == "job_abroad":
            if not f["abroad"]:
                ops.append(Operation("demenager", s, s + 1, {"lieu": "etranger", "cout_chf": th["cout_demenagement"]}))
            ops.append(Operation("travailler", s, e, {"salaire_brut_mensuel": th["salaire_etranger_eur"], "devise": "EUR", **seniority}))
            worked += e - s
        if leg["to_month"] > leg["from_month"]:
            legs.append(leg)
    return ops, legs


def blocks_to_ops(path: list[dict], th: dict, horizon_months: int) -> tuple[Operation, ...]:
    """Les opérations d'un trajet, en mois comptés depuis le départ, avec les valeurs des hypothèses en cours."""
    return tuple(_translate(normalize(path, horizon_months), th)[0])


def legs_of(path: list[dict], th: dict, horizon_months: int, from_month: int = 0) -> list[dict]:
    """Les tronçons d'un trajet, pour la carte : un par bloc, plus la recherche d'emploi quand il y en a une."""
    legs = _translate(normalize(path, horizon_months), th)[1]
    return [{**leg, "from_month": max(leg["from_month"], from_month)} for leg in legs if leg["to_month"] > from_month]


def cut(path: list[dict], month: int) -> list[dict]:
    """Les blocs déjà parcourus quand on arrive à une gare (un mois multiple de 12)."""
    out, start = [], 0
    for b in path:
        years = min(b["years"], (month - start) // 12)
        if years > 0:
            out.append({"block": b["block"], "years": years})
        start += 12 * b["years"]
    return out


def _years(n: int) -> str:
    return "1 an" if n == 1 else f"{n} ans"


def destinations(path: list[dict], gare_month: int, horizon_months: int, age0: int) -> list[dict]:
    """Les branches proposées à une gare : trois au plus, « rester » compris, chacune avec sa suite par défaut.

    Depuis des études : continuer, arrêter pour un emploi à Lausanne, passer en master en travaillant.
    Depuis un emploi en Suisse, ou au départ : l'emploi à Lausanne, un master, partir à Berlin.
    Depuis Berlin : rester, rentrer pour un emploi à Lausanne, un master à Lausanne.
    Après un master, la suite par défaut est un emploi à Lausanne. Une branche impossible porte sa raison.
    """
    path = normalize(path, horizon_months) if path else []        # au départ, aucun trajet n'est encore suivi
    if not path and gare_month:
        raise ValueError("Il faut un trajet pour ouvrir une gare après le départ.")
    if gare_month % 12 or not 0 <= gare_month < horizon_months:
        raise ValueError(f"Pas de gare au mois {gare_month} : une gare par an, du mois 0 au mois {horizon_months - 12}.")
    past, left = cut(path, gare_month), (horizon_months - gare_month) // 12
    progress, last = Fraction(0), None
    for b in past:
        progress += Fraction(b["years"], MASTER_YEARS if b["block"] == "master" else PART_TIME_YEARS) if b["block"] in STUDIES else 0
        last = b["block"]
    end_age = age0 + horizon_months // 12

    def then(*blocks: tuple[str, int]) -> list[dict]:
        """Le trajet complet : le passé, les blocs de la branche, puis l'emploi à Lausanne jusqu'au bout."""
        trip, used = list(past), 0
        for block, years in blocks:
            trip.append({"block": block, "years": years})
            used += years
        if used < left:
            trip.append({"block": "job", "years": left - used})
        return normalize(trip, horizon_months)

    def study(branch_id: str, label: str, block: str) -> dict:
        """Une branche qui mène au master, à plein temps ou en travaillant."""
        if progress >= 1:
            return {"id": branch_id, "label": label, "available": False, "reason": "Alexia a déjà un master.", "path": None}
        needed = ceil((1 - progress) * (MASTER_YEARS if block == "master" else PART_TIME_YEARS))
        if needed > left:
            return {"id": branch_id, "label": label, "available": False, "path": None,
                    "reason": f"Il reste {_years(left)} avant {end_age} ans : il en faut {needed} pour finir le master."}
        return {"id": branch_id, "label": label, "available": True, "reason": None, "path": then((block, needed))}

    def other(branch_id: str, label: str, *blocks: tuple[str, int]) -> dict:
        return {"id": branch_id, "label": label, "available": True, "reason": None, "path": then(*blocks)}

    if last in STUDIES and progress < 1:
        out = [study("continuer", "Continuer le master", last),
               other("emploi", "Arrêter pour un emploi à Lausanne")]
        if last == "master":
            out.append(study("master_en_travaillant", "Passer en master en travaillant", "master_part_time"))
    elif last == "job_abroad":
        out = [other("berlin", "Rester à Berlin", ("job_abroad", left)),
               other("emploi", "Rentrer pour un emploi à Lausanne"),
               study("master", "Reprendre le master à Lausanne" if progress else "Commencer un master à Lausanne", "master")]
    elif last is None:
        out = [study("master", "Faire un master", "master"),
               other("emploi", "Travailler à Lausanne"),
               other("berlin", "Partir à Berlin", ("job_abroad", left))]
    else:
        out = [other("emploi", "Rester en emploi à Lausanne" if last == "job" else "Prendre un emploi à Lausanne"),
               study("master", "Reprendre le master" if progress else "Commencer un master", "master"),
               other("berlin", "Partir à Berlin", ("job_abroad", left))]

    # Le trajet suivi : c'est la branche qui commence par le même bloc que lui après la gare. Elle garde le trajet
    # tel qu'il est, même s'il change encore plus tard. S'il n'est dans aucune branche, il s'ajoute en tête.
    def block_at(trip: list[dict], month: int) -> str | None:
        start = 0
        for b in trip:
            if start <= month < start + 12 * b["years"]:
                return b["block"]
            start += 12 * b["years"]
        return None

    following = block_at(path, gare_month) if path else None
    for branch in out:
        branch["on_path"] = False
    if path:
        mine = next((b for b in out if b["available"] and block_at(b["path"], gare_month) == following), None)
        if mine:
            mine["on_path"], mine["path"] = True, path
        else:
            out.insert(0, {"id": "trajet", "label": "Suivre le trajet actuel", "available": True, "reason": None,
                           "path": path, "on_path": True})
    return out
