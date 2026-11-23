"""The live model, the recordings and the two modes (ai/model.py, ai/recordings.py, ai/service.py, the routes /ai/…).

No test here calls the model. The SDK is exercised for real, up to the moment a request would leave the machine: a
transport that answers locally takes its place. A recorded exchange is made with a stand-in for the model, then
played again the way a real one is.
"""
from __future__ import annotations

import offline  # noqa: F401  the recorded mode, and no client of the SDK: before anything else

import copy
import json
import os
import random
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai import ask as asking
from ai import benchmark, cost, recordings, rehearsal, service
from ai import model as M
from ai import stress as stressing
from ai import vocabulary as V
from ai.checker import Fact, check
from ai.model import Live, Recorder, Reply, Scripted, Stale, answers, request_for, says
from engine import i18n
from engine import worlds as W
from engine.assumptions import ASSUMPTIONS
from engine.blocks import BLOCKS, normalize
from engine.simulate import load_scenario
from engine.tree import Tree

try:
    import test_english
except ImportError:  # pragma: no cover
    test_english = None

try:
    import anthropic
    import httpx2
    from anthropic import DefaultHttpxClient
except ImportError:  # pragma: no cover
    anthropic = None

try:
    from fastapi.testclient import TestClient
    from api.main import app
except ImportError:  # pragma: no cover
    TestClient = None

ROOT = Path(__file__).resolve().parents[1]
ALEXIA = load_scenario(ROOT / "engine/scenarios/alexia.json")
TREE = Tree(ALEXIA)
H = ALEXIA.horizon_months
STORY = normalize(benchmark.ROUTES["story_a"], H)
WORK = normalize(benchmark.ROUTES["work_only"], H)
SHAPED = "sk-" + "ant-" + "api03-" + "k" * 60          # the shape of a key, put together here: it is not one
NINE = "What if I lost my job for 9 months at 27?"
NEUF = "Et si je perdais mon emploi pendant 9 mois à 27 ans ?"
FORM = {**rehearsal.EMPTY, "crises": [{"type": "chomage_6_mois", "age": 27, "size": 9, "unit": "months", "quote": "I lost my job for 9 months at 27"}]}
SPENT = {"input_tokens": 1000, "output_tokens": 100, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}


class Understudy(rehearsal.StandIn):
    """The stand-in, with a form that says something for “Ask”, and with tokens counted as the API counts them."""
    name = M.MODEL

    def reply(self, **request) -> Reply:
        fields = (request["output"] or {}).get("properties") or {}
        played = answers(FORM) if "route" in fields else super().reply(**request)
        return Reply(played.content, played.stop_reason, dict(SPENT), M.MODEL)


def understudy(tree: Tree = TREE) -> Understudy:
    return Understudy(rehearsal.sample(tree))


def recording_of(kind: str, lang: str = "en", sentence: str | None = None, path: list[dict] = STORY, model=None, **fields) -> dict:
    """An exchange made with a stand-in, as a recording: what scripts/record_ai.py writes for a live one."""
    recorder = Recorder(model or understudy())
    if kind == "stress":
        stressing.run(TREE, path, recorder, {}, lang, benchmark.truth_for(path, {}, H))
    else:
        asking.ask(TREE, sentence, recorder, path, {}, lang)
    return {"kind": kind, "language": lang, "scenario": "alexia", "label": "story_a", "path": path, "assumptions": {}, "sentence": sentence,
            "model": M.MODEL, "served_by": [M.MODEL], "recorded_at": "2026-11-23", "sdk": "2.12.0", "seconds": 1.0, "usage": {}, "cost_usd": 0.0,
            "turns": recorder.turns, **fields}


