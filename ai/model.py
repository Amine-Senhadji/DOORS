"""The turns of a model, behind one interface.

The stress test and “Ask” talk to a model through `reply`. What goes in and what comes out has the shape of the
Messages API: a system prompt, messages made of content blocks, tools, and an optional JSON schema for the answer.
The same loop therefore runs with four sources of turns:

- `Live`: the model itself, through the SDK. The only place where a request leaves the machine.
- `Recorder`: any model, with everything that was asked and answered kept, to be written to a file.
- `Replay`: a recorded exchange played again. Each request of today must be the request that was answered then.
- `Scripted`: a script, for the tests and for the benchmark's check of itself.

The key is read by the SDK, in the environment. Nothing in this repository reads its value, writes it or prints it.
"""
from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 16000                                  # room for the thinking as well as the answer
FALLBACK = "server-side-fallback-2026-07-01"        # the beta under which a declined request is run again on the fallback model
KEPT = {"text": ("type", "text"), "tool_use": ("type", "id", "name", "input")}       # what a recording keeps of a block


@dataclass(frozen=True)
class Reply:
    """One answer of a model. `content`: its blocks as the Messages API gives them (text, tool_use, thinking). They go
    back into the conversation as they are: the loop never rewrites what a model said. `model`: the model that served
    the answer, when it is known."""
    content: tuple[dict, ...]
    stop_reason: str = "end_turn"          # end_turn, tool_use, max_tokens, refusal
    usage: dict = field(default_factory=dict)
    model: str | None = None

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


