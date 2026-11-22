"""A rehearsal: an exchange played with a stand-in for the model, so that a dry run can show every request as it would
be sent and estimate what it would cost. Nothing is sent, no client is built, and the key is not looked at.

The stand-in does not think. In a search it calls the tool with worlds drawn from the space in a fixed order, until
the budget is used up; for the explanations it writes a sentence with no figure; for “Ask” it returns an empty form.
What it says is thrown away. What matters is what the loop builds around it: the system prompts, the tool, the
forms, the results of the engine sent back turn after turn, the facts given for the explanations. Those are real.
"""
from __future__ import annotations

import random

from ai import ask as asking
from ai import stress as stressing
from ai import vocabulary as V
from ai.cost import number
from ai.model import FALLBACK, MAX_TOKENS, MODEL, Recorder, Reply, answers, calls, request_for
from engine.simulate import theta_for
from engine.tree import Tree

SEED = 2026
PLAIN = "The route loses goals in this world."         # a sentence with no figure: the checker accepts it in both languages
EMPTY = {"route": [], "change": None, "crises": [], "assumptions": [], "savings": None, "not_understood": []}


class StandIn:
    """Plays the model's part with no model."""
    name = "stand-in"

    def __init__(self, worlds: list[str]):
        self.worlds = worlds

    def reply(self, *, system: str, messages: list[dict], tools: list[dict], output: dict | None, effort: str) -> Reply:
        if tools:                                       # a turn of the search: the next worlds of the list
            turn = sum(message["role"] == "assistant" for message in messages)
            batch = self.worlds[turn * stressing.PER_CALL:(turn + 1) * stressing.PER_CALL]
            return calls(stressing.TOOL, {"worlds": batch}, call_id=f"standin_{turn + 1}")
        fields = (output or {}).get("properties") or {}
        if "explanations" in fields:                    # the explanations: one plain sentence per world asked
            asked = fields["explanations"]["items"]["properties"]["world"]["enum"]
            return answers({"explanations": [{"world": world, "text": PLAIN} for world in asked]})
        return answers(EMPTY)                           # one sentence to read: an empty form


def sample(tree: Tree, overrides: dict | None = None, seed: int = SEED) -> list[str]:
    """Worlds for the stand-in to test: as many as the budget, drawn from the whole space, the same at every rehearsal."""
    th = theta_for(tree.sc, overrides or {})
    space = list(V.worlds(th, tree.h, tree.age0))
    return random.Random(seed).sample(space, stressing.CALLS * stressing.PER_CALL)


def stress(tree: Tree, path: list[dict], overrides: dict | None = None, lang: str = "en") -> list[dict]:
    """The requests of one stress test, as the loop builds them: the turns of the search, then the explanations."""
    recorder = Recorder(StandIn(sample(tree, overrides)))
    stressing.run(tree, path, recorder, overrides, lang)
    return [turn["request"] for turn in recorder.turns]


def ask(tree: Tree, sentence: str, path: list[dict] | None = None, overrides: dict | None = None, lang: str = "en") -> list[dict]:
    """The one request of “Ask” for a sentence."""
    recorder = Recorder(StandIn([]))
    asking.ask(tree, sentence, recorder, path, overrides, lang)
    return [turn["request"] for turn in recorder.turns]


def settings(fallback: bool = True) -> str:
    """What every live request carries besides its own content, in one line."""
    return (f"model {MODEL} · max_tokens {number(MAX_TOKENS)} · adaptive thinking · system prompt marked for the cache · "
            + (f"fallback \"default\" (beta {FALLBACK})" if fallback else "no fallback"))


HEADING = ("DRY RUN. Nothing is sent, no client is built, and the key is not looked at.\n"
           "A stand-in plays the model's part, so that each request is built as it would be sent. In a stress test it tests worlds\n"
           "drawn from the space in a fixed order: the results of the engine and the facts shown are examples of what would go back.\n")


def indent(text: str, by: str = "     | ") -> str:
    return "\n".join(by + line for line in str(text).splitlines())


def as_sent(requests: list[dict], fallback: bool = True) -> list[dict]:
    """The requests in the shape the SDK would be given: what `Live` would send, keyword for keyword."""
    return [request_for(**request, fallback=fallback) for request in requests]