class Offline(unittest.TestCase):
    """What every test of this module starts from: nothing kept from another test, a directory of its own for the
    recordings, and the recorded mode."""

    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(recordings, "DIR", self.folder / "recorded"))
        self.enterContext(mock.patch.object(recordings, "LOG", self.folder / "ai_live.log"))
        self.enterContext(mock.patch.dict(os.environ, {"DOORS_AI": "recorded"}))
        service._hour.times.clear()
        service._played.clear()
        recordings._read.clear()

    def live(self, model=None, **environment):
        """The live mode for the rest of the test, with a model that is not the model: the live mode asked for, a
        key-shaped text in the environment, and `live_model` replaced."""
        self.enterContext(mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": SHAPED, "DOORS_AI": "live", **environment}))
        self.enterContext(mock.patch.object(service, "live_model", lambda: model or understudy()))

    def keep(self, *made: dict) -> list[dict]:
        for recording in made:
            recordings.write(recording)
        return recordings.every()


# ----------------------------------------------------------------------------------------------- the live model
class TheRequest(unittest.TestCase):
    """What the SDK is given. The dry run prints these very keywords."""

    TOOL = {"name": "test_worlds", "strict": True, "description": "d", "input_schema": {"type": "object", "additionalProperties": False, "required": [], "properties": {}}}

    def test_a_turn_of_the_search_the_explanations_and_a_sentence_to_read(self):
        messages = [{"role": "user", "content": "The route to test"}]
        cached = [{"type": "text", "text": "SYSTEM", "cache_control": {"type": "ephemeral"}}]
        common = {"model": "claude-sonnet-5-5", "max_tokens": 16000, "system": cached, "messages": messages, "thinking": {"type": "adaptive"}}
        fallback = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        search = request_for(system="SYSTEM", messages=messages, tools=[self.TOOL], output=None, effort="medium")
        self.assertEqual(search, {**common, "output_config": {"effort": "medium"}, "tools": [self.TOOL], "cache_control": {"type": "ephemeral"}, **fallback})
        schema = {"type": "object", "additionalProperties": False, "required": [], "properties": {}}
        sentence = request_for(system="SYSTEM", messages=messages, tools=[], output=schema, effort="low")
        self.assertEqual(sentence, {**common, "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}}, **fallback})
        plain = request_for(system="SYSTEM", messages=messages, tools=[], output=schema, effort="low", fallback=False)
        self.assertEqual(plain, {**common, "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}}})
        # Never a forced tool, a sampling parameter or a thinking budget: this model refuses each of them.
        for request in (search, sentence, plain):
            self.assertFalse({"tool_choice", "temperature", "top_p", "top_k", "budget_tokens", "stream"} & set(request))
            self.assertEqual(request["thinking"], {"type": "adaptive"})
        self.assertEqual((M.MODEL, M.MAX_TOKENS, M.FALLBACK), ("claude-sonnet-5-5", 16000, "server-side-fallback-2026-07-01"))

    def test_the_real_requests_of_doors_have_that_shape(self):
        """The requests the loops really build, taken from a rehearsal: each is accepted by `request_for` as it is."""
        requests = rehearsal.stress(TREE, STORY, None, "en") + rehearsal.ask(TREE, NINE, STORY, None, "en")
        self.assertEqual([cost.kind_of(request) for request in requests], ["search"] * 5 + ["explain", "ask"])
        for request, sent in zip(requests, rehearsal.as_sent(requests)):
            self.assertEqual((sent["system"][0]["text"], sent["messages"], sent["output_config"]["effort"]), (request["system"], request["messages"], request["effort"]))
            self.assertEqual("tools" in sent, bool(request["tools"]))
            self.assertEqual("cache_control" in sent, bool(request["tools"]))
            self.assertEqual("format" in sent["output_config"], request["output"] is not None)
        self.assertEqual([request["effort"] for request in requests], ["medium"] * 6 + ["low"])


def message(content: list[dict], stop_reason: str = "end_turn", model: str = "claude-sonnet-5-5", **usage) -> dict:
    """An answer of the API, as its JSON."""
    return {"id": "msg_local", "type": "message", "role": "assistant", "model": model, "content": content, "stop_reason": stop_reason,
            "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 5, **usage}}


@unittest.skipIf(anthropic is None, "the SDK is not installed: pip install -r requirements.txt")
class TheSdk(unittest.TestCase):
    """The SDK itself, with a transport that answers on this machine: what it would put on the wire, and what `Live`
    makes of what comes back. Nothing leaves the machine, and the client is given a text that is not a key."""

    def client(self, answer):
        self.sent = []

        def handler(request):
            body = json.loads(request.content)
            self.sent.append({"path": request.url.path, "beta": request.headers.get("anthropic-beta"), "body": body})
            return httpx2.Response(200, json=answer(body) if callable(answer) else answer)
        return anthropic.Anthropic(api_key="not-a-key", http_client=DefaultHttpxClient(transport=httpx2.MockTransport(handler)))

    def test_the_sdk_sends_the_request_as_it_is_built_and_the_answer_comes_back_block_for_block(self):
        blocks = [{"type": "thinking", "thinking": "", "signature": "signed-by-the-api"},
                  {"type": "text", "text": "I will test worlds."},
                  {"type": "tool_use", "id": "toolu_1", "name": "test_worlds", "input": {"worlds": ["krach@24"]}, "caller": {"type": "direct"}}]
        live = Live(client=self.client(message(blocks, "tool_use", cache_creation_input_tokens=700, cache_read_input_tokens=0,
                                               output_tokens_details={"thinking_tokens": 3})))
        asked = dict(system="SYSTEM", messages=[{"role": "user", "content": "brief"}], tools=[TheRequest.TOOL], output=None, effort="medium")
        reply = live.reply(**asked)
        sent, built = self.sent[0], request_for(**asked)
        self.assertEqual((sent["path"], sent["beta"]), ("/v1/messages", "server-side-fallback-2026-07-01"))
        self.assertEqual(sent["body"], {key: value for key, value in built.items() if key != "betas"})          # the beta goes in a header
        self.assertEqual((list(reply.content), reply.stop_reason, reply.model), (blocks, "tool_use", "claude-sonnet-5-5"))
        self.assertEqual(reply.usage, {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 700, "cache_read_input_tokens": 0, "thinking_tokens": 3})
        self.assertEqual((reply.text(), [call["id"] for call in reply.tool_calls()]), ("I will test worlds.", ["toolu_1"]))
        # The next request carries what the model said, thinking and signature included, exactly as it came.
        asked["messages"] = asked["messages"] + [{"role": "assistant", "content": list(reply.content)},
                                                 {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "{}"}]}]
        live.reply(**asked)
        self.assertEqual(self.sent[1]["body"]["messages"][1], {"role": "assistant", "content": blocks})

    def test_without_the_fallback_the_request_goes_to_the_plain_endpoint_with_no_beta(self):
        live = Live(fallback=False, client=self.client(message([{"type": "text", "text": "{}"}])))
        schema = {"type": "object", "additionalProperties": False, "required": [], "properties": {}}
        reply = live.reply(system="SYSTEM", messages=[{"role": "user", "content": "x"}], tools=[], output=schema, effort="low")
        self.assertEqual((self.sent[0]["path"], self.sent[0]["beta"], reply.text()), ("/v1/messages", None, "{}"))
        self.assertEqual(self.sent[0]["body"]["output_config"], {"effort": "low", "format": {"type": "json_schema", "schema": schema}})
        self.assertFalse({"fallbacks", "tools", "cache_control"} & set(self.sent[0]["body"]))

    def test_a_declined_request_is_a_reply_with_nothing_in_it(self):
        live = Live(client=self.client(message([], "refusal")))
        reply = live.reply(system="S", messages=[{"role": "user", "content": "x"}], tools=[], output=None, effort="low")
        self.assertEqual((reply.content, reply.stop_reason, reply.text()), ((), "refusal", ""))
        result = asking.ask(TREE, NINE, live, STORY, None, "en")
        self.assertEqual((result["understood"], result["not_understood"][0]["reason"]), (False, "The model declined to read this sentence."))

    def test_a_whole_stress_test_runs_through_the_sdk_and_its_conversation_only_grows(self):
        """The stand-in plays the model at the other end of the SDK: five turns of search with thinking blocks, then the
        explanations. Every request is looked at as it would have gone on the wire."""
        worlds = rehearsal.sample(TREE)

        def answer(body):
            if "tools" in body:
                turn = sum(each["role"] == "assistant" for each in body["messages"])
                return message([{"type": "thinking", "thinking": "", "signature": f"signature-{turn + 1}"},
                                {"type": "tool_use", "id": f"toolu_{turn + 1}", "name": "test_worlds", "input": {"worlds": worlds[turn * 8:turn * 8 + 8]},
                                 "caller": {"type": "direct"}}], "tool_use", cache_read_input_tokens=100 * turn)
            asked = body["output_config"]["format"]["schema"]["properties"]["explanations"]["items"]["properties"]["world"]["enum"]
            return message([{"type": "thinking", "thinking": "", "signature": "signature-explain"},
                            {"type": "text", "text": json.dumps({"explanations": [{"world": world, "text": rehearsal.PLAIN} for world in asked]})}])

        result = stressing.run(TREE, STORY, Live(client=self.client(answer)), None, "en")
        search, explain = self.sent[:5], self.sent[5:]
        self.assertEqual((len(self.sent), len(explain), result["budget"]["worlds_tested"], result["stopped"], result["model"]),
                         (6, 1, 40, "budget", "claude-sonnet-5-5"))
        self.assertEqual([world["explanation"]["accepted"] for world in result["ranking"]], [True] * len(result["ranking"]))
        self.assertEqual(result["usage"]["input_tokens"], 60)
        for number, sent in enumerate(search):
            body = sent["body"]
            self.assertEqual((body["system"], body["tools"], body["cache_control"], body["fallbacks"], body["output_config"]),
                             (search[0]["body"]["system"], search[0]["body"]["tools"], {"type": "ephemeral"}, "default", {"effort": "medium"}))
            self.assertEqual(len(body["messages"]), 1 + 2 * number)
            if number:
                before = search[number - 1]["body"]["messages"]
                self.assertEqual(body["messages"][:len(before)], before)                 # nothing already sent is rewritten
                said, results = body["messages"][-2], body["messages"][-1]
                self.assertEqual(said["content"][0], {"type": "thinking", "thinking": "", "signature": f"signature-{number}"})
                self.assertEqual((said["content"][1]["id"], said["content"][1]["caller"]), (f"toolu_{number}", {"type": "direct"}))
                self.assertEqual([(block["type"], block["tool_use_id"]) for block in results["content"]], [("tool_result", f"toolu_{number}")])
        told = explain[0]["body"]
        self.assertEqual((len(told["messages"]), "tools" in told, "cache_control" in told, told["output_config"]["effort"]), (1, False, False, "medium"))
        self.assertEqual(told["output_config"]["format"]["type"], "json_schema")

    def test_the_form_of_ask_goes_through_the_sdk_untouched(self):
        live = Live(client=self.client(message([{"type": "text", "text": json.dumps(FORM)}])))
        result = asking.ask(TREE, NINE, live, STORY, None, "en")
        body = self.sent[0]["body"]
        self.assertEqual(body["output_config"], {"effort": "low", "format": {"type": "json_schema", "schema": asking.form(TREE.theta(None), H, TREE.age0)}})
        self.assertEqual((result["world"]["id"], result["model"], body["system"][0]["cache_control"]), ("chomage_6_mois@27~150", "claude-sonnet-5-5", {"type": "ephemeral"}))


class TheLanguageOfWhatIsSent(unittest.TestCase):
    """For an English text, what the model is sent is in English: the prompts, the route, the goals, the names of the
    worlds, the notes of the ledger, the refusals of the engine, what the checker says of a refused text. The search is
    held in English even when the screen is in French. What stays as the engine writes it: its identifiers, which are
    code and not prose (krach, chomage_long, loyer, emploi), each given next to its English name."""

    @classmethod
    def setUpClass(cls):
        named = [world.id for world in W.WORLDS + W.EXTRA] + [assumption.key for assumption in ASSUMPTIONS] + list(asking.BRANCHES) + list(BLOCKS) + list(asking.WHY)
        cls.identifiers = re.compile(r"\b(?:" + "|".join(sorted(map(re.escape, named), key=len, reverse=True)) + r")\b")

    def french(self, text) -> list[str]:
        """The lines of a text where French is left once the identifiers of the engine are taken out."""
        text = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
        return [line for line in text.splitlines() if test_english.FRENCH.search(self.identifiers.sub("", line))]

    def sent(self, request: dict) -> list:
        """Every text of a request: the system prompt, the tool, the form, and each message."""
        return [request["system"], request["tools"], request["output"]] + [message["content"] for message in request["messages"]]

    def test_the_detector_sees_french_and_leaves_the_identifiers_alone(self):
        for text in ("Pas d'indemnité de chômage : 0 mois cotisés sur 24, il en faut 12", "Chômage long à 27 ans", "Krach des marchés", "un trajet", "12 mois",
                     "Rendement des placements (monde de référence)", "« Sans crise »"):
            self.assertTrue(self.french(text), text)
        for text in ("- chomage_long: Long unemployment. Job loss for twelve months", "krach@24+chomage_long@27", "- loyer: Rent [CHF/month], 900 in the engine",
                     "- emploi: take or keep a job in Lausanne", "Weaker franc at 21, severity 50%", "No unemployment benefit: 0 months contributed out of 24, 12 are required"):
            self.assertEqual(self.french(text), [], text)

    @unittest.skipIf(test_english is None, "the helpers of test_english are needed")
    def test_an_english_exchange_holds_no_french_whatever_the_default_language_of_the_process(self):
        sentences = ("What if I lost my job for 9 months at 27?", "With a rent of 1'500 CHF and a return of 5%, and 40'000 CHF set aside at 26.")
        usual = i18n.current()
        try:
            for default in ("en", "fr"):
                i18n.set_default(default)
                requests = [request for route in benchmark.ROUTES for request in rehearsal.stress(TREE, benchmark.ROUTES[route], {"loyer": 1500.0}, "en")]
                requests += [request for sentence in sentences for request in rehearsal.ask(TREE, sentence, STORY, {"loyer": 1500.0}, "en")]
                self.assertEqual(len(requests), 3 * 6 + 2)
                for number, request in enumerate(requests):
                    for text in self.sent(request):
                        with self.subTest(default=default, request=number):
                            self.assertEqual(self.french(text), [])
        finally:
            i18n.set_default(usual)

    @unittest.skipIf(test_english is None, "the helpers of test_english are needed")
    def test_the_search_of_a_french_exchange_is_held_in_english_and_its_explanations_are_asked_in_french(self):
        requests = rehearsal.stress(TREE, STORY, None, "fr")
        search, explain = requests[:5], requests[5]
        for request in search:
            for text in self.sent(request):
                self.assertEqual(self.french(text), [])
        self.assertEqual(self.french(explain["system"])[:1], ["You write short explanations for Doors, a financial twin for a student in Switzerland. The engine has simulated "
                                                              "Alexia's ten-year route in a few hard worlds. For each world you are given, write one or two sentences, in French, "
                                                              "that say what happens to the route in that world and why, in plain words, addressed to Alexia (« tu »)."])
        self.assertGreater(len(self.french(explain["messages"][0]["content"])), 60)             # the facts, in French

    @unittest.skipIf(test_english is None, "the helpers of test_english are needed")
    def test_the_names_the_notes_and_the_refusals_of_the_engine_are_in_english_for_any_world(self):
        draw = random.Random(7)
        notes = set()
        with i18n.use("en"):
            for key, path in benchmark.ROUTES.items():
                route = stressing.Route(Tree(ALEXIA), path)
                worlds = V.singles(route.th, route.h, route.age0)[::9] + draw.sample(list(V.pairs(route.th, route.h, route.age0)), 25) \
                    + ["chomage_long@23+chomage_long@24", "perte_job_etudiant@26", "chomage_long@27"]
                for world in worlds:
                    listed = stressing._listed(stressing.world_facts(route, world))
                    notes |= {line for line in listed if line.startswith("- Note of the ledger (quote): ")}
                    for text in (listed, route.name(world), stressing._told(route, route.detail(world))):
                        with self.subTest(route=key, world=world):
                            self.assertEqual(self.french(text if isinstance(text, (str, dict)) else "\n".join(text)), [])
                self.assertEqual(self.french("\n".join(stressing._listed(stressing.common_facts(route)))), [])
                for asked in ("meteorite@24", "krach@31", "krach@24~80", "krach@24+inflation@22+chomage_long@27", "krach@24+krach@24~150", "prudent", "", 12):
                    with self.assertRaises((ValueError, KeyError)) as refusal:
                        V.accept(asked, route.th, route.h, route.age0)
                    self.assertEqual(self.french(str(refusal.exception.args[0])), [])
            # What the checker tells the model about a refused text.
            report = check("You borrow about 43k CHF, double the usual, with a 30% chance, in krach@99.", [Fact.chf(43123.47, "Peak borrowing", "w", "borrowed")], ["w"], [], "en")
            self.assertGreater(len(report.problems), 3)
            self.assertEqual(self.french(report.feedback()), [])
        # The notes of the ledger, which the simulation keeps in French, reach the model in English.
        self.assertTrue({"- Note of the ledger (quote): “No unemployment benefit: 0 months contributed out of 24, 12 are required”",
                         "- Note of the ledger (quote): “Student job lost: no income this month, and no unemployment benefit”"} <= notes, sorted(notes))


class WhatGoesBackToTheModel(unittest.TestCase):
    """The API refuses a turn of the assistant with nothing in it. An answer that was declined, or that came back
    empty, is therefore never put into the conversation that is sent again."""

    def test_a_declined_or_empty_answer_is_not_a_turn_of_the_conversation(self):
        worlds = rehearsal.sample(TREE)
        search = [M.calls("test_worlds", {"worlds": worlds[turn * 8:turn * 8 + 8]}, f"call_{turn}") for turn in range(5)]
        plain = lambda request: answers({"explanations": [{"world": world, "text": rehearsal.PLAIN}
                                                         for world in request["output"]["properties"]["explanations"]["items"]["properties"]["world"]["enum"]]})
        # The explanations: declined once, then empty, then written.
        model = Scripted(search + [Reply((), "refusal"), Reply(()), plain])
        result = stressing.run(TREE, STORY, model, None, "en")
        self.assertEqual([world["explanation"]["attempts"] for world in result["ranking"]], [3] * len(result["ranking"]))
        for request in model.requests[5:]:
            self.assertEqual([message["role"] for message in request["messages"]], ["user"] * len(request["messages"]))
            self.assertTrue(all(message["content"] for message in request["messages"]))
        self.assertEqual([len(request["messages"]) for request in model.requests[5:]], [1, 2, 3])
        # The search: an empty answer first, which gets the one reminder, then the calls.
        model = Scripted([Reply(())] + search + [plain])
        result = stressing.run(TREE, STORY, model, None, "en")
        self.assertEqual((result["stopped"], result["budget"]["worlds_tested"]), ("budget", 40))
        self.assertEqual([message["role"] for message in model.requests[1]["messages"]], ["user", "user"])
        for request in model.requests:
            self.assertTrue(all(message["content"] for message in request["messages"]))


# ------------------------------------------------------------------------------------- recording, and playing again
class RecordedAndPlayedAgain(Offline):
    def test_a_recorder_keeps_what_was_asked_and_what_was_answered_without_the_thinking(self):
        thinking = {"type": "thinking", "thinking": "", "signature": "signed"}
        call = {"type": "tool_use", "id": "toolu_1", "name": "test_worlds", "input": {"worlds": ["krach@24"]}, "caller": {"type": "direct"}}
        first = Reply((thinking, {"type": "text", "text": "Testing.", "citations": None}, call), "tool_use", {"input_tokens": 7, "output_tokens": 3, "service_tier": "standard"}, "claude-sonnet-5-5")
        recorder = Recorder(Scripted([first, says("Done.")], name="claude-sonnet-5-5"))
        messages = [{"role": "user", "content": "brief"}]
        reply = recorder.reply(system="S", messages=messages, tools=[TheRequest.TOOL], output=None, effort="medium")
        self.assertIs(reply, first)                                                     # the loop gets the answer as it is, thinking included
        messages += [{"role": "assistant", "content": list(reply.content)}, {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "{}"}]}]
        recorder.reply(system="S", messages=messages, tools=[TheRequest.TOOL], output=None, effort="medium")
        kept = [{"type": "text", "text": "Testing."}, {"type": "tool_use", "id": "toolu_1", "name": "test_worlds", "input": {"worlds": ["krach@24"]}}]
        self.assertEqual(recorder.turns[0]["request"]["messages"], [{"role": "user", "content": "brief"}])           # as it was when it was asked
        self.assertEqual(recorder.turns[0]["reply"], {"content": kept, "stop_reason": "tool_use", "usage": {"input_tokens": 7, "output_tokens": 3},
                                                      "model": "claude-sonnet-5-5"})
        self.assertEqual(recorder.turns[1]["request"]["messages"][1], {"role": "assistant", "content": kept})
        self.assertNotIn("signed", json.dumps(recorder.turns))
        self.assertEqual((recorder.name, [set(turn) for turn in recorder.turns]), ("claude-sonnet-5-5", [{"request", "reply", "seconds"}] * 2))

    def test_a_recording_played_again_gives_the_answer_of_the_live_run(self):
        for kind, lang, sentence in (("stress", "en", None), ("stress", "fr", None), ("ask", "en", NINE), ("ask", "fr", NEUF)):
            recorder = Recorder(understudy())
            live = stressing.run(TREE, STORY, recorder, {}, lang, benchmark.truth_for(STORY, {}, H)) if kind == "stress" else \
                asking.ask(TREE, sentence, recorder, STORY, {}, lang)
            recording = json.loads(json.dumps(recording_of(kind, lang, sentence)))        # as it comes back from a file
            exchange = lambda turns: [(turn["request"], turn["reply"]) for turn in json.loads(json.dumps(turns))]
            self.assertEqual(exchange(recording["turns"]), exchange(recorder.turns))      # the same exchange, made twice: nothing in it is left to chance
            with self.subTest(kind=kind, lang=lang):
                played = service.replay(TREE, recording)
                self.assertEqual(json.loads(json.dumps(played)), json.loads(json.dumps(live)))
                self.assertEqual((played["model"], played["language"]), ("claude-sonnet-5-5", lang))

    def test_the_tools_of_a_replay_run_on_the_engine_of_today_and_a_changed_figure_refuses_the_recording(self):
        recording = recording_of("stress")
        self.assertEqual(len(recording["turns"]), 6)
        # The engine of today gives one franc more of peak borrowing for the worlds of the first call: the second request is not the one recorded.
        told = stressing._told

        def one_franc_more(route, detail):
            return {**told(route, detail), "peak_borrowing_chf": told(route, detail)["peak_borrowing_chf"] + 1}
        with mock.patch.object(stressing, "_told", one_franc_more), self.assertRaises(Stale) as stale:
            service.replay(TREE, recording)
        self.assertEqual((stale.exception.turn, stale.exception.part), (2, "message 3 of 3 is not the one that was recorded"))
        # A prompt, the tool or the form changed since: refused at the first turn, with the name of what changed.
        for part, change in (("system", lambda request: request.update(system=request["system"] + " ")),
                             ("tools", lambda request: request["tools"][0].update(description="another")),
                             ("effort", lambda request: request.update(effort="high")),
                             ("output", lambda request: request.update(output={"type": "object"}))):
            changed = copy.deepcopy(recording)
            change(changed["turns"][0]["request"])
            with self.subTest(part=part), self.assertRaises(Stale) as stale:
                service.replay(TREE, changed)
            self.assertEqual((stale.exception.turn, stale.exception.part), (1, f"the {part} is not the one that was recorded"))
        # A recording cut short, or with a turn the exchange never reaches.
        with self.assertRaises(Stale) as stale:
            service.replay(TREE, {**recording, "turns": recording["turns"][:3]})
        self.assertEqual(str(stale.exception), "turn 4: the exchange asks for one more turn than the 3 recorded")
        with self.assertRaises(Stale) as stale:
            service.replay(TREE, {**recording, "turns": recording["turns"] + recording["turns"][-1:]})
        self.assertEqual(str(stale.exception), "turn 7: the exchange stops after 6 turns and the recording holds 7")
        self.assertEqual(service.replay(TREE, recording)["budget"]["worlds_tested"], 40)                      # untouched, it still plays

    def test_the_checker_reads_a_recorded_text_again_and_a_figure_it_refuses_refuses_the_recording(self):
        recording = recording_of("stress")
        written = json.loads(recording["turns"][-1]["reply"]["content"][0]["text"])
        self.assertEqual({item["text"] for item in written["explanations"]}, {rehearsal.PLAIN})
        # The same recording, with a figure the engine never gave in one of its texts.
        written["explanations"][0]["text"] = "You borrow 99'999 CHF in this world."
        tampered = copy.deepcopy(recording)
        tampered["turns"][-1]["reply"]["content"][0]["text"] = json.dumps(written)
        with self.assertRaises(Stale) as stale:
            service.replay(TREE, tampered)
        # The checker refused the text and the loop asked for another one, which the recording does not hold.
        self.assertEqual(str(stale.exception), "turn 7: the exchange asks for one more turn than the 6 recorded")

    def test_a_recording_is_found_for_exactly_what_it_answers(self):
        kept = self.keep(recording_of("stress", "en"), recording_of("stress", "fr"), recording_of("ask", "en", NINE), recording_of("ask", "fr", NEUF))
        self.assertEqual([each["file"] for each in kept], ["ask.en.what-if-i-lost-my-job-for-9-months-at-27.json",
                                                           "ask.fr.et-si-je-perdais-mon-emploi-pendant-9-mois-a-27.json",
                                                           "stress.story-a.en.json", "stress.story-a.fr.json"])
        self.assertEqual({each["format"] for each in kept}, {1})
        find = lambda *asked, **more: (recordings.find(*asked, **more) or {}).get("file")
        self.assertEqual(find("stress", "en", "alexia", STORY, {}), "stress.story-a.en.json")
        self.assertEqual(find("stress", "fr", "alexia", STORY, None), "stress.story-a.fr.json")
        self.assertEqual(find("ask", "en", "alexia", STORY, {}, "  What if I lost my job   for 9 months at 27?\n"), "ask.en.what-if-i-lost-my-job-for-9-months-at-27.json")
        # Another route, other assumptions, another scenario, another sentence, the other language: nothing is approached.
        for asked in (("stress", "en", "alexia", WORK, {}), ("stress", "en", "alexia", STORY, {"loyer": 1500.0}), ("stress", "en", "other", STORY, {}),
                      ("ask", "en", "alexia", STORY, {}, "What if I lost my job for 9 months at 26?"), ("ask", "en", "alexia", STORY, {}, NEUF),
                      ("ask", "en", "alexia", STORY, {}, NINE.lower()), ("ask", "en", "alexia", STORY, {}, None), ("ask", "en", "alexia", WORK, {}, NINE)):
            with self.subTest(asked=asked[:2] + asked[4:]):
                self.assertIsNone(find(*asked))
        self.assertEqual(recordings.listing("alexia"), {
            "stress": [{"language": lang, "path": STORY, "assumptions": {}, "model": "claude-sonnet-5-5", "recorded_at": "2026-11-23"} for lang in ("en", "fr")],
            "ask": [{"language": "en", "path": STORY, "assumptions": {}, "model": "claude-sonnet-5-5", "recorded_at": "2026-11-23", "sentence": NINE},
                    {"language": "fr", "path": STORY, "assumptions": {}, "model": "claude-sonnet-5-5", "recorded_at": "2026-11-23", "sentence": NEUF}]})
        self.assertEqual(recordings.listing("other"), {"stress": [], "ask": []})
        # A file changed on disk is read again.
        recordings.write(recording_of("ask", "en", NINE, recorded_at="2026-12-01"))
        self.assertEqual(recordings.find("ask", "en", "alexia", STORY, {}, NINE)["recorded_at"], "2026-12-01")

    def test_nothing_shaped_like_a_key_is_ever_written(self):
        self.assertEqual(recordings.scrub(f"Bearer {SHAPED} was refused"), "Bearer [key removed] was refused")
        self.assertEqual(recordings.scrub("a risk of 3 goals, sk-ant, ant-1234"), "a risk of 3 goals, sk-ant, ant-1234")
        leaking = recording_of("ask", "en", NINE)
        leaking["turns"][0]["reply"]["content"][0]["text"] += SHAPED
        file = recordings.write(leaking)
        self.assertNotIn(SHAPED, file.read_text(encoding="utf-8"))
        self.assertIn("[key removed]", file.read_text(encoding="utf-8"))

        class Refused(Exception):
            status_code, message = 401, f"invalid key {SHAPED}"
        self.assertEqual(recordings.describe(Refused("x")), {"type": "Refused", "status": 401, "message": "invalid key [key removed]"})
        self.assertEqual(recordings.describe(ValueError(f"no {SHAPED}")), {"type": "ValueError", "status": None, "message": "no [key removed]"})
        recordings.log({"command": "check", "ok": False, "error": {"message": f"{SHAPED}"}})
        logged = json.loads(recordings.LOG.read_text(encoding="utf-8"))
        self.assertEqual((logged["command"], logged["error"], set(logged)), ("check", {"message": "[key removed]"}, {"at", "command", "ok", "error"}))
        self.assertEqual((recordings.shown(ROOT / "ai" / "recorded" / "x.json"), recordings.shown(self.folder / "x.json")), ("ai/recorded/x.json", "x.json"))


# ---------------------------------------------------------------------------------------------------- the two modes
class TheModes(Offline):
    def test_the_live_mode_takes_both_the_key_and_doors_ai_live(self):
        """A key exported in a terminal is not enough: the page never spends on its own. And asking for the live mode
        without a key gives the recorded mode, which says why."""
        recorded = "Recorded mode: no request leaves this machine. The live mode takes DOORS_AI=live and a key (ANTHROPIC_API_KEY) on the server."
        no_key = "Recorded mode: DOORS_AI=live is set, but the server has no key (ANTHROPIC_API_KEY)."
        live = "Live mode: the model (claude-sonnet-5-5) is called for each request."
        for environment, expected, why in (({}, "recorded", recorded), ({"ANTHROPIC_API_KEY": SHAPED}, "recorded", recorded),
                                           ({"ANTHROPIC_API_KEY": SHAPED, "DOORS_AI": "recorded"}, "recorded", recorded),
                                           ({"ANTHROPIC_API_KEY": SHAPED, "DOORS_AI": "yes"}, "recorded", recorded),
                                           ({"DOORS_AI": "live"}, "recorded", no_key), ({"ANTHROPIC_API_KEY": "", "DOORS_AI": "live"}, "recorded", no_key),
                                           ({"ANTHROPIC_API_KEY": SHAPED, "DOORS_AI": "live"}, "live", live),
                                           ({"ANTHROPIC_API_KEY": SHAPED, "DOORS_AI": " Live "}, "live", live)):
            with self.subTest(environment=sorted(environment.items())), mock.patch.dict(os.environ, environment), i18n.use("en"):
                for name in ("ANTHROPIC_API_KEY", "DOORS_AI"):
                    if name not in environment:
                        os.environ.pop(name, None)
                self.assertEqual((service.mode(), service.why(), service.status()["mode"], service.status()["why"]), (expected, why, expected, why))
                self.assertNotIn(SHAPED, json.dumps(service.status()))
        with mock.patch.dict(os.environ, {"DOORS_AI": "live"}), i18n.use("fr"):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            self.assertEqual(service.why(), "Mode enregistré : DOORS_AI=live est réglé, mais le serveur n'a pas de clé (ANTHROPIC_API_KEY).")
        self.assertEqual(service.mode(), "recorded")                # the tests themselves: whatever the terminal they are run from

    def test_no_test_can_build_the_client_of_the_sdk(self):
        with self.assertRaises(AssertionError) as refused:
            Live().client
        self.assertIn("No test may call the model", str(refused.exception))
        self.assertIsNone(Live._shared)

    def test_the_status_says_the_mode_the_limits_and_what_is_recorded_and_never_the_key(self):
        self.keep(recording_of("stress"), recording_of("ask", "fr", NEUF))
        status = service.status("alexia")
        self.assertEqual(sorted(status), ["limits", "mode", "model", "recorded", "why"])
        self.assertEqual({key: status[key] for key in ("mode", "model", "limits")},
                         {"mode": "recorded", "model": "claude-sonnet-5-5",
                          "limits": {"sentence_characters": 400, "live_requests_per_hour": None, "live_requests_left": None}})
        self.assertEqual(([each["language"] for each in status["recorded"]["stress"]], [each["sentence"] for each in status["recorded"]["ask"]]), (["en"], [NEUF]))
        self.live()
        status = service.status("alexia")
        self.assertEqual((status["mode"], status["limits"]), ("live", {"sentence_characters": 400, "live_requests_per_hour": 20, "live_requests_left": 20}))
        self.assertNotIn(SHAPED, json.dumps(status))
        self.assertNotIn("sk-", json.dumps(status))

    def test_in_recorded_mode_a_stress_test_is_the_recording_of_that_route_played_again(self):
        self.keep(recording_of("stress", "en"), recording_of("stress", "fr"))
        answer = service.stress(TREE, benchmark.ROUTES["story_a"], None, "en")
        self.assertEqual({key: value for key, value in answer.items() if key not in ("result", "scan")},
                         {"mode": "recorded", "available": True, "source": "recorded", "model": "claude-sonnet-5-5", "recorded_at": "2026-11-23",
                          "label": "Recorded answer · claude-sonnet-5-5 · 2026-11-23", "notice": None, "reason": None, "engine": None})
        direct = stressing.run(TREE, STORY, understudy(), {}, "en", benchmark.truth_for(STORY, {}, H))
        self.assertEqual(json.loads(json.dumps(answer["result"])), json.loads(json.dumps(direct)))
        self.assertEqual(answer["result"]["verification"]["benchmark"]["route"], "story_a")
        self.assertIs(service.stress(TREE, STORY, {}, "en")["result"], answer["result"])           # played once, then kept
        french = service.stress(TREE, STORY, None, "fr")
        self.assertEqual((french["label"], french["result"]["language"], french["result"]["rejected_label"]),
                         ("Réponse enregistrée · claude-sonnet-5-5 · 2026-11-23", "fr", "Explication de l'IA rejetée par le contrôleur"))
        # No recording for another route or other assumptions: it is said, and nothing is made up.
        for path, overrides, lang, why in ((WORK, None, "en", "No recorded answer for this route with these assumptions."),
                                           (STORY, {"loyer": 1500.0}, "en", "No recorded answer for this route with these assumptions."),
                                           (WORK, None, "fr", "Pas de réponse enregistrée pour ce trajet avec ces hypothèses.")):
            missing = service.stress(TREE, path, overrides, lang)
            self.assertEqual({key: value for key, value in missing.items() if key not in ("engine", "scan")},
                             {"mode": "recorded", "available": False, "source": None, "model": None, "recorded_at": None, "label": None, "notice": None,
                              "reason": why, "result": None})
        with self.assertRaises(ValueError) as refused, i18n.use("en"):
            service.stress(TREE, [{"block": "job", "years": 3}], None, "en")
        self.assertEqual(str(refused.exception), "The route covers 3 years: 10 are needed.")

    def test_with_no_answer_of_the_model_the_engine_says_what_it_finds_on_its_own(self):
        """A route with no recording: the screen is told so, and given what the engine finds with no model at all. That
        part is the engine's and is never labelled as an answer."""
        answer = service.stress(TREE, STORY, None, "en")
        self.assertEqual((answer["available"], answer["source"], answer["label"], answer["result"], answer["reason"]),
                         (False, None, None, None, "No recorded answer for this route with these assumptions."))
        engine, direct = answer["engine"], stressing.Route(Tree(ALEXIA), STORY)
        self.assertEqual(sorted(engine), ["calm", "single_crises", "space"])
        self.assertEqual(engine["calm"], {"goals_kept": 3, "goals_total": 6, "peak_financing_chf": round(direct.calm.peak_financing_chf, 2),
                                          "net_worth_end_chf": round(direct.calm.net_worth_end_chf, 2)})
        single = engine["single_crises"]
        self.assertEqual((single["scanned"], single["max_goals_lost"], [world["world"] for world in single["hardest"]], engine["space"]["worlds"]),
                         (315, 2, ["chomage_long@27"], 49140))
        self.assertEqual((single["hardest"][0]["name"], single["hardest"][0]["goals_lost_names"]), ("Long unemployment at 27", ["Career change", "Resilience"]))
        # For a route of the benchmark, the full scan made offline, with the names of its hardest worlds.
        scan = answer["scan"]
        self.assertEqual((scan["route"], scan["worlds"], scan["max_goals_lost"], scan["hardest_count"], [world["world"] for world in scan["hardest"]][:1]),
                         ("story_a", 49140, 3, 47, ["chomage_long@23+chomage_long@24"]))
        self.assertEqual((scan["hardest"][0]["name"], scan["hardest"][0]["goals_lost_names"]),
                         ("Long unemployment at 23 + long unemployment at 24", ["Emergency savings", "Career change", "Resilience"]))
        # In French the names are French, and the figures are the same. Another route or other assumptions: no scan to cite.
        french = service.stress(TREE, STORY, None, "fr")
        self.assertEqual((french["engine"]["single_crises"]["hardest"][0]["name"], french["scan"]["hardest"][0]["name"]),
                         ("Chômage long à 27 ans", "Chômage long à 23 ans + chômage long à 24 ans"))
        self.assertEqual(french["engine"]["calm"], engine["calm"])
        other = service.stress(TREE, STORY, {"loyer": 1500.0}, "en")
        self.assertEqual((other["scan"], other["engine"]["single_crises"]["scanned"]), (None, 315))
        # And what the engine finds on its own is found with her assumptions: with this rent the route keeps one goal less with no crisis.
        self.assertEqual(other["engine"], stressing.alone(TREE, STORY, {"loyer": 1500.0}, "en"))
        self.assertEqual((other["engine"]["calm"]["goals_kept"], other["engine"]["single_crises"]["max_goals_lost"]), (2, 1))
        self.assertNotEqual(other["engine"]["calm"], engine["calm"])
        # With an answer to show, the engine's own part is left out: the answer carries its own check of the search.
        self.keep(recording_of("stress"))
        shown = service.stress(TREE, STORY, None, "en")
        self.assertEqual((shown["available"], shown["engine"], shown["scan"]["route"]), (True, None, "story_a"))

    def test_in_recorded_mode_a_sentence_is_answered_only_if_it_is_a_recorded_one(self):
        self.keep(recording_of("ask", "en", NINE), recording_of("ask", "fr", NEUF))
        answer = service.ask(TREE, "  What if I lost my job for   9 months at 27? ", STORY, None, "en")
        self.assertEqual((answer["source"], answer["label"], answer["result"]["world"]["id"], answer["result"]["sentence"]),
                         ("recorded", "Recorded answer · claude-sonnet-5-5 · 2026-11-23", "chomage_6_mois@27~150", NINE))
        self.assertEqual(answer["result"]["world"]["crises"][0]["conversion"],
                         "You ask for 9 months: severity 150% of “Six months of unemployment”, usually 6 months. The engine builds 9 months.")
        for sentence, path, lang, why in (("What if I lost my job for 9 months at 26?", STORY, "en", "No recorded answer for this sentence on this route."),
                                          (NINE, WORK, "en", "No recorded answer for this sentence on this route."),
                                          (NINE, STORY, "fr", "Pas de réponse enregistrée pour cette phrase sur ce trajet.")):
            missing = service.ask(TREE, sentence, path, None, lang)
            self.assertEqual((missing["available"], missing["source"], missing["reason"], missing["result"]), (False, None, why, None))
        # An empty sentence, or one that is too long, is answered by code in either mode: no model, no recording.
        for sentence, why in (("  ", "Write a sentence: what would you like to try?"), ("What if " * 60, "One sentence at a time: 400 characters at most.")):
            answer = service.ask(TREE, sentence, STORY, None, "en")
            self.assertEqual((answer["available"], answer["source"], answer["label"], answer["result"]["not_understood"][0]["reason"]), (True, "code", None, why))

    def test_a_recording_that_no_longer_matches_the_engine_is_not_shown(self):
        stale = recording_of("stress")
        stale["turns"][0]["request"]["system"] += " (an older prompt)"
        self.keep(stale)
        for lang, why in (("en", "The recorded answer no longer matches the engine: it is not shown."),):
            answer = service.stress(TREE, STORY, None, lang)
            self.assertEqual((answer["available"], answer["source"], answer["reason"], answer["result"]), (False, None, why, None))
        self.assertEqual(service._played, {})

    def test_in_live_mode_the_model_answers_and_the_answer_says_so(self):
        self.keep(recording_of("stress", recorded_at="2026-01-01"))
        self.live()
        answer = service.stress(TREE, STORY, None, "en")
        self.assertEqual({key: value for key, value in answer.items() if key not in ("result", "scan")},
                         {"mode": "live", "available": True, "source": "live", "model": "claude-sonnet-5-5", "recorded_at": None,
                          "label": "Live answer · claude-sonnet-5-5", "notice": None, "reason": None, "engine": None})
        self.assertEqual((answer["result"]["budget"]["worlds_tested"], answer["result"]["usage"]["input_tokens"]), (40, 6000))
        # For a route of the benchmark, the answer also carries what the full scan found, to hold the search against it.
        self.assertEqual((answer["result"]["verification"]["benchmark"]["route"], answer["result"]["verification"]["benchmark"]["max_goals_lost"]), ("story_a", 3))
        self.assertIsNone(service.stress(TREE, STORY, {"loyer": 1500.0}, "en")["result"]["verification"]["benchmark"])        # other assumptions: no scan to cite
        asked = service.ask(TREE, "Whatever she types, the model reads it.", WORK, {"loyer": 1500.0}, "fr")
        self.assertEqual((asked["source"], asked["label"], asked["result"]["world"]["id"]), ("live", "Réponse en direct · claude-sonnet-5-5", "chomage_6_mois@27~150"))
        self.assertEqual(service.status()["limits"]["live_requests_left"], 17)
        for answer in (answer, asked, service.status()):
            self.assertNotIn(SHAPED, json.dumps(answer, ensure_ascii=False))

    def test_past_the_hourly_limit_the_live_mode_gives_the_recorded_answer_and_says_why(self):
        self.keep(recording_of("ask", "en", NINE))
        self.live(DOORS_AI_PER_HOUR="2")
        self.assertEqual([service.ask(TREE, NINE, STORY, None, "en")["source"] for _ in range(2)], ["live", "live"])
        third = service.ask(TREE, NINE, STORY, None, "en")
        self.assertEqual((third["source"], third["notice"], third["label"]),
                         ("recorded", "The limit of 2 live requests per hour is reached.", "Recorded answer · claude-sonnet-5-5 · 2026-11-23"))
        other = service.ask(TREE, "Another sentence, with no recording.", STORY, None, "fr")
        self.assertEqual((other["available"], other["notice"], other["reason"]),
                         (False, "La limite de 2 demandes en direct par heure est atteinte.", "Pas de réponse enregistrée pour cette phrase sur ce trajet."))
        self.assertEqual(service.status()["limits"], {"sentence_characters": 400, "live_requests_per_hour": 2, "live_requests_left": 0})
        # An hour later, the requests of the hour before no longer count.
        with mock.patch.object(service.time, "monotonic", lambda real=service.time.monotonic: real() + 3601):
            self.assertEqual((service.status()["limits"]["live_requests_left"], service.ask(TREE, NINE, STORY, None, "en")["source"]), (2, "live"))

    def test_when_the_live_call_fails_the_answer_says_so_and_gives_the_recorded_one(self):
        class RateLimitError(Exception):
            status_code = 429
        RateLimitError.__module__ = "anthropic"

        class Unreachable:
            name = M.MODEL

            def reply(self, **request):
                raise RateLimitError(f"too many requests for {SHAPED}")
        self.keep(recording_of("stress"))
        self.live(Unreachable())
        answer = service.stress(TREE, STORY, None, "en")
        self.assertEqual((answer["source"], answer["notice"], answer["result"]["budget"]["worlds_tested"]),
                         ("recorded", "The live model could not be reached (RateLimitError).", 40))
        missing = service.stress(TREE, WORK, None, "fr")
        self.assertEqual((missing["available"], missing["notice"], missing["reason"]),
                         (False, "Le modèle en direct n'a pas pu être joint (RateLimitError).", "Pas de réponse enregistrée pour ce trajet avec ces hypothèses."))
        for answer in (answer, missing):
            self.assertNotIn("too many requests", json.dumps(answer))              # the message of the error is not shown, only its kind
            self.assertNotIn(SHAPED, json.dumps(answer))

    def test_a_fault_of_the_code_is_not_dressed_as_a_failure_of_the_network(self):
        class Broken:
            name = M.MODEL

            def reply(self, **request):
                raise KeyError("a bug")
        self.live(Broken())
        with self.assertRaises(KeyError):
            service.ask(TREE, NINE, STORY, None, "en")
        self.assertIsNone(service._unreached(KeyError("a bug")))
        self.assertIsNotNone(service._unreached(TypeError("Could not resolve authentication method. Expected one of api_key, auth_token…")))


# -------------------------------------------------------------------------------------------------------- the routes
@unittest.skipIf(TestClient is None, "FastAPI is not installed: pip install -r requirements.txt")
class TheRoutes(Offline):
    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(app)

    def test_the_status(self):
        self.keep(recording_of("stress"), recording_of("ask", "en", NINE))
        status = self.c.get("/ai/status").json()
        self.assertEqual((status["mode"], status["model"], status["limits"]["sentence_characters"]), ("recorded", "claude-sonnet-5-5", 400))
        self.assertEqual((len(status["recorded"]["stress"]), status["recorded"]["ask"][0]["sentence"]), (1, NINE))
        self.assertEqual(self.c.get("/ai/status?lang=fr").json(), status)
        self.assertEqual(self.c.get("/ai/status?scenario_id=unknown").status_code, 404)

    def test_the_stress_test_of_the_demo_route_in_both_languages(self):
        self.keep(recording_of("stress", "en"), recording_of("stress", "fr"))
        answer = self.c.post("/ai/stress?lang=en", json={}).json()                     # no route given: the demo route
        self.assertEqual((answer["source"], answer["label"], answer["result"]["path"], answer["result"]["budget"]["worlds_tested"]),
                         ("recorded", "Recorded answer · claude-sonnet-5-5 · 2026-11-23", STORY, 40))
        french = self.c.post("/ai/stress?lang=fr", json={"path": benchmark.ROUTES["story_a"], "assumptions": {}}).json()
        self.assertEqual((french["label"], french["result"]["language"]), ("Réponse enregistrée · claude-sonnet-5-5 · 2026-11-23", "fr"))
        self.assertEqual(len(french["result"]["tested"]), 40)
        other = self.c.post("/ai/stress?lang=en", json={"path": benchmark.ROUTES["work_only"]})
        self.assertEqual((other.status_code, other.json()["available"], other.json()["reason"]), (200, False, "No recorded answer for this route with these assumptions."))
        refused = self.c.post("/ai/stress?lang=en", json={"path": [{"block": "job", "years": 3}]})
        self.assertEqual((refused.status_code, refused.json()["detail"]), (422, "The route covers 3 years: 10 are needed."))

    def test_a_sentence(self):
        self.keep(recording_of("ask", "en", NINE), recording_of("ask", "fr", NEUF))
        answer = self.c.post("/ai/ask?lang=en", json={"sentence": NINE}).json()
        self.assertEqual((answer["source"], answer["result"]["settings"]["world"], answer["result"]["understood"]), ("recorded", "chomage_6_mois@27~150", True))
        french = self.c.post("/ai/ask?lang=fr", json={"sentence": NEUF, "path": STORY}).json()
        self.assertEqual(french["result"]["world"]["crises"][0]["conversion"],
                         "Tu demandes 9 mois : gravité 150 % de « Six mois de chômage », d'habitude 6 mois. Le moteur construit 9 mois.")
        unknown = self.c.post("/ai/ask?lang=en", json={"sentence": "What if I won the lottery?"}).json()
        self.assertEqual((unknown["available"], unknown["reason"]), (False, "No recorded answer for this sentence on this route."))
        empty = self.c.post("/ai/ask?lang=fr", json={}).json()
        self.assertEqual((empty["source"], empty["result"]["not_understood"][0]["reason"]), ("code", "Écris une phrase : que veux-tu essayer ?"))
        long = self.c.post("/ai/ask?lang=en", json={"sentence": "What if " * 60}).json()
        self.assertEqual(long["result"]["not_understood"][0]["reason"], "One sentence at a time: 400 characters at most.")
        self.assertEqual(self.c.post("/ai/ask", json={"sentence": "x" * 4001}).status_code, 422)
        self.assertEqual(self.c.post("/ai/ask", json={"sentence": NINE, "path": [{"block": "phd", "years": 10}]}).status_code, 422)

    def test_in_live_mode_the_routes_answer_live_and_no_answer_holds_the_key(self):
        self.keep(recording_of("ask", "en", NINE))
        self.live()
        answers_ = [self.c.get("/ai/status"), self.c.post("/ai/stress?lang=en", json={}), self.c.post("/ai/ask?lang=en", json={"sentence": "A sentence she types."}),
                    self.c.post("/ai/ask?lang=fr", json={"sentence": NINE}), self.c.post("/ai/stress", json={"path": [{"block": "job", "years": 3}]})]
        self.assertEqual([answer.status_code for answer in answers_], [200, 200, 200, 200, 422])
        self.assertEqual([answer.json().get("source") for answer in answers_[1:4]], ["live", "live", "live"])
        self.assertEqual(answers_[0].json()["mode"], "live")
        for answer in answers_:
            self.assertNotIn(SHAPED, answer.text)
            self.assertNotIn(SHAPED, json.dumps(dict(answer.headers)))

    def test_the_placeholder_of_the_hackathon_is_gone(self):
        self.assertIn(self.c.post("/ask").status_code, (404, 405))


# ------------------------------------------------------------------------------ what is recorded in the repository
class WhatIsRecordedInTheRepository(unittest.TestCase):
    """The real answers kept in ai/recorded/. Each one is played again here, on the engine of today, by the loop that
    made it. The day the engine, a prompt or a form changes, the recordings it touches fail here until they are
    recorded again. With no recording yet, there is nothing to play."""

    FOLDER = ROOT / "ai" / "recorded"

    def test_every_recording_is_whole_and_keeps_no_thinking_and_no_key(self):
        for recording in recordings.every(self.FOLDER):
            with self.subTest(file=recording["file"]):
                self.assertEqual(recording["file"], recordings.file_name(recording))
                self.assertEqual((recording["format"], recording["scenario"], recording["model"], recording["path"], recording["assumptions"]),
                                 (1, "alexia", "claude-sonnet-5-5", STORY, {}))
                self.assertIn(recording["language"], ("en", "fr"))
                self.assertRegex(recording["recorded_at"], r"^20\d\d-\d\d-\d\d$")
                self.assertTrue(recording["turns"])
                kinds = {block["type"] for turn in recording["turns"] for block in turn["reply"]["content"]}
                self.assertTrue(kinds <= {"text", "tool_use"}, kinds)
                written = (self.FOLDER / recording["file"]).read_text(encoding="utf-8")
                for words in ("signature", "redacted_thinking", "authorization", "x-api-key"):
                    self.assertNotIn(words, written)
                self.assertEqual(recordings.scrub(written), written)

    def test_every_recording_plays_again_on_the_engine_of_today(self):
        for recording in recordings.every(self.FOLDER):
            with self.subTest(file=recording["file"]):
                try:
                    result = service.replay(Tree(ALEXIA), recording)
                except Stale as stale:
                    self.fail(f"{recording['file']} is not what Doors would ask today ({stale}). Record it again: python scripts/record_ai.py record --force")
                self.assertEqual((result["language"], result["model"]), (recording["language"], "claude-sonnet-5-5"))
                if recording["kind"] == "ask":
                    self.assertEqual(result["sentence"], recording["sentence"])
                    continue
                # The ranking is the code's own, made again from the worlds the recorded search tested; each text shown
                # passed the checker again, and a text it refuses is not in the result.
                self.assertEqual([world["world"] for world in result["ranking"]], [summary["world"] for summary in stressing.rank(result["tested"])])
                self.assertLessEqual(result["budget"]["worlds_tested"], 40)
                for world in result["ranking"]:
                    explanation = world["explanation"]
                    self.assertEqual(explanation["text"] is not None, explanation["accepted"])
                    self.assertEqual(explanation["label"] == result["rejected_label"], not explanation["accepted"])


if __name__ == "__main__":
    unittest.main()
