"""The two modes of the AI layer, and what each one answers.

- Live: only when it is asked for and can be had, that is with DOORS_AI=live and ANTHROPIC_API_KEY both set in the
  environment of the server. A key exported in a terminal is not enough: the page never spends on its own. Only whether
  the key is there is looked at here: its value is never read, kept or returned. The SDK reads it when it sends a request.
- Recorded: in every other case, no request leaves the machine. A recorded answer is played again by the same loop
  as a live one: the tools run on the engine of today and the checker reads the texts again. A recording that Doors
  would not ask today, to the letter, is refused. A route or a sentence with no recording has no recorded answer, and
  nothing is made up in its place: the screen says so, and shows what the engine finds on its own.

When a live call fails, or when the hourly limit of live calls is reached, the answer says so, and gives the recorded
answer if there is one. Every answer says where it comes from.
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque

from ai import ask as asking
from ai import benchmark, recordings
from ai import stress as stressing
from ai.model import MODEL, Live, Replay, Stale
from engine import i18n
from engine.blocks import normalize
from engine.i18n import say
from engine.tree import Tree

PER_HOUR = 20                       # live requests per hour, for the whole server; DOORS_AI_PER_HOUR changes it


class _Hour:
    """How many live requests the server has made in the last hour."""

    def __init__(self):
        self.times: deque[float] = deque()
        self.lock = threading.Lock()

    @staticmethod
    def most() -> int:
        try:
            return max(0, int(os.environ.get("DOORS_AI_PER_HOUR", PER_HOUR)))
        except ValueError:
            return PER_HOUR

    def _recent(self) -> int:
        while self.times and time.monotonic() - self.times[0] > 3600:
            self.times.popleft()
        return len(self.times)

    def left(self) -> int:
        with self.lock:
            return max(0, self.most() - self._recent())

    def take(self) -> bool:
        """Counts one live request, unless the hour is full."""
        with self.lock:
            if self._recent() >= self.most():
                return False
            self.times.append(time.monotonic())
            return True


_hour = _Hour()
_played: dict = {}                  # the recordings already played again by this server, each with its result


def _asked_live() -> bool:
    return os.environ.get("DOORS_AI", "").strip().lower() == "live"


def mode() -> str:
    """"live" or "recorded". Live takes both DOORS_AI=live and a key; only the presence of the key is looked at."""
    return "live" if _asked_live() and os.environ.get("ANTHROPIC_API_KEY") else "recorded"


def why() -> str:
    """The mode in one sentence, for the screen: what it is, and what would change it."""
    if mode() == "live":
        return say(f"Live mode: the model ({MODEL}) is called for each request.", f"Mode direct : le modèle ({MODEL}) est appelé à chaque demande.")
    if _asked_live():
        return say("Recorded mode: DOORS_AI=live is set, but the server has no key (ANTHROPIC_API_KEY).",
                   "Mode enregistré : DOORS_AI=live est réglé, mais le serveur n'a pas de clé (ANTHROPIC_API_KEY).")
    return say("Recorded mode: no request leaves this machine. The live mode takes DOORS_AI=live and a key (ANTHROPIC_API_KEY) on the server.",
               "Mode enregistré : aucune demande ne quitte cette machine. Le mode direct demande DOORS_AI=live et une clé (ANTHROPIC_API_KEY) sur le serveur.")


def live_model() -> Live:
    """The live model. DOORS_AI_FALLBACK=off sends the requests without the server-side fallback, which is a beta."""
    return Live(fallback=os.environ.get("DOORS_AI_FALLBACK", "").strip().lower() != "off")


def status(scenario: str = "alexia") -> dict:
    """What the screen needs to know before it asks: the mode, the model, the limits, and what is recorded."""
    live = mode() == "live"
    return {"mode": "live" if live else "recorded", "why": why(), "model": MODEL,
            "limits": {"sentence_characters": asking.MAX_LENGTH, "live_requests_per_hour": _hour.most() if live else None,
                       "live_requests_left": _hour.left() if live else None},
            "recorded": recordings.listing(scenario)}


def _label(source: str, model: str, recorded_at: str | None) -> str:
    if source == "live":
        return say(f"Live answer · {model}", f"Réponse en direct · {model}")
    return say(f"Recorded answer · {model} · {recorded_at}", f"Réponse enregistrée · {model} · {recorded_at}")


def _answer(source: str | None, result: dict | None, model: str | None = None, recorded_at: str | None = None,
            notice: str | None = None, reason: str | None = None) -> dict:
    """What a route of the AI layer returns: the result when there is one, where it comes from, and what to say when
    there is none. `notice`: something the screen must say next to an answer, such as a live call that failed."""
    return {"mode": mode(), "available": result is not None, "source": source, "model": model, "recorded_at": recorded_at,
            "label": _label(source, model, recorded_at) if source in ("live", "recorded") else None,
            "notice": notice, "reason": reason, "result": result}


def _unreached(error: Exception) -> str | None:
    """The sentence for a live call that failed because of the API, the network or the key. None for any other error:
    a fault of this code is not dressed as a failure of the network. The message of the error is not shown."""
    module = type(error).__module__.split(".")[0]
    if module in ("anthropic", "httpx2", "httpx", "httpcore", "anyio") or "authentication method" in str(error):
        return say(f"The live model could not be reached ({type(error).__name__}).",
                   f"Le modèle en direct n'a pas pu être joint ({type(error).__name__}).")
    return None


def replay(tree: Tree, recording: dict) -> dict:
    """A recording played again on the engine of today, by the loop that made it. Raises `Stale` when Doors would not
    ask today what it asked then. The result is kept for as long as the recording read from its file is the same."""
    key = (id(recording), id(tree.sc))
    if key in _played and _played[key][0] is recording:
        return _played[key][2]
    model = Replay(recording["turns"], recording["model"])
    if recording["kind"] == "stress":
        result = stressing.run(tree, recording["path"], model, recording["assumptions"], recording["language"],
                               benchmark.truth_for(recording["path"], recording["assumptions"], tree.h))
    else:
        result = asking.ask(tree, recording["sentence"], model, recording["path"], recording["assumptions"], recording["language"])
    model.finish()
    _played[key] = (recording, tree.sc, result)         # the recording and the scenario are held, so that their identities stay theirs
    return result


def _serve(kind: str, tree: Tree, scenario: str, path: list[dict] | None, overrides: dict, lang: str, sentence: str | None, run_live) -> dict:
    """Live when the mode is live and the hour is not full, and otherwise the recording made for exactly this."""
    notice = None
    if mode() == "live":
        if not _hour.take():
            notice = say(f"The limit of {_hour.most()} live requests per hour is reached.",
                         f"La limite de {_hour.most()} demandes en direct par heure est atteinte.")
        else:
            try:
                result = run_live(live_model())
                return _answer("live", result, result.get("model") or MODEL)
            except Exception as error:
                notice = _unreached(error)
                if notice is None:
                    raise
    recorded = recordings.find(kind, lang, scenario, path, overrides, sentence)
    nothing = say("No recorded answer for this route with these assumptions.", "Pas de réponse enregistrée pour ce trajet avec ces hypothèses.") \
        if kind == "stress" else say("No recorded answer for this sentence on this route.", "Pas de réponse enregistrée pour cette phrase sur ce trajet.")
    if recorded is None:
        return _answer(None, None, notice=notice, reason=nothing)
    try:
        result = replay(tree, recorded)
    except Stale:
        return _answer(None, None, notice=notice,
                       reason=say("The recorded answer no longer matches the engine: it is not shown.",
                                  "La réponse enregistrée ne correspond plus au moteur : elle n'est pas montrée."))
    return _answer("recorded", result, recorded["model"], recorded["recorded_at"], notice)


def _scan(tree: Tree, path: list[dict], overrides: dict, truth: dict | None) -> dict | None:
    """For a route of the benchmark, the hardest worlds of the full scan made offline, named for the screen."""
    if truth is None:
        return None
    route = stressing.Route(Tree(tree.sc), path, overrides)
    return {**truth, "hardest": [route.shown(summary) for summary in truth["hardest"]]}


def stress(tree: Tree, path: list[dict], overrides: dict | None = None, lang: str | None = None, scenario: str = "alexia") -> dict:
    """“Find what breaks my plan” for a route: live, or the recording made for this route, these assumptions and this
    language. A route the engine refuses is refused before anything else, with the engine's reason."""
    lang, overrides = lang or i18n.current(), dict(overrides or {})
    with i18n.use(lang):
        path = normalize(path, tree.h)
        truth = benchmark.truth_for(path, overrides, tree.h)
        answer = _serve("stress", tree, scenario, path, overrides, lang, None,
                        lambda model: stressing.run(tree, path, model, overrides, lang, truth))
        # With no answer of the model to show, the screen shows what the engine finds on its own. It is not an answer
        # of the model and is never labelled as one.
        return {**answer, "engine": None if answer["available"] else stressing.alone(tree, path, overrides, lang),
                "scan": _scan(tree, path, overrides, truth)}


def ask(tree: Tree, sentence: str, path: list[dict] | None = None, overrides: dict | None = None, lang: str | None = None,
        scenario: str = "alexia") -> dict:
    """“Ask in your own words” for one sentence: live, or the recording made for this sentence on this route. A sentence
    that is empty or too long is answered by code, with no model in either mode."""
    lang, overrides = lang or i18n.current(), dict(overrides or {})
    with i18n.use(lang):
        path = normalize(path, tree.h) if path else None
        refused = asking.before_reading(sentence, lang)
        if refused is not None:
            return _answer("code", refused)
        return _serve("ask", tree, scenario, path, overrides, lang, sentence,
                      lambda model: asking.ask(tree, sentence, model, path, overrides, lang))
