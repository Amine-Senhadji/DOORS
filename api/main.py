"""API du jumeau financier. Les formes des réponses sont décrites dans docs/API.md.

Lancer depuis la racine du repo :
    .venv/bin/uvicorn api.main:app --reload --port 8000
Documentation interactive : http://localhost:8000/docs
"""
from __future__ import annotations

import io
import json
import sys
import time
import unittest
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from urllib.parse import parse_qs

from engine import folk, i18n
from engine import policy as policies
from engine import worlds as named_worlds
from engine.assumptions import localized
from engine.i18n import say
from engine.checks import run_checks
from engine.explore import compare, frontier
from engine.simulate import load_scenario, run, theta_for
from engine.tree import Tree

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "engine" / "scenarios"

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Au démarrage : le trajet par défaut de la démo est calculé dans tous les mondes, et gardé en mémoire."""
    warm_up()
    yield


app = FastAPI(title="Doors : jumeau financier", version="0.1.0", lifespan=lifespan,
              description="Exploration conditionnelle, pas de prévision. Voir docs/API.md.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class Language:
    """La langue des phrases d'une demande : `?lang=fr` ou `?lang=en` dans son adresse. Sans elle, la langue par défaut.
    Les chiffres sont les mêmes dans les deux langues."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        asked = parse_qs(scope.get("query_string", b"").decode()).get("lang", [None])[0] if scope["type"] == "http" else None
        if asked in i18n.LANGUAGES:
            with i18n.use(asked):
                await self.inner(scope, receive, send)
        else:
            await self.inner(scope, receive, send)


app.add_middleware(Language)


@lru_cache(maxsize=16)
def _scenario(scenario_id: str):
    path = SCENARIOS / f"{scenario_id}.json"
    if not path.is_file():
        raise HTTPException(404, say(f"Unknown scenario “{scenario_id}”.", f"Scénario inconnu « {scenario_id} »."))
    return load_scenario(path)


@lru_cache(maxsize=16)
def _tree(scenario_id: str) -> Tree:
    """L'arbre des trajets d'un scénario : il garde en mémoire les trajets déjà simulés."""
    return Tree(_scenario(scenario_id))


def default_path(scenario_id: str = "alexia") -> list[dict]:
    """Le trajet affiché à l'ouverture de la page : il est écrit dans le fichier du scénario."""
    _scenario(scenario_id)
    return json.loads((SCENARIOS / f"{scenario_id}.json").read_text(encoding="utf-8")).get("default_path", [])


def warm_up(scenario_id: str = "alexia") -> None:
    """Calcule d'avance ce que la page demande à l'ouverture : le trajet par défaut, ses chemins d'adaptation, ses gares."""
    path, tree = default_path(scenario_id), _tree(scenario_id)
    if not path:
        return
    tree.path_view(path)
    for gare in tree.pathways_view(path)["gares"]:
        tree.node_view(path, gare["gare_month"])
    policies.view(tree, path)             # le tableau de valeur : ses seuils, ses mondes, ses variantes de test


def _world(scenario_id: str, world_id: str, assumptions: dict):
    """Le monde nommé demandé, mois par mois. Un monde inconnu est refusé clairement."""
    sc = _scenario(scenario_id)
    return _guard(named_worlds.build, theta_for(sc, assumptions), world_id, sc.horizon_months, sc.profile.age)


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as e:          # paramètre manquant, ligne ou station inconnue, trajet invalide...
        raise HTTPException(422, str(e)) from e
    except KeyError as e:            # monde inconnu, ou tirage au hasard pas encore disponible
        raise HTTPException(400, e.args[0]) from e


class SimulateIn(BaseModel):
    scenario_id: str = "alexia"
    line_id: str
    world_id: str = "reference"
    assumptions: dict[str, float] = Field(default_factory=dict)


class CompareIn(BaseModel):
    scenario_id: str = "alexia"
    station_id: str
    world_id: str = "reference"
    assumptions: dict[str, float] = Field(default_factory=dict)


class Axis(BaseModel):
    key: str
    min: float
    max: float
    steps: int = Field(15, ge=2, le=40)


class FrontierIn(BaseModel):
    scenario_id: str = "alexia"
    station_id: str
    criterion: str = "patrimoine"
    x: Axis
    y: Axis
    assumptions: dict[str, float] = Field(default_factory=dict)


@app.get("/scenario/{scenario_id}")
def get_scenario(scenario_id: str):
    _scenario(scenario_id)
    return json.loads((SCENARIOS / f"{scenario_id}.json").read_text(encoding="utf-8"))


@app.get("/assumptions")
def get_assumptions():
    return [asdict(a) for a in localized()]


@app.post("/simulate")
def post_simulate(req: SimulateIn):
    world = _world(req.scenario_id, req.world_id, req.assumptions)
    r = _guard(run, _scenario(req.scenario_id), req.line_id, req.assumptions, world, req.world_id)
    answer = asdict(r)
    return {**answer, "months": i18n.months(answer["months"])}


@app.post("/compare")
def post_compare(req: CompareIn):
    world = _world(req.scenario_id, req.world_id, req.assumptions)
    return _guard(compare, _scenario(req.scenario_id), req.station_id, req.assumptions, world, req.world_id)


@lru_cache(maxsize=64)
def _frontier_cached(payload: str, lang: str):
    req = FrontierIn.model_validate_json(payload)
    return _guard(frontier, _scenario(req.scenario_id), req.station_id, req.x.model_dump(),
                  req.y.model_dump(), req.criterion, req.assumptions)