# ------------------------------------------------------------------------------------------------- the live model
def request_for(*, system: str, messages: list[dict], tools: list[dict], output: dict | None, effort: str,
                model: str = MODEL, fallback: bool = True) -> dict:
    """The request as the SDK takes it: the keywords of `messages.create`. Nothing is sent here, so a dry run can show
    exactly what a live call would send.

    - Thinking is adaptive and the effort is said: the model decides how much to think within it.
    - The system prompt is the same for every request of its kind: it is marked to be cached. A conversation with
      tools grows turn after turn, so each turn also caches what the previous one sent.
    - No tool is ever forced: this model refuses it. The prompt says when to call, and the loop checks that it did.
    - `fallback`: a request the safety classifiers decline for certain reasons is run again by the API on its fallback
      model, within the same call."""
    request: dict = {"model": model, "max_tokens": MAX_TOKENS,
                     "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                     "messages": messages, "thinking": {"type": "adaptive"}, "output_config": {"effort": effort}}
    if output is not None:
        request["output_config"]["format"] = {"type": "json_schema", "schema": output}
    if tools:
        request["tools"] = tools
        request["cache_control"] = {"type": "ephemeral"}
    if fallback:
        request["betas"], request["fallbacks"] = [FALLBACK], "default"
    return request


def reply_from(message) -> Reply:
    """An answer of the SDK as a `Reply`. Every block is kept as the API gave it, thinking included, so that it goes back
    unchanged in the next request of the same conversation."""
    used = message.usage
    usage = {name: getattr(used, name) for name in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
             if isinstance(getattr(used, name, None), int)}
    thinking = getattr(getattr(used, "output_tokens_details", None), "thinking_tokens", None)
    if isinstance(thinking, int):
        usage["thinking_tokens"] = thinking         # a part of the output tokens, not an addition to them
    return Reply(tuple(block.to_dict(mode="json") for block in message.content), message.stop_reason or "end_turn", usage, message.model)


def build_client():
    """The SDK's client. It finds the key in the environment by itself. The SDK is loaded here and nowhere else: the
    tests and the recorded mode never need it, and the tests fail if this function is called."""
    import anthropic
    return anthropic.Anthropic(max_retries=4)


class Live:
    """The live model. One client for all the requests of a process, built on the first call."""
    _shared = None

    def __init__(self, model: str = MODEL, fallback: bool = True, client=None):
        self.name, self.fallback, self._client = model, fallback, client

    @property
    def client(self):
        if self._client is None:
            if Live._shared is None:
                Live._shared = build_client()
            self._client = Live._shared
        return self._client

    def reply(self, *, system: str, messages: list[dict], tools: list[dict], output: dict | None, effort: str) -> Reply:
        request = request_for(system=system, messages=messages, tools=tools, output=output, effort=effort, model=self.name, fallback=self.fallback)
        api = self.client.beta.messages if "betas" in request else self.client.messages       # the fallback is a beta of the API
        return reply_from(api.create(**request))


# ------------------------------------------------------------------------------------- recording, and playing again
def plain_block(block: dict) -> dict | None:
    """A block of the model as a recording keeps it: its text, or its tool call. The thinking is not kept. It belongs
    to the conversation and to the account that made it, and nothing of it is ever shown."""
    keys = KEPT.get(block.get("type")) if isinstance(block, dict) else None
    return {key: block.get(key) for key in keys} if keys else None


def plain_request(request: dict) -> dict:
    """A request as a recording keeps it and as a replay compares it: what the loop built, with the blocks of the model
    reduced to what a recording keeps of them."""
    messages = []
    for message in request["messages"]:
        content = message["content"]
        if message["role"] == "assistant" and isinstance(content, (list, tuple)):
            content = [kept for kept in map(plain_block, content) if kept is not None]
        messages.append({"role": message["role"], "content": content})
    plain = {"system": request["system"], "messages": messages, "tools": request["tools"], "output": request["output"], "effort": request["effort"]}
    return json.loads(json.dumps(plain, ensure_ascii=False))            # as it comes back from a file


def plain_reply(reply: Reply) -> dict:
    return {"content": [kept for kept in map(plain_block, reply.content) if kept is not None], "stop_reason": reply.stop_reason,
            "usage": {key: value for key, value in reply.usage.items() if isinstance(value, (int, float)) and not isinstance(value, bool)},
            "model": reply.model}


class Recorder:
    """A model that passes every request on and keeps what was asked and what was answered. `turns` is what a
    recording is made of."""

    def __init__(self, model: Model):
        self.model, self.name = model, model.name
        self.turns: list[dict] = []

    def reply(self, *, system: str, messages: list[dict], tools: list[dict], output: dict | None, effort: str) -> Reply:
        request = {"system": system, "messages": messages, "tools": tools, "output": output, "effort": effort}
        asked = plain_request(request)                  # taken now: the conversation is the loop's, and it grows afterwards
        started = time.perf_counter()
        reply = self.model.reply(**request)
        self.turns.append({"request": asked, "reply": plain_reply(reply), "seconds": round(time.perf_counter() - started, 2)})
        return reply


class Stale(Exception):
    """A recorded exchange that is not the one Doors would have today. The engine, a prompt or the form has changed
    since: the recorded answer was given to another question, so it is not shown. `turn`: where they part, from 1."""

    def __init__(self, turn: int, part: str):
        super().__init__(f"turn {turn}: {part}")
        self.turn, self.part = turn, part


def _parting(today: dict, then: dict) -> str:
    """Where two requests differ, in a few words: the name of the part, and for the conversation the message."""
    for part in ("system", "tools", "output", "effort"):
        if today[part] != then[part]:
            return f"the {part} is not the one that was recorded"
    mine, theirs = today["messages"], then["messages"]
    for index, (now, recorded) in enumerate(zip(mine, theirs), start=1):
        if now != recorded:
            return f"message {index} of {len(theirs)} is not the one that was recorded"
    return f"the conversation holds {len(mine)} messages and the recording {len(theirs)}"


class Replay:
    """A recorded exchange played again, turn by turn, by the same loop as the live one. The tools run on the engine
    of today. A request that is not, to the letter, the request that was answered then stops the replay: `Stale`."""

    def __init__(self, turns: list[dict], name: str = MODEL):
        self.turns, self.name, self.played = turns, name, 0

    def reply(self, *, system: str, messages: list[dict], tools: list[dict], output: dict | None, effort: str) -> Reply:
        number = self.played + 1
        if self.played >= len(self.turns):
            raise Stale(number, f"the exchange asks for one more turn than the {len(self.turns)} recorded")
        today = plain_request({"system": system, "messages": messages, "tools": tools, "output": output, "effort": effort})
        turn = self.turns[self.played]
        if today != turn["request"]:
            raise Stale(number, _parting(today, turn["request"]))
        self.played = number
        answer = turn["reply"]
        return Reply(tuple(answer["content"]), answer["stop_reason"], dict(answer["usage"]), answer.get("model"))

    def finish(self) -> None:
        """Called when the loop is over: every recorded turn must have been played."""
        if self.played != len(self.turns):
            raise Stale(self.played + 1, f"the exchange stops after {self.played} turns and the recording holds {len(self.turns)}")
