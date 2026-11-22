"""What a live call costs: the tokens the API counted, priced; and before any call, an estimate.

The prices are those of the model's documentation, in US dollars per million tokens. The cost given after a real
call comes from the tokens the API reported for it. An estimate comes from a count of characters, which is not how the
API counts: it gives an order of size before anything is sent, and nothing more. Once real answers are recorded, the
estimate uses what they measured instead of what is assumed here.
"""
from __future__ import annotations

import json
import math

from ai.model import MAX_TOKENS, MODEL

# US dollars per million tokens: input, output (thinking included), writing the 5-minute cache, reading it.
PRICES = {
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_write": 2.50, "cache_read": 0.10},
    "claude-sonnet-5": {"input": 2.00, "output": 10.00, "cache_write": 2.50, "cache_read": 0.20},        # the fallback model
}
CHARACTERS_PER_TOKEN = 2.8          # assumed until an answer is recorded; the tokenizer of this model counts short
# Tokens of one answer, thinking included, by kind of request: a short one and a long one. Assumed until measured.
ASSUMED = {"ask": (150, 1500), "search": (300, 3000), "explain": (400, 3000)}
BILLED = {"input_tokens": "input", "output_tokens": "output", "cache_creation_input_tokens": "cache_write", "cache_read_input_tokens": "cache_read"}


def number(value: float) -> str:
    """A count as the screen of Doors writes one: 16'000."""
    return f"{value:,.0f}".replace(",", "'")


def usd(value: float | None) -> str:
    return "not priced" if value is None else f"{value:.4f} USD" if value < 1 else f"{value:.2f} USD"


def count(how_many: int, what: str) -> str:
    """A count with its noun: 1 request, 6 requests."""
    return f"{number(how_many)} {what}{'' if how_many == 1 else 's'}"


def span(low: float, high: float, write=number) -> str:
    """Two bounds, or one value when they are the same."""
    return write(low) if low == high else f"{write(low)} to {write(high)}"


def cost(usage: dict, model: str | None = MODEL) -> float | None:
    """The price of the tokens the API reported, in US dollars. None for a model whose prices are not listed here."""
    price = PRICES.get(model or MODEL)
    if price is None:
        return None
    return sum(usage.get(name, 0) * price[rate] for name, rate in BILLED.items()) / 1_000_000


def sent(usage: dict) -> int:
    """The tokens of a request as the API counted them: what was read from the cache, written to it, and the rest."""
    return usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0) + usage.get("cache_read_input_tokens", 0)


def kind_of(request: dict) -> str:
    """What a request is for: a turn of the search, the explanations, or one sentence to read."""
    if request.get("tools"):
        return "search"
    return "explain" if "explanations" in ((request.get("output") or {}).get("properties") or {}) else "ask"


def characters(request: dict) -> int:
    """The size of a request, in characters: the system prompt, the tools, the form, and the conversation."""
    size = len(request["system"])
    if request.get("tools"):
        size += len(json.dumps(request["tools"], ensure_ascii=False))
    if request.get("output") is not None:
        size += len(json.dumps(request["output"], ensure_ascii=False))
    for message in request["messages"]:
        content = message["content"]
        size += len(content) if isinstance(content, str) else len(json.dumps(content, ensure_ascii=False))
    return size


def measured(recordings: list[dict]) -> dict:
    """What the recorded answers measured: how many characters make a token, and the tokens of an answer by kind of
    request. Empty when nothing is recorded yet."""
    read, counted, answers = 0, 0, {}
    for recording in recordings:
        for turn in recording.get("turns", []):
            usage = turn["reply"].get("usage") or {}
            if sent(usage) > 0:
                read, counted = read + characters(turn["request"]), counted + sent(usage)
            if usage.get("output_tokens"):
                answers.setdefault(kind_of(turn["request"]), []).append(usage["output_tokens"])
    found = {"answers": {kind: {"count": len(tokens), "least": min(tokens), "most": max(tokens), "mean": round(sum(tokens) / len(tokens))}
                         for kind, tokens in sorted(answers.items())}}
    if counted:
        found["characters_per_token"] = round(read / counted, 2)
    return found


def estimate(requests: list[dict], measures: dict | None = None, model: str = MODEL) -> dict:
    """An estimate for one exchange, from the requests a stand-in made the loop build. Two cases and a ceiling:

    - low: the exchange as it was played, with short answers;
    - high: one more turn of search and two rewrites of the explanations, with long answers;
    - ceiling: the high case with every answer as long as the API allows.

    The input is priced as if nothing were read from the cache: caching lowers it after the first request of a kind,
    and writing the cache costs a quarter more on what is written."""
    measures = measures or {}
    per_token = measures.get("characters_per_token", CHARACTERS_PER_TOKEN)
    price = PRICES[model]
    tokens = lambda request: math.ceil(round(characters(request) / per_token, 6))

    def answer(kind: str) -> tuple[int, int]:
        seen = (measures.get("answers") or {}).get(kind)
        return (seen["least"], math.ceil(seen["most"] * 1.5)) if seen else ASSUMED[kind]     # half as much again above the longest seen

    played = [(kind_of(request), tokens(request)) for request in requests]
    longer = list(played)
    search = [size for kind, size in played if kind == "search"]
    explain = [size for kind, size in played if kind == "explain"]
    if search:                                      # a model may take one more turn than the stand-in to close its search
        longer.append(("search", search[-1] + (search[-1] - search[-2] if len(search) > 1 else 0)))
    if explain:                                     # each rewrite sends the facts again, with the refused text and what the checker said
        longer += [("explain", math.ceil(explain[0] * 1.3)), ("explain", math.ceil(explain[0] * 1.6))]
    cases = {}
    for name, turns, which in (("low", played, 0), ("high", longer, 1)):
        read, written = sum(size for _, size in turns), sum(answer(kind)[which] for kind, _ in turns)
        cases[name] = {"requests": len(turns), "input_tokens": read, "output_tokens": written,
                       "usd": (read * price["input"] + written * price["output"]) / 1_000_000}
    cases["ceiling_usd"] = (cases["high"]["input_tokens"] * price["input"] + len(longer) * MAX_TOKENS * price["output"]) / 1_000_000
    cases["characters_per_token"], cases["measured"] = per_token, sorted((measures.get("answers") or {}))
    return cases


def add(estimates: list[dict]) -> dict:
    """Several estimates as one: a series of exchanges."""
    total = {case: {key: sum(each[case][key] for each in estimates) for key in ("requests", "input_tokens", "output_tokens", "usd")} for case in ("low", "high")}
    total["ceiling_usd"] = sum(each["ceiling_usd"] for each in estimates)
    return total