@app.post("/frontier")
def post_frontier(req: FrontierIn):
    # Le cache rend instantané un retour à une carte déjà vue.
    return _frontier_cached(req.model_dump_json(), i18n.current())      # la carte porte des phrases : une par langue


@app.get("/checks")
def get_checks(scenario_id: str = "alexia", lines: str = "master,travailler"):
    return _guard(run_checks, _scenario(scenario_id), [l for l in lines.split(",") if l])


@app.post("/checks/starter-kit")
def post_checks_starter_kit():
    """Relance en direct l'égalité avec le moteur de référence du starter-kit : les tests de tests/test_vs_starter_kit.py,
    lancés dans ce serveur, donc sur le moteur qui répond en ce moment."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    started = time.perf_counter()
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_vs_starter_kit")
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    problems = [{"test": str(test), "message": trace.strip().splitlines()[-1][:300]} for test, trace in result.failures + result.errors]
    return {"ok": result.wasSuccessful() and result.testsRun > 0, "total": result.testsRun, "failed": len(problems),
            "duration_s": round(time.perf_counter() - started, 3), "ran_at": datetime.now().isoformat(timespec="seconds"),
            "title": say("Equality with the starter kit's reference engine", "Égalité avec le moteur de référence du starter-kit"),
            "detail": say("The 360 monthly balances of the starter kit's three scenarios, to the cent, once the Swiss rules are switched off.",
                          "Les 360 soldes mensuels des trois scénarios du starter-kit, au centime, une fois les règles suisses neutralisées."),
            "source": "tests/test_vs_starter_kit.py", "failures": problems}


@app.get("/limits")
def get_limits():
    """Les limites connues du modèle : la liste de docs/LIMITS.md (ou de docs/limits.fr.md en français), lue telle quelle."""
    name = say("docs/LIMITS.md", "docs/limits.fr.md")
    limits = [line[2:].strip() for line in (ROOT / name).read_text(encoding="utf-8").splitlines() if line.startswith("- ")]
    return {"source": name, "limits": limits}


# ----------------------------------------------------------------- version 3 : l'arbre des trajets
class TripIn(BaseModel):
    """Un trajet : une suite de blocs qui couvre la période. `mondes` : les mondes nommés à tester (tous par défaut)."""
    scenario_id: str = "alexia"
    path: list[dict] = Field(default_factory=list)
    # Les mondes à tester : des noms (« krach », « krach@25 ») ou des crises { "type": "krach", "age": 25 }.
    mondes: list[str | dict] | dict | None = None
    assumptions: dict[str, float] = Field(default_factory=dict)
    # Le jumeau qui apprend : ce qu'Alexia a vraiment de côté à une gare, { "gare_month": 72, "value_chf": 40000 }.
    observation: dict | None = None


class PathIn(TripIn):
    world_id: str = "reference"


class NodeIn(TripIn):
    gare_month: int = 0


@app.get("/worlds")
def get_worlds(scenario_id: str = "alexia", mondes: str | None = None):
    """`mondes` : les mondes à décrire, séparés par des virgules, avec l'âge choisi pour une crise (« krach@25 »)."""
    sc = _scenario(scenario_id)
    chosen = [m for m in mondes.split(",") if m] if mondes else None
    return _guard(named_worlds.describe, theta_for(sc), sc.horizon_months, sc.profile.age, chosen)


@app.post("/path")
def post_path(req: PathIn):
    return _guard(_tree(req.scenario_id).path_view, req.path, req.world_id, req.assumptions, req.mondes, req.observation)


@app.post("/node")
def post_node(req: NodeIn):
    return _guard(_tree(req.scenario_id).node_view, req.path, req.gare_month, req.assumptions, req.mondes, req.observation)


@app.post("/pathways")
def post_pathways(req: NodeIn):
    return _guard(_tree(req.scenario_id).pathways_view, req.path, req.gare_month, req.assumptions, req.mondes, req.observation)


class AdaptiveIn(TripIn):
    """Une règle adaptative, comme une donnée : { gare_month, variable, threshold_chf, branch_id }. Sans elle : la règle par défaut
    du trajet, tirée de son signal à surveiller. `door` : la porte que la règle cherche à garder, pour le résumé."""
    rule: dict | None = None
    door: str | None = None


@app.post("/adaptive")
def post_adaptive(req: AdaptiveIn):
    return _guard(_tree(req.scenario_id).adaptive_view, req.path, req.rule, req.door, req.assumptions, req.mondes, req.observation)


@app.post("/policies")
def post_policies(req: TripIn):
    """Le tableau de valeur : le plan figé et les trois politiques, dans les mondes du tableau (ou dans `mondes`).
    Sans trajet : celui de la démo."""
    path = req.path or default_path(req.scenario_id)
    return _guard(policies.view, _tree(req.scenario_id), path, req.assumptions, req.mondes)


@app.post("/folk-rule")
def post_folk_rule(req: TripIn):
    """Une règle répandue, mise à l'épreuve par le moteur : « trois mois d'épargne de précaution suffisent ».
    Deux états au même âge : salariée, et en master (le trajet donné, ou celui de la démo)."""
    path = req.path or default_path(req.scenario_id)
    return _guard(folk.view, _tree(req.scenario_id), path, req.assumptions)


@app.post("/ask")
def post_ask():
    raise HTTPException(501, say("The AI desk is not connected.", "Le guichet IA n'est pas encore branché."))


# --- Interface (web/) : la page est servie par ce même serveur.
# Ces lignes doivent rester les dernières du fichier : une route déclarée après elles serait masquée par la page.
from api.web import attach  # noqa: E402

attach(app)
