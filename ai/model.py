"""The turns of a model, behind one interface.

The stress test talks to a model through `reply`. What goes in and what comes out has the shape of the Messages API:
a system prompt, messages made of content blocks, tools, and an optional JSON schema for the answer. The same loop
can therefore run with the live model, with a recorded answer replayed, and with a script.

Only the scripted model lives here for now: no test and no benchmark of this step opens a connection.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Callable, Protocol


@dataclass(frozen=True)
class Reply:
    """One answer of a model. `content`: its blocks as the Messages API gives them (text, tool_use, thinking). They go
    back into the conversation as they are: the loop never rewrites what a model said."""
    content: tuple[dict, ...]
    stop_reason: str = "end_turn"          # end_turn, tool_use, max_tokens, refusal
    usage: dict = field(default_factory=dict)

    def text(self) -> str:
        """What the model wrote, its tool calls and its thinking left aside."""
        return "".join(block.get("text", "") for block in self.content if block.get("type") == "text")

    def tool_calls(self) -> list[dict]:
        return [block for block in self.content if block.get("type") == "tool_use"]


class Model(Protocol):
    """Anything that can answer a request shaped like the Messages API."""
    name: str

    def reply(self, *, system: str, messages: list[dict], tools: list[dict], output: dict | None, effort: str) -> Reply:
        """`output`: a JSON schema the answer must follow, or None. `effort`: low, medium or high."""


def says(words: str) -> Reply:
    """A turn where the model only writes."""
    return Reply(({"type": "text", "text": words},))


def answers(data) -> Reply:
    """A turn where the model fills the JSON schema it was given."""
    return Reply(({"type": "text", "text": json.dumps(data, ensure_ascii=False)},))


def calls(tool: str, arguments: dict, call_id: str = "call", words: str = "") -> Reply:
    """A turn where the model asks for a tool, with or without a word before it."""
    said = ({"type": "text", "text": words},) if words else ()
    return Reply(said + ({"type": "tool_use", "id": call_id, "name": tool, "input": arguments},), "tool_use")


class Scripted:
    """A model that plays a script: the tests, and the benchmark's check of itself. Each turn is a `Reply`, or a
    function that reads the request and returns one. `requests` keeps what it was asked, turn after turn."""

    def __init__(self, turns, name: str = "scripted"):
        self.turns: list[Reply | Callable[[dict], Reply]] = list(turns)
        self.name = name
        self.requests: list[dict] = []

    def reply(self, *, system: str, messages: list[dict], tools: list[dict], output: dict | None, effort: str) -> Reply:
        request = {"system": system, "messages": messages, "tools": tools, "output": output, "effort": effort}
        if len(self.requests) >= len(self.turns):
            raise RuntimeError(f"The script holds {len(self.turns)} turns and was asked for one more.")
        turn = self.turns[len(self.requests)]
        self.requests.append(copy.deepcopy(request))
        return turn(request) if callable(turn) else turn
