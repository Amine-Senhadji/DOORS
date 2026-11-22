"""The commands that call the model (scripts/record_ai.py, scripts/benchmark_agent.py live), tested without it.

A dry run sends nothing and builds no client. The live commands are run here with a stand-in in the place of the
model: what they write, what they skip, where they stop and what they log is what they do with the real one.
"""
from __future__ import annotations

import offline  # noqa: F401  the recorded mode, and no client of the SDK: before anything else

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from importlib import metadata
from pathlib import Path
from unittest import mock

from ai import benchmark, cost, recordings, rehearsal, service
from ai import model as M
from ai.model import Reply, answers
from engine.blocks import normalize
from engine.simulate import load_scenario
from engine.tree import Tree

ROOT = Path(__file__).resolve().parents[1]
TREE = Tree(load_scenario(ROOT / "engine/scenarios/alexia.json"))
STORY = normalize(benchmark.ROUTES["story_a"], TREE.h)
SHAPED = "sk-" + "ant-" + "api03-" + "k" * 60          # the shape of a key, put together here: it is not one
FORM = {**rehearsal.EMPTY, "crises": [{"type": "chomage_6_mois", "age": 27, "size": 9, "unit": "months", "quote": ""}]}
SPENT = {"input_tokens": 1000, "output_tokens": 100, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
TURN = 0.003                                            # what one such answer costs: 1'000 tokens sent at 2 USD a million, 100 answered at 10


def script(name: str):
    """A script of the repository, loaded as a module."""
    spec = importlib.util.spec_from_file_location(f"doors_{name}", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RECORD, BENCH = script("record_ai"), script("benchmark_agent")


class Understudy(rehearsal.StandIn):
    """The stand-in, with a form that says something for “Ask”, and with tokens counted as the API counts them."""
    name = M.MODEL

    def reply(self, **request) -> Reply:
        fields = (request["output"] or {}).get("properties") or {}
        played = answers(FORM) if "route" in fields else super().reply(**request)
        return Reply(played.content, played.stop_reason, dict(SPENT), M.MODEL)


def refusing(status: int, kind: str = "AuthenticationError"):
    """A model the API refuses, the way the SDK reports it: an error of its own module, with a status and a message."""
    error = type(kind, (Exception,), {"status_code": status, "message": f"the request with {SHAPED} was refused", "__module__": "anthropic"})

    class Refused:
        name = M.MODEL

        def reply(self, **request):
            raise error("refused")
    return Refused()


class Commands(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        for holder, name, file in ((recordings, "DIR", "recorded"), (recordings, "LOG", "ai_live.log"), (benchmark, "AGENT", "agent.json"),
                                   (RECORD, "DRY_RUN", "dry.record.json"), (BENCH, "DRY_RUN", "dry.benchmark.json")):
            self.enterContext(mock.patch.object(holder, name, self.folder / file))
        self.enterContext(mock.patch.dict(os.environ, {"DOORS_AI": "recorded"}))
        os.environ.pop("ANTHROPIC_API_KEY", None)
        service._played.clear()
        recordings._read.clear()

    def key(self):
        self.enterContext(mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": SHAPED}))

    def run_(self, module, *arguments: str) -> tuple[int, str]:
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            code = module.main(list(arguments))
        self.assertNotIn(SHAPED, said.getvalue())
        return code, said.getvalue()

    def files(self) -> list[str]:
        return sorted(file.name for file in (self.folder / "recorded").glob("*")) if (self.folder / "recorded").is_dir() else []

    def log(self) -> list[dict]:
        file = self.folder / "ai_live.log"
        self.assertNotIn(SHAPED, file.read_text(encoding="utf-8") if file.is_file() else "")
        return [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines()] if file.is_file() else []


class TheDryRun(Commands):
    def test_the_dry_run_of_the_recordings_shows_what_would_be_sent_and_sends_nothing(self):
        self.key()                                      # even with a key there: nothing is sent, and the key is not looked at
        code, said = self.run_(RECORD, "record", "--dry-run")
        self.assertEqual(code, 0)
        self.assertTrue(said.startswith("DRY RUN. Nothing is sent, no client is built, and the key is not looked at.\n"))
        self.assertTrue(said.rstrip().endswith("Nothing was sent."))
        self.assertIn('model claude-sonnet-5-5 · max_tokens 16\'000 · adaptive thinking · system prompt marked for the cache · fallback "default" '
                      "(beta server-side-fallback-2026-07-01)", said)
        for language, sentences in RECORD.SENTENCES.items():
            self.assertEqual(len(sentences), 6)
            for index, sentence in enumerate(sentences, start=1):
                self.assertIn(f"== ask · {language} · {index} · “{sentence}”", said)
                self.assertIn("\n".join(["     | Her sentence", f"     | {sentence}"]), said)                # the message, in full
        self.assertIn("== stress · en · the demo route", said)
        self.assertIn("== stress · fr · the demo route", said)
        self.assertIn("5 to 6 requests of the search, with the tool test_worlds · effort medium", said)
        self.assertIn("1 to 3 requests for the explanations, one more each time the checker refuses a text · effort medium", said)
        # Each system prompt is printed once, in full: the two of “Ask” (their names are in the language of the screen),
        # the one of the search, and the two of the explanations.
        self.assertEqual((said.count("--- system prompt ---"), said.count("| You read one sentence written by Alexia"), said.count("| You are the stress-test agent"),
                          said.count("| You write short explanations for Doors"), said.count("--- tool ---")), (5, 2, 1, 2, 1))
        # The estimate is the one of ai/cost.py for the requests of a rehearsal, and the total is their sum.
        each = [cost.estimate(rehearsal.ask(TREE, sentence, STORY, {}, language)) for language in RECORD.SENTENCES for sentence in RECORD.SENTENCES[language]]
        each += [cost.estimate(rehearsal.stress(TREE, STORY, {}, language)) for language in RECORD.SENTENCES]
        total = cost.add(each)
        self.assertIn(f"TOTAL for 14 exchanges: {total['low']['requests']} to {total['high']['requests']} requests, "
                      f"{cost.usd(total['low']['usd'])} to {cost.usd(total['high']['usd'])}.", said)
        self.assertIn(f"Ceiling, if every answer were as long as the API allows (16'000 tokens): {cost.usd(total['ceiling_usd'])}.", said)
        self.assertEqual((total["low"]["requests"], total["high"]["requests"]), (24, 30))
        self.assertTrue(0.1 < total["low"]["usd"] < total["high"]["usd"] < 2 < total["ceiling_usd"] < 10)
        # The file holds every request, keyword for keyword as the SDK would be given it.
        written = json.loads((self.folder / "dry.record.json").read_text(encoding="utf-8"))
        self.assertEqual((len(written["exchanges"]), [len(exchange["requests"]) for exchange in written["exchanges"]]), (14, [1] * 12 + [6, 6]))
        first = written["exchanges"][0]["requests"][0]
        self.assertEqual((sorted(first), first["model"], first["max_tokens"], first["thinking"], first["fallbacks"], first["betas"], first["output_config"]["effort"]),
                         (["betas", "fallbacks", "max_tokens", "messages", "model", "output_config", "system", "thinking"], "claude-sonnet-5-5", 16000,
                          {"type": "adaptive"}, "default", ["server-side-fallback-2026-07-01"], "low"))
        self.assertEqual(written["exchanges"][-1]["requests"][0]["tools"][0]["name"], "test_worlds")
        self.assertNotIn(SHAPED, json.dumps(written))
        # Nothing else was written: no recording, no log.
        self.assertEqual((self.files(), self.log()), ([], []))

    def test_the_dry_run_can_be_brief_or_about_one_call_and_leaves_out_what_is_recorded(self):
        code, said = self.run_(RECORD, "check", "--dry-run", "--brief", "--no-fallback")
        self.assertEqual((code, said.count("== ask"), said.count("== stress"), "--- system prompt ---" in said), (0, 1, 0, False))
        self.assertIn("· no fallback", said)
        self.assertIn("TOTAL for 1 exchange: 1 request,", said)
        self.assertNotIn("fallbacks", json.loads((self.folder / "dry.record.json").read_text(encoding="utf-8"))["exchanges"][0]["requests"][0])
        self.key()
        with mock.patch.object(RECORD, "Live", lambda fallback=True: Understudy(rehearsal.sample(TREE))):
            self.run_(RECORD, "check")
        code, said = self.run_(RECORD, "record", "--dry-run", "--brief", "--only", "ask", "--lang", "en")
        self.assertIn("== ask · en · 1 · “What if I lost my job for 9 months at 27?”\n   already recorded: kept (--force would record it again)", said)
        self.assertIn("TOTAL for 5 exchanges: 5 requests,", said)
        self.assertIn("1 already recorded: left as it is.", said)
        # Once an answer is recorded, the estimate uses what it measured instead of what is assumed.
        self.assertIn("characters per token (measured on the recorded answers)", said)

    def test_the_dry_run_of_the_benchmark(self):
        self.key()
        code, said = self.run_(BENCH, "live", "--dry-run")
        self.assertEqual(code, 0)
        self.assertTrue(said.startswith("DRY RUN. Nothing is sent, no client is built, and the key is not looked at.\n"))
        for route in benchmark.ROUTES:
            for language in ("en", "fr"):
                self.assertIn(f"== {route} · explanations in {language} · 5 runs to make", said)
        each = {(route, language): cost.estimate(rehearsal.stress(TREE, benchmark.ROUTES[route], None, language)) for route in benchmark.ROUTES for language in ("en", "fr")}
        total = cost.add([estimate for estimate in each.values() for _ in range(5)])
        self.assertIn(f"TOTAL for 30 runs: {total['low']['requests']} to {total['high']['requests']} requests, {cost.usd(total['low']['usd'])} to "
                      f"{cost.usd(total['high']['usd'])}.", said)
        self.assertEqual((total["low"]["requests"], total["high"]["requests"]), (180, 270))
        self.assertTrue(1 < total["low"]["usd"] < 3 < total["high"]["usd"] < 15)
        self.assertEqual((said.count("--- system prompt of the search ---"), said.count("--- first message ---")), (1, 1))
        written = json.loads((self.folder / "dry.benchmark.json").read_text(encoding="utf-8"))
        self.assertEqual((written["runs_to_make"], len(written["examples"]), {len(example["requests"]) for example in written["examples"]}), (30, 6, {6}))
        self.assertIsNone(written["from_the_runs_already_made"])                         # before any run is made, there is nothing measured
        self.assertNotIn("Measured on", said)
        self.assertFalse((self.folder / "agent.json").exists())
        code, said = self.run_(BENCH, "live", "--dry-run", "--brief", "--route", "berlin", "--runs", "3")
        self.assertIn("TOTAL for 3 runs:", said)
        self.assertEqual((said.count("== berlin"), said.count("== story_a"), "--- system prompt" in said), (2, 0, False))


class TheLiveCommands(Commands):
    def stand_in(self, model=None):
        self.key()
        self.enterContext(mock.patch.object(RECORD, "Live", lambda fallback=True: model or Understudy(rehearsal.sample(TREE))))

    def test_without_a_key_the_live_commands_say_so_and_do_nothing(self):
        for module, arguments in ((RECORD, ["check"]), (RECORD, ["record"]), (BENCH, ["live"])):
            code, said = self.run_(module, *arguments)
            self.assertEqual((code, said), (2, "ANTHROPIC_API_KEY is not set in this terminal. Export it, then run this command again.\n"
                                               "The key is read by the SDK when it sends a request. This script never prints it and never writes it.\n"))
        self.assertEqual((self.files(), self.log(), (self.folder / "agent.json").exists()), ([], [], False))

    def test_check_makes_one_call_and_its_answer_is_the_first_recording(self):
        self.stand_in()
        code, said = self.run_(RECORD, "check")
        self.assertEqual((code, self.files()), (0, ["ask.en.what-if-i-lost-my-job-for-9-months-at-27.json"]))
        for words in ("== ask · en · 1 · “What if I lost my job for 9 months at 27?”", "1 request in ", "sent 1'000 tokens (0 read from the cache, 0 written to it)",
                      "answered 100 tokens (0 of thinking) · 0.0030 USD", "understood: True",
                      "crisis chomage_6_mois@27~150 · You ask for 9 months: severity 150% of “Six months of unemployment”, usually 6 months. The engine builds 9 months.",
                      "written: ai/recorded/ask.en.what-if-i-lost-my-job-for-9-months-at-27.json · played again without the model: the same answer",
                      "Done. 1 recorded by this command, 0.0030 USD spent."):
            self.assertIn(words, said)
        recording = recordings.every()[0]
        self.assertEqual({key: recording[key] for key in ("format", "kind", "language", "scenario", "label", "path", "assumptions", "sentence", "model", "served_by",
                                                         "recorded_at", "sdk", "usage", "cost_usd")},
                         {"format": 1, "kind": "ask", "language": "en", "scenario": "alexia", "label": "story_a", "path": STORY, "assumptions": {},
                          "sentence": "What if I lost my job for 9 months at 27?", "model": "claude-sonnet-5-5", "served_by": ["claude-sonnet-5-5"],
                          "recorded_at": date.today().isoformat(), "sdk": metadata.version("anthropic"), "usage": SPENT, "cost_usd": TURN})
        self.assertEqual(service.replay(TREE, recording)["world"]["id"], "chomage_6_mois@27~150")
        logged = self.log()
        self.assertEqual((len(logged), {key: logged[0][key] for key in ("command", "ok", "file", "same_when_replayed", "requests", "usage", "cost_usd", "stop_reasons")}),
                         (1, {"command": "check", "ok": True, "file": "ask.en.what-if-i-lost-my-job-for-9-months-at-27.json", "same_when_replayed": True,
                              "requests": 1, "usage": SPENT, "cost_usd": TURN, "stop_reasons": ["end_turn"]}))

    def test_record_makes_what_is_missing_and_keeps_what_is_there(self):
        self.stand_in()
        self.run_(RECORD, "check")
        code, said = self.run_(RECORD, "record")
        self.assertEqual((code, len(self.files())), (0, 14))
        self.assertEqual((said.count("already recorded: kept"), said.count("played again without the model: the same answer"), said.count("NOT THE SAME")), (1, 13, 0))
        # Eleven sentences of one request, and two stress tests of six: priced from the tokens each answer reported.
        self.assertIn(f"Done. 13 recorded by this command, {cost.usd(11 * TURN + 2 * 6 * TURN)} spent.", said)
        self.assertIn("search: 5 calls, 40 worlds tested, stopped by: budget", said)
        self.assertIn("true answer of the full scan: 3 goals lost at most. Found by the search: False", said)
        self.assertEqual(sorted((each["kind"], each["language"]) for each in recordings.every()), sorted([("ask", "en")] * 6 + [("ask", "fr")] * 6 + [("stress", "en"), ("stress", "fr")]))
        for recording in recordings.every():                    # each one plays again on the engine, with no model
            self.assertTrue(service.replay(TREE, recording))
        self.assertEqual(sorted(len(each["turns"]) for each in recordings.every()), [1] * 12 + [6, 6])
        # Run again: nothing is asked twice.
        code, said = self.run_(RECORD, "record")
        self.assertEqual((code, said.count("already recorded: kept"), "Done. 0 recorded by this command, 0.0000 USD spent." in said), (0, 14, True))
        self.assertEqual(len(self.log()), 14)
        # One sentence recorded again on purpose, and a limit on what a command may spend.
        code, said = self.run_(RECORD, "record", "--only", "ask", "--lang", "fr", "--sentence", "2", "--force")
        self.assertEqual((said.count("== ask"), "Done. 1 recorded by this command" in said), (1, True))
        code, said = self.run_(RECORD, "record", "--only", "ask", "--lang", "en", "--force", "--max-usd", "0.005")
        self.assertEqual((said.count("played again without the model"), said.count("not recorded: this command has spent 0.0060 USD, and the limit is 0.0050 USD")), (2, 4))

    def test_a_recording_that_does_not_play_again_as_it_was_answered_is_said(self):
        self.stand_in()
        with mock.patch.object(service, "replay", lambda tree, recording: {"another": "answer"}):
            code, said = self.run_(RECORD, "check")
        self.assertIn("played again without the model: NOT THE SAME ANSWER", said)
        self.assertEqual((code, self.log()[0]["same_when_replayed"]), (0, False))

        def stale(tree, recording):
            raise M.Stale(1, "the system is not the one that was recorded")
        with mock.patch.object(service, "replay", stale):
            code, said = self.run_(RECORD, "check", "--force")
        self.assertIn("the replay failed: Stale: turn 1: the system is not the one that was recorded", said)
        self.assertIn("played again without the model: NOT THE SAME ANSWER", said)

    def test_a_failure_stops_the_command_and_is_logged_without_any_key(self):
        self.stand_in(refusing(401))
        code, said = self.run_(RECORD, "record")
        self.assertEqual((code, self.files(), said.count("== ask")), (1, [], 1))                 # it stops at the first one
        self.assertIn("   FAILED: AuthenticationError (status 401): the request with [key removed] was refused", said)
        self.assertIn("The key was refused, or it is not the key of an account that may call this model.", said)
        self.assertIn("Stopped. 0 recorded by this command, 0.0000 USD spent.", said)
        logged = self.log()
        self.assertEqual((len(logged), logged[0]["ok"], logged[0]["error"]),
                         (1, False, {"type": "AuthenticationError", "status": 401, "message": "the request with [key removed] was refused"}))
        with mock.patch.object(RECORD, "Live", lambda fallback=True: refusing(400, "BadRequestError")):
            code, said = self.run_(RECORD, "check")
        self.assertIn("If the message is about “fallbacks” or the beta header, run the command again with --no-fallback.", said)
        with mock.patch.object(RECORD, "Live", lambda fallback=True: refusing(400, "BadRequestError")):
            self.assertNotIn("--no-fallback", self.run_(RECORD, "check", "--no-fallback")[1])

    def test_the_fallback_can_be_switched_off(self):
        asked = []
        self.key()
        with mock.patch.object(RECORD, "Live", lambda fallback=True: asked.append(fallback) or Understudy(rehearsal.sample(TREE))):
            self.run_(RECORD, "check")
            self.run_(RECORD, "check", "--force", "--no-fallback")
        self.assertEqual(asked, [True, False])


class TheBenchmarkWithAModel(Commands):
    """`live` with a stand-in: the runs are made in threads here, in processes for real."""

    def setUp(self):
        super().setUp()
        self.key()
        self.made, self.failing, self.on_disk, lock = [], {}, [], threading.Lock()

        def run(job):
            key, number, fallback = job
            with lock:
                self.made.append((key, number))
                error = self.failing.pop((key, number), None)
                file = self.folder / "agent.json"           # what is already written when this run starts
                self.on_disk.append(sum(len(route["runs"]) for route in json.loads(file.read_text(encoding="utf-8"))["routes"].values()) if file.is_file() else 0)
            if error is not None:
                return {"route": key, "run": number, "language": benchmark.language_of(number), "error": error}
            return benchmark.run_once(key, number, Understudy(rehearsal.sample(TREE)))
        self.enterContext(mock.patch.object(benchmark, "live_run", run))
        self.enterContext(mock.patch.object(BENCH, "ProcessPoolExecutor", ThreadPoolExecutor))

    def saved(self) -> dict:
        return json.loads((self.folder / "agent.json").read_text(encoding="utf-8"))

    def test_the_runs_are_measured_written_after_each_one_and_never_made_twice(self):
        code, said = self.run_(BENCH, "live", "--route", "story_a", "--runs", "2", "--parallel", "2")
        self.assertEqual((code, sorted(self.made)), (0, [("story_a", 0), ("story_a", 1)]))
        self.assertIn("2 runs to make, 0 already made and kept. 2 at a time.", said)
        self.assertIn("story_a #0 (en): not found, 2 goals lost at best (the most is 3) · 40 worlds in 5 calls · rewrites per explanation: 0/0/0 · 6 requests, ", said)
        self.assertIn("story_a #1 (fr): not found,", said)
        saved = self.saved()
        self.assertEqual((saved["model"], saved["sdk"], saved["budget"], list(saved["routes"])), ("claude-sonnet-5-5", metadata.version("anthropic"), 40, ["story_a"]))
        runs, summary = saved["routes"]["story_a"]["runs"], saved["routes"]["story_a"]["summary"]
        self.assertEqual([(run["run"], run["language"], run["found"], run["goals_lost"], run["worlds_tested"], run["calls_used"], run["requests"], run["cost_usd"])
                          for run in runs], [(0, "en", False, 2, 40, 5, 6, round(6 * TURN, 6)), (1, "fr", False, 2, 40, 5, 6, round(6 * TURN, 6))])
        self.assertEqual([[(explanation["accepted"], explanation["attempts"], explanation["rewrites"]) for explanation in run["explanations"]] for run in runs],
                         [[(True, 1, 0)] * 3] * 2)
        self.assertEqual({key: summary[key] for key in ("runs", "failed", "found", "share_found", "budget", "space", "max_goals_lost", "best_goals_lost", "requests", "cost_usd")},
                         {"runs": 2, "failed": 0, "found": 0, "share_found": 0.0, "budget": 40, "space": 49140, "max_goals_lost": 3, "best_goals_lost": {"2": 2},
                          "requests": 12, "cost_usd": round(12 * TURN, 6)})
        self.assertEqual(summary["explanations"], {"count": 6, "accepted": 6, "rejected": 0, "accepted_after_rewrites": {"0": 6}, "mean_rewrites_when_accepted": 0.0,
                                                   "by_language": {language: {"count": 3, "accepted": 3, "rejected": 0, "accepted_after_rewrites": {"0": 3},
                                                                              "mean_rewrites_when_accepted": 0.0} for language in ("en", "fr")}})
        self.assertEqual((saved["total"]["runs"], saved["total"]["cost_usd"], saved["total"]["explanations"]["count"]), (2, round(12 * TURN, 6), 6))
        # A dry run now also says what the runs left would cost at the price of the runs made: the most direct estimate.
        code, said = self.run_(BENCH, "live", "--dry-run", "--brief", "--route", "story_a", "--runs", "5", "--parallel", "2")
        self.assertEqual((code, len(self.made)), (0, 2))                               # nothing is run by a dry run
        self.assertIn("TOTAL for 3 runs:", said)
        self.assertIn("Measured on the 2 runs already made: 0.0180 USD a run on average (from 0.0180 USD to 0.0180 USD), ", said)
        self.assertIn("At that price, the 3 runs left: about 0.0540 USD (from 0.0540 USD to 0.0540 USD), and about ", said)
        self.assertIn(" minutes with 2 at a time.", said)
        projection = json.loads((self.folder / "dry.benchmark.json").read_text(encoding="utf-8"))["from_the_runs_already_made"]
        self.assertEqual((projection["runs_made"], projection["runs_left"], round(projection["usd"], 6)), (2, 3, 0.054))
        self.assertEqual(BENCH.projected([{"cost_usd": 0.2, "seconds": 100}, {"cost_usd": 0.4, "seconds": 200}, {"error": {}}, {"cost_usd": None, "seconds": 9}], 24, 3),
                         {"runs_made": 2, "usd_a_run": 0.30000000000000004, "least_usd_a_run": 0.2, "most_usd_a_run": 0.4, "seconds_a_run": 150.0, "runs_left": 24,
                          "usd": 0.30000000000000004 * 24, "least_usd": 0.2 * 24, "most_usd": 0.4 * 24, "minutes": 150.0 * 24 / 3 / 60})
        self.assertIsNone(BENCH.projected([{"error": {}}], 30, 3))
        # A third run asked: only that one is made.
        code, said = self.run_(BENCH, "live", "--route", "story_a", "--runs", "3")
        self.assertEqual((code, self.made[2:], len(self.saved()["routes"]["story_a"]["runs"])), (0, [("story_a", 2)], 3))
        self.assertIn("1 run to make, 2 already made and kept.", said)
        # Nothing left to make: nothing is sent, and the report is printed.
        code, said = self.run_(BENCH, "live", "--route", "story_a", "--runs", "3")
        self.assertEqual((code, len(self.made)), (0, 3))
        self.assertIn("the agent (claude-sonnet-5-5), 40 worlds: finds one of the hardest in 0 of 3 runs (0%); best found per run, goals lost -> runs: {'2': 3}", said)
        self.assertIn("explanations: 9 of 9 accepted by the checker; rewrites -> explanations: {'0': 9}; rejected after three attempts: 0", said)

    def test_a_run_that_fails_is_kept_as_what_happened_and_made_again_the_next_time(self):
        self.failing["story_a", 1] = {"type": "RateLimitError", "status": 429, "message": "slow down"}
        code, said = self.run_(BENCH, "live", "--route", "story_a", "--runs", "2", "--parallel", "1")
        self.assertEqual(code, 1)
        self.assertIn("story_a #1 (fr): FAILED RateLimitError (status 429): slow down", said)
        self.assertIn("1 run made in all, 1 failed in this command", said)
        self.assertIn("Run the command again to make the runs that failed: the ones that are made are kept.", said)
        summary = self.saved()["routes"]["story_a"]["summary"]
        self.assertEqual((summary["runs"], summary["failed"], [("error" in run) for run in self.saved()["routes"]["story_a"]["runs"]]), (1, 1, [False, True]))
        self.assertEqual([entry["what"] for entry in self.log()], ["story_a #1", "2 runs asked"])
        code, said = self.run_(BENCH, "live", "--route", "story_a", "--runs", "2")
        self.assertEqual((code, self.made, [("error" in run) for run in self.saved()["routes"]["story_a"]["runs"]]),
                         (0, [("story_a", 0), ("story_a", 1), ("story_a", 1)], [False, False]))

    def test_a_request_the_api_refuses_stops_the_runs_that_have_not_started(self):
        self.failing["story_a", 0] = {"type": "AuthenticationError", "status": 401, "message": "invalid key"}
        code, said = self.run_(BENCH, "live", "--runs", "2", "--parallel", "1")
        self.assertEqual((code, self.made), (1, [("story_a", 0)]))
        self.assertIn("Stopped: the API refused the request itself.", said)
        self.assertIn("run the command again with --no-fallback", said)

    def test_a_limit_on_what_a_command_may_spend(self):
        code, said = self.run_(BENCH, "live", "--runs", "2", "--parallel", "1", "--max-usd", "0.02")
        self.assertEqual((code, self.made), (0, [("story_a", 0), ("work_only", 0)]))            # 0.018 USD each: the second one passes the limit
        self.assertEqual(self.on_disk, [0, 1])                                                  # each run is on disk before the next one starts
        self.assertIn("No new run is started once this command has spent 0.0200 USD (--max-usd): the runs under way are let to finish.", said)
        self.assertIn("Stopped: this command has spent 0.0360 USD, and the limit is 0.0200 USD.", said)
        # --fresh starts over, without the runs already made.
        code, said = self.run_(BENCH, "live", "--route", "berlin", "--runs", "1", "--fresh")
        self.assertEqual((self.made[2:], list(self.saved()["routes"])), ([("berlin", 0)], ["berlin"]))


class TheCost(unittest.TestCase):
    def test_the_cost_of_a_call_is_the_price_of_the_tokens_the_api_reported(self):
        self.assertEqual(cost.PRICES["claude-sonnet-5-5"], {"input": 2.0, "output": 10.0, "cache_write": 2.5, "cache_read": 0.1})
        usage = {"input_tokens": 1_000_000, "output_tokens": 100_000, "cache_creation_input_tokens": 200_000, "cache_read_input_tokens": 3_000_000, "thinking_tokens": 50_000}
        self.assertAlmostEqual(cost.cost(usage), 2.0 + 1.0 + 0.5 + 0.3)                           # the thinking is part of the output, not added to it
        self.assertAlmostEqual(cost.cost(usage, "claude-sonnet-5"), 2.0 + 1.0 + 0.5 + 0.6)
        self.assertEqual((cost.cost({}), cost.cost(usage, "another-model"), cost.cost(SPENT)), (0.0, None, TURN))
        self.assertEqual(cost.sent(usage), 4_200_000)
        self.assertEqual((cost.number(16000), cost.usd(0.0123456), cost.usd(12.3456), cost.usd(None), cost.span(5, 5), cost.span(5, 6), cost.span(0.5, 2, cost.usd)),
                         ("16'000", "0.0123 USD", "12.35 USD", "not priced", "5", "5 to 6", "0.5000 USD to 2.00 USD"))
        self.assertEqual((cost.count(1, "request"), cost.count(6, "request"), cost.count(1200, "run")), ("1 request", "6 requests", "1'200 runs"))

    def test_an_estimate_is_made_from_the_size_of_the_requests(self):
        request = lambda size, **more: {"system": "s" * size, "messages": [{"role": "user", "content": ""}], "tools": [], "output": None, "effort": "low", **more}
        ask = request(2800 - 2, output={})                                                     # 2'800 characters in all: "{}" counts for two
        self.assertEqual((cost.kind_of(ask), cost.characters(ask)), ("ask", 2800))
        self.assertEqual(cost.estimate([ask]), {"low": {"requests": 1, "input_tokens": 1000, "output_tokens": 150, "usd": (1000 * 2 + 150 * 10) / 1e6},
                                                "high": {"requests": 1, "input_tokens": 1000, "output_tokens": 1500, "usd": (1000 * 2 + 1500 * 10) / 1e6},
                                                "ceiling_usd": (1000 * 2 + 16000 * 10) / 1e6, "characters_per_token": 2.8, "measured": []})
        tool = [{"name": "t"}]
        size = len(json.dumps(tool))
        search = [request(2800 * turn - size, tools=tool) for turn in (1, 2, 3)]
        explain = request(5600 - len(json.dumps({"properties": {"explanations": {}}})), output={"properties": {"explanations": {}}})
        self.assertEqual([cost.kind_of(each) for each in search + [explain]], ["search"] * 3 + ["explain"])
        estimate = cost.estimate(search + [explain])
        # Low: the four requests as they are. High: one more turn of search, as much larger than the last as the last was
        # than the one before, and two rewrites of the explanations.
        self.assertEqual(estimate["low"], {"requests": 4, "input_tokens": 1000 + 2000 + 3000 + 2000, "output_tokens": 3 * 300 + 400,
                                           "usd": (8000 * 2 + 1300 * 10) / 1e6})
        self.assertEqual(estimate["high"], {"requests": 7, "input_tokens": 8000 + 4000 + 2600 + 3200, "output_tokens": 4 * 3000 + 3 * 3000,
                                            "usd": (17800 * 2 + 21000 * 10) / 1e6})
        self.assertEqual(estimate["ceiling_usd"], (17800 * 2 + 7 * 16000 * 10) / 1e6)
        both = cost.add([estimate, estimate])
        self.assertEqual((both["low"]["requests"], both["high"]["input_tokens"], both["ceiling_usd"]), (8, 35600, 2 * estimate["ceiling_usd"]))

    def test_once_answers_are_recorded_the_estimate_uses_what_they_measured(self):
        self.assertEqual(cost.measured([]), {"answers": {}})
        request = {"system": "s" * 3000, "messages": [{"role": "user", "content": ""}], "tools": [], "output": {}, "effort": "low"}
        turn = lambda sent, answered: {"request": request, "reply": {"usage": {"input_tokens": sent - 400, "cache_read_input_tokens": 400, "output_tokens": answered}}}
        measures = cost.measured([{"turns": [turn(1000, 200), turn(1001, 400)]}, {"turns": [{"request": request, "reply": {"usage": {}}}]}])
        self.assertEqual(measures, {"answers": {"ask": {"count": 2, "least": 200, "most": 400, "mean": 300}}, "characters_per_token": 3.0})
        estimate = cost.estimate([request], measures)
        self.assertEqual((estimate["low"]["input_tokens"], estimate["low"]["output_tokens"], estimate["high"]["output_tokens"], estimate["characters_per_token"],
                          estimate["measured"]), (1001, 200, 600, 3.0, ["ask"]))


if __name__ == "__main__":
    unittest.main()
