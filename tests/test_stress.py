"""“Find what breaks my plan” (ai/stress.py): the model searches and writes, the engine decides.

No test here calls a model. A scripted model plays the turns; the worlds, the figures and the sentences of the
signposts are the engine's, computed again here without the stress test.
"""
from __future__ import annotations

import offline  # noqa: F401  the recorded mode, and no client of the SDK: before anything else

import ast
import json
import re
import unittest
from pathlib import Path

from ai import stress
from ai import vocabulary as V
from ai.checker import Fact, check
from ai.model import Reply, Scripted, answers, calls, says
from engine import i18n
from engine import worlds as W
from engine.blocks import blocks_to_ops
from engine.explore import doors_of
from engine.simulate import load_scenario, run_ops, theta_for
from engine.tree import Tree

ROOT = Path(__file__).resolve().parents[1]
ALEXIA = load_scenario(ROOT / "engine/scenarios/alexia.json")
TH = theta_for(ALEXIA)
H, AGE0 = ALEXIA.horizon_months, ALEXIA.profile.age
STORY = [{"block": "job", "years": 5}, {"block": "master", "years": 2}, {"block": "job", "years": 3}]
TREE = Tree(ALEXIA)
TWICE, LONG, BOTH = "chomage_long@23+chomage_long@24", "chomage_long@27", "krach@24+chomage_long@27"
SINGLES = V.singles(TH, H, AGE0)


def live(world: str):
    """The engine, without the stress test: the demo route simulated from the start in this world."""
    return run_ops(ALEXIA.profile, blocks_to_ops(STORY, TH, H), H, TH, W.build(TH, world, H, AGE0))


def lost(world: str) -> list[str]:
    calm, here = doors_of(live("reference"), TH, AGE0), doors_of(live(world), TH, AGE0)
    return [key for key in here if calm[key] and not here[key]]


def chf(amount: float) -> str:
    with i18n.use("en"):
        return Fact.chf(amount, "").written()


def asked(request: dict) -> list[str]:
    """The worlds an explanation is asked for: they are listed in the schema of the answer."""
    return request["output"]["properties"]["explanations"]["items"]["properties"]["world"]["enum"]


def writes(text_of):
    """A turn of the script that explains every world asked, with the text `text_of(world)` or `text_of[world]`."""
    return lambda request: answers({"explanations": [{"world": world, "text": text_of(world) if callable(text_of) else text_of[world]}
                                                     for world in asked(request)]})


def told(model: Scripted, turn: int) -> dict:
    """What the tool answered after the turn `turn` of the search: it is the last message of the next request."""
    return json.loads(model.requests[turn + 1]["messages"][-1]["content"][0]["content"])


PLAIN = "This crisis comes when you can least afford it."        # an explanation with no figure: always accepted


class TheSearch(unittest.TestCase):
    """The conversation where the model proposes worlds. Code holds the budget and the engine answers."""

    def test_the_budget_is_held_by_code_whatever_the_model_asks(self):
        tens = [SINGLES[10 * turn:10 * turn + 10] for turn in range(5)]                    # ten worlds a call: two too many each time
        model = Scripted([calls(stress.TOOL, {"worlds": worlds}, f"call_{turn}") for turn, worlds in enumerate(tens)] + [writes(lambda world: PLAIN)])
        result = stress.run(TREE, STORY, model, lang="en")
        self.assertEqual((stress.CALLS, stress.PER_CALL), (5, 8))
        self.assertEqual(result["budget"], {"calls": 5, "worlds_per_call": 8, "worlds": 40, "calls_used": 5, "worlds_tested": 40})
        self.assertEqual((result["stopped"], result["space"]["worlds"]), ("budget", 49140))
        for turn, record in enumerate(result["calls"]):
            self.assertEqual((record["call"], len(record["tested"]), record["not_tested"]), (turn + 1, 8, tens[turn][8:]))
        self.assertEqual([world["world"] for world in result["tested"]], [W.canonical(world, TH, H, AGE0) for worlds in tens for world in worlds[:8]])
        # Five turns of search, and the sixth request is the explanation: the model is not asked for a sixth call.
        self.assertEqual([bool(request["tools"]) for request in model.requests], [True] * 5 + [False])
        self.assertEqual((told(model, 0)["calls_left"], told(model, 3)["calls_left"], told(model, 3)["worlds_tested_so_far"]), (4, 1, 32))
        self.assertEqual(told(model, 0)["not_tested"], {"worlds": tens[0][8:], "reason": "A call tests 8 worlds at most."})

    def test_two_calls_in_one_turn_are_two_calls_and_a_call_too_many_is_not_run(self):
        pair = lambda turn: Reply(tuple(block for half in (0, 1) for block in calls(stress.TOOL, {"worlds": SINGLES[8 * (2 * turn + half):][:8]},
                                                                                      f"call_{turn}_{half}").content), "tool_use")
        model = Scripted([pair(0), pair(1), pair(2), writes(lambda world: PLAIN)])
        result = stress.run(TREE, STORY, model, lang="en")
        self.assertEqual((result["budget"]["calls_used"], result["budget"]["worlds_tested"], result["stopped"]), (5, 40, "budget"))
        last = model.requests[3]["messages"][-1]["content"] if len(model.requests) > 3 and model.requests[3]["tools"] else None
        self.assertIsNone(last, "After the fifth call the search is over")
        # The sixth call of the third turn got an answer, as the conversation requires, and was not run.
        search = stress.search(stress.Route(Tree(ALEXIA), STORY), Scripted([pair(0), pair(1), pair(2)]))
        answered = search["messages"][-1]["content"]
        self.assertEqual([block["tool_use_id"] for block in answered], ["call_2_0", "call_2_1"])
        self.assertEqual((json.loads(answered[1]["content"]), answered[1]["is_error"]),
                         ({"error": "The budget is used up: 5 calls. This call was not run."}, True))
        self.assertEqual(len(search["tested"]), 40)

    def test_a_world_outside_the_grammar_comes_back_with_the_refusal_of_the_engine(self):
        outside = ["krach@40", "krach@24~500", "a+b+c", "krach@24+krach@24", "krach@24+reference", "covid@22", "krach@24~130", "reference"]
        model = Scripted([calls(stress.TOOL, {"worlds": outside}, "one"), says("Nothing more.")])
        found = stress.search(stress.Route(Tree(ALEXIA), STORY), model)
        self.assertEqual((found["tested"], found["stopped"], len(found["calls"])), ({}, "model", 1))
        refused = {refusal["asked"]: refusal["reason"] for refusal in told(model, 0)["refused"]}
        self.assertEqual(list(refused), outside)
        with i18n.use("en"):
            for world in outside[:5]:                 # refused by the engine itself, in the engine's words
                with self.subTest(world=world), self.assertRaises(ValueError) as refusal:
                    W.canonical(world, TH, H, AGE0)
                self.assertEqual(refused[world], str(refusal.exception))
        self.assertEqual(refused["krach@40"], "The age of a crisis can be set from 21 to 29: 40 is refused.")
        self.assertEqual(refused["a+b+c"], "A world holds at most 2 crises: “a+b+c” has 3.")
        # Known to the engine, but not part of the search: an unknown type, a severity off the grid, a whole world.
        self.assertEqual(refused["covid@22"], "World “covid” not available yet. Types of crisis: krach, chomage_6_mois, perte_job_etudiant, "
                                              "inflation, crise_immobiliere, franc_faible, chomage_long.")
        self.assertEqual(refused["krach@24~130"], "The search covers five severities: 50, 75, 100, 125, 150. 130 is not one of them.")
        self.assertEqual(refused["reference"], "“reference” is a whole world, not a crisis: the search covers worlds with one crisis or two.")
        self.assertEqual((found["calls"][0]["refused"], found["calls"][0]["tested"]), (told(model, 0)["refused"], []))

    def test_a_call_with_a_mistake_in_it_counts_and_a_near_miss_of_the_name_is_understood(self):
        model = Scripted([calls(stress.TOOL, {"worlds": "krach@24"}, "one"), calls("simulate", {"worlds": ["krach@24"]}, "two"),
                          calls("test-worlds", {"worlds": ["krach@24"]}, "three"), calls("testWorld", {"worlds": [LONG, 27]}, "four"),
                          says("Done.")])
        found = stress.search(stress.Route(Tree(ALEXIA), STORY), model)
        self.assertEqual((len(found["calls"]), list(found["tested"]), found["stopped"]), (4, ["krach@24", LONG], "model"))
        self.assertEqual(told(model, 0), {"error": 'test_worlds takes a list of world identifiers: {"worlds": ["krach@24", ...]}.', "calls_left": 4,
                                          "worlds_tested_so_far": 0})
        self.assertEqual(told(model, 1), {"error": "Unknown tool. The only tool is test_worlds.", "calls_left": 3})
        self.assertEqual([model.requests[turn + 1]["messages"][-1]["content"][0].get("is_error", False) for turn in range(4)], [True, True, False, False])
        self.assertEqual(told(model, 3)["refused"], [{"asked": "27", "reason": "A world is written as text: type@age~severity, or two of them joined by “+”."}])

    def test_what_the_tool_tells_about_a_world_is_what_the_engine_computes(self):
        model = Scripted([calls(stress.TOOL, {"worlds": [LONG, "chomage_long@25+krach@24", LONG]}, "one"), says("Done.")])
        found = stress.search(stress.Route(Tree(ALEXIA), STORY), model)
        result = live(LONG)
        self.assertEqual(told(model, 0)["tested"][0],
                         {"world": LONG, "name": "Long unemployment at 27", "goals_kept": 1, "goals_lost": ["Career change", "Resilience"],
                          "peak_borrowing_chf": round(result.peak_financing_chf), "net_worth_at_the_end_chf": round(result.net_worth_end_chf),
                          "missing": [{"goal": "Career change", "at_age": 28, "reached_chf": -5145, "asked_chf": 39366},
                                      {"goal": "Resilience", "at_age": 29, "reached_chf": 8519, "asked_chf": 18600}]})
        # Written in another order, a world is the same world; asked twice, it is simulated once.
        self.assertEqual((list(found["tested"]), found["calls"][0]["already_tested"]), ([LONG, "krach@24+chomage_long@25"], [LONG]))
        self.assertEqual([world["world"] for world in told(model, 0)["tested"]], [LONG, "krach@24+chomage_long@25", LONG])
        for world, summary in found["tested"].items():
            direct = live(world)
            with self.subTest(world=world):
                self.assertEqual((summary["goals_lost"], summary["goals_kept"], summary["peak_financing_chf"], summary["net_worth_end_chf"]),
                                 (lost(world), sum(doors_of(direct, TH, AGE0).values()), round(direct.peak_financing_chf, 2), round(direct.net_worth_end_chf, 2)))

    def test_the_conversation_only_grows_and_what_the_model_said_goes_back_unchanged(self):
        thinking = {"type": "thinking", "thinking": "Unemployment after the master's looks worst.", "signature": "sig-1"}
        first = Reply((thinking, *calls(stress.TOOL, {"worlds": [LONG]}, "one", "Let me test.").content), "tool_use")
        model = Scripted([first, calls(stress.TOOL, {"worlds": [TWICE]}, "two"), calls(stress.TOOL, {"worlds": [BOTH]}, "three"), says("Done."),
                          writes(lambda world: "You borrow about 40'000 CHF."), writes(lambda world: PLAIN)])
        stress.run(TREE, STORY, model, lang="en")
        search, explanation = model.requests[:4], model.requests[4:]
        for conversation in (search, explanation):
            for before, after in zip(conversation, conversation[1:]):
                self.assertEqual(after["messages"][:len(before["messages"])], before["messages"], "Nothing already said is rewritten")
                self.assertGreater(len(after["messages"]), len(before["messages"]))
                self.assertEqual((after["system"], after["tools"], after["output"]), (before["system"], before["tools"], before["output"]))
        self.assertEqual(search[1]["messages"][1], {"role": "assistant", "content": list(first.content)})
        self.assertEqual(search[1]["messages"][1]["content"][0], thinking)
        self.assertEqual([message["role"] for message in search[3]["messages"]], ["user", "assistant", "user", "assistant", "user", "assistant", "user"])
        self.assertEqual([message["role"] for message in explanation[1]["messages"]], ["user", "assistant", "user"])

    def test_a_model_that_does_not_call_the_tool_is_reminded_once_and_never_twice(self):
        model = Scripted([says("The hardest world is surely a crash."), calls(stress.TOOL, {"worlds": [LONG]}, "one"), says("Done.")])
        found = stress.search(stress.Route(Tree(ALEXIA), STORY), model)
        self.assertEqual(model.requests[1]["messages"][-1], {"role": "user", "content": "Use the test_worlds tool to test worlds: nothing has been tested yet."})
        self.assertEqual((list(found["tested"]), found["stopped"]), ([LONG], "model"))
        silent = Scripted([says("A crash."), says("A crash, I said.")])
        found = stress.search(stress.Route(Tree(ALEXIA), STORY), silent)
        self.assertEqual((found["tested"], found["stopped"], len(silent.requests)), ({}, "no_call", 2))

    def test_a_refusal_of_the_model_stops_the_search_and_the_engine_still_answers(self):
        model = Scripted([Reply((), "refusal")])
        result = stress.run(TREE, STORY, model, lang="en")
        self.assertEqual((result["stopped"], result["tested"], result["ranking"], len(model.requests)), ("refusal", [], [], 1))
        self.assertEqual((result["verification"]["single_crises"]["harder_than_found"], result["verification"]["single_crises"]["max_goals_lost"]), (True, 2))

    def test_the_assumptions_alexia_changed_are_told_to_the_model_and_used_by_the_engine(self):
        changed = {"loyer": 1500.0}
        model = Scripted([calls(stress.TOOL, {"worlds": [LONG]}, "one"), says("Done."), writes(lambda world: PLAIN)])
        result = stress.run(TREE, STORY, model, overrides=changed, lang="en")
        # She is named what she changed as the drawer shows it, not by the key the engine keeps it under.
        self.assertIn("\n\nAssumptions changed by Alexia\n- Rent [CHF/month]: 1'500 (the engine starts from 900)\n\nThe six goals.",
                      model.requests[0]["messages"][0]["content"])
        self.assertNotIn("loyer", model.requests[0]["messages"][0]["content"])
        rate = Scripted([says("Nothing to test."), says("Still nothing.")])
        stress.run(TREE, STORY, rate, overrides={"rendement_placements_annuel": 0.05, "not_an_assumption": 3.0}, lang="fr")
        self.assertIn("\nAssumptions changed by Alexia\n- Return on investments (reference world) [%/year]: 5 (the engine starts from 3)\n\n",
                      rate.requests[0]["messages"][0]["content"])
        th = theta_for(ALEXIA, changed)
        direct = run_ops(ALEXIA.profile, blocks_to_ops(STORY, th, H), H, th, W.build(th, LONG, H, AGE0))
        self.assertEqual((result["tested"][0]["peak_financing_chf"], result["tested"][0]["net_worth_end_chf"]),
                         (round(direct.peak_financing_chf, 2), round(direct.net_worth_end_chf, 2)))
        self.assertNotEqual(result["tested"][0]["peak_financing_chf"], round(live(LONG).peak_financing_chf, 2))
        self.assertIn(f"- Peak borrowing in this world: {chf(direct.peak_financing_chf)}", model.requests[2]["messages"][0]["content"])

    def test_the_search_is_held_in_english_and_says_what_the_model_needs(self):
        model = Scripted([calls(stress.TOOL, {"worlds": [LONG]}, "one"), says("Done."), writes(lambda world: "Cette crise arrive au pire moment.")])
        stress.run(TREE, STORY, model, lang="fr")
        request = model.requests[0]
        brief = request["messages"][0]["content"]
        for words in ("5 calls of the tool, 8 worlds per call at most, so 40 worlds out of 49140", "You compute nothing."):
            self.assertIn(words, request["system"])
        for words in ("- Job in Lausanne, from age 20 to age 25", "- Job search, from age 27 to 27 years 3 months", "Assumptions changed by Alexia: none",
                      "With no crisis the route keeps 3 of 6.", "- Career change (at 28): kept with no crisis (42200 CHF for 39366 CHF asked).",
                      "- Never go into the red (over the whole route): not kept even with no crisis, so no crisis can make the route lose it.",
                      "- chomage_long: Long unemployment. Job loss for twelve months", "Ages: 21 to 29. Severities: 50, 75, 100, 125, 150",
                      "The space holds 49140 worlds. You have 5 calls of at most 8 worlds."):
            self.assertIn(words, brief)
        tool = request["tools"][0]
        self.assertEqual((tool["name"], tool["strict"], tool["input_schema"]["additionalProperties"], tool["input_schema"]["required"]),
                         ("test_worlds", True, False, ["worlds"]))
        self.assertEqual((request["effort"], request["output"]), ("medium", None))
        # The prompt gives the grammar and no answer: no world that breaks this route is named in it.
        for hint in ("benefit", "chomage", "unemploy", "contribut"):
            self.assertNotIn(hint, request["system"] + brief.split("The types of crisis")[0] + json.dumps(tool))


class TheRanking(unittest.TestCase):
    """What was tested is ranked by code: goals lost, then total severity, then peak borrowing."""
    TESTED = ["franc_faible@22", "krach@24", "chomage_long@27~150", LONG, "inflation@21", TWICE, BOTH, "chomage_6_mois@27"]

    def run_with(self, *turns, lang="en", **more):
        model = Scripted(list(turns))
        return stress.run(TREE, STORY, model, lang=lang, **more), model

    def test_the_ranking_is_the_one_of_the_engine_whatever_the_model_concludes(self):
        result, _ = self.run_with(calls(stress.TOOL, {"worlds": self.TESTED}, "one"), says("The hardest world is franc_faible@22, by far."),
                                  writes(lambda world: PLAIN))
        # The same order, computed here from the engine alone.
        measured = {W.canonical(world, TH, H, AGE0): live(world) for world in self.TESTED}
        order = sorted(measured, key=lambda world: (-len(lost(world)), V.severity(world), -measured[world].peak_financing_chf, world))
        expected, seen = [], set()
        for world in order:
            if lost(world) and V.types(world) not in seen:
                seen.add(V.types(world))
                expected.append(world)
        self.assertEqual([world["world"] for world in result["ranking"]], expected[:3])
        self.assertEqual(expected[:3], [TWICE, LONG, BOTH])
        self.assertEqual([(len(world["goals_lost"]), world["severity"]) for world in result["ranking"]], [(3, 200), (2, 100), (2, 200)])
        # The milder of two worlds of the same types is the one kept: twelve months at 27, not eighteen.
        self.assertNotIn("chomage_long@27~150", [world["world"] for world in result["ranking"]])
        for world in result["ranking"]:
            direct = live(world["world"])
            with self.subTest(world=world["world"]):
                self.assertEqual((world["goals_lost"], world["goals_kept"], world["goals_total"]), (lost(world["world"]), 3 - len(lost(world["world"])), 6))
                self.assertEqual((world["peak_financing_chf"], world["net_worth_end_chf"]),
                                 (round(direct.peak_financing_chf, 2), round(direct.net_worth_end_chf, 2)))
        self.assertEqual((result["ranking"][0]["name"], result["ranking"][0]["goals_lost_names"]),
                         ("Long unemployment at 23 + long unemployment at 24", ["Emergency savings", "Career change", "Resilience"]))
        self.assertEqual(result["calm"], {"goals_kept": 3, "goals_total": 6, "peak_financing_chf": 14233.94, "net_worth_end_chf": 96749.17})

    def test_a_world_that_loses_no_goal_is_not_ranked_and_nothing_is_explained(self):
        result, model = self.run_with(calls(stress.TOOL, {"worlds": ["franc_faible@22", "crise_immobiliere@24", "chomage_long@26"]}, "one"), says("Done."))
        self.assertEqual((result["ranking"], [len(world["goals_lost"]) for world in result["tested"]], len(model.requests)), ([], [0, 0, 0], 2))
        self.assertTrue(result["verification"]["single_crises"]["harder_than_found"])

    def test_the_engine_says_whether_a_single_crisis_is_harder_than_what_was_found(self):
        cases = {("krach@24",): (True, False), (LONG,): (False, False), ("chomage_long@27~150",): (False, True), (TWICE,): (False, False)}
        for tested, (harder, milder) in cases.items():
            result, _ = self.run_with(calls(stress.TOOL, {"worlds": list(tested)}, "one"), says("Done."), writes(lambda world: PLAIN))
            checked = result["verification"]["single_crises"]
            with self.subTest(tested=tested):
                self.assertEqual((checked["scanned"], checked["max_goals_lost"], checked["harder_than_found"], checked["as_hard_and_milder"]),
                                 (315, 2, harder, milder))
                self.assertEqual([(world["world"], world["name"], world["goals_lost"]) for world in checked["hardest"]],
                                 [(LONG, "Long unemployment at 27", ["reconversion", "resilience"])])
        # The scan itself, made again here: no single crisis of the space loses more than two goals on this route.
        self.assertEqual(max(len(lost(world)) for world in SINGLES[::7]), 2)

    def test_the_true_answer_of_the_benchmark_is_cited_when_it_is_given(self):
        truth = {"route": "story_a", "worlds": 49140, "max_goals_lost": 3, "hardest_count": 1, "least_severity": 200, "hardest": []}
        for tested, found in (((LONG,), False), ((TWICE,), True)):
            result, _ = self.run_with(calls(stress.TOOL, {"worlds": list(tested)}, "one"), says("Done."), writes(lambda world: PLAIN), truth=truth)
            self.assertEqual(result["verification"]["benchmark"], {**truth, "found": found})
        result, _ = self.run_with(calls(stress.TOOL, {"worlds": [LONG]}, "one"), says("Done."), writes(lambda world: PLAIN))
        self.assertIsNone(result["verification"]["benchmark"])

    def test_the_signposts_are_the_sentences_of_the_engine(self):
        result, _ = self.run_with(calls(stress.TOOL, {"worlds": [TWICE, LONG]}, "one"), says("Done."), writes(lambda world: PLAIN))
        for world in result["ranking"]:
            with i18n.use("en"):
                rows = Tree(ALEXIA).pathways_view(STORY, 0, None, ["reference", world["world"]])["by_world"][world["world"]]["doors"]
            expected = [(row["key"], row["signpost"]["text"]) for row in rows if row["key"] in world["goals_lost"] and row["signpost"]]
            with self.subTest(world=world["world"]):
                self.assertEqual([(sign["goal"], sign["text"]) for sign in world["signposts"]], expected)
        self.assertEqual([sign["text"] for sign in result["ranking"][0]["signposts"]][:1],
                         ["If you have less than 52'800 CHF set aside (cash + investments − debts) at 24, this route no longer holds “Emergency savings”."])
        # Twelve months of unemployment at 27 come after the last decision: the engine has no signpost, and the list is empty.
        self.assertEqual(result["ranking"][1]["signposts"], [])


class TheExplanations(unittest.TestCase):
    """One or two sentences per world, checked against the facts of that world. A refused text is never shown."""

    def search_then(self, *turns, lang="en"):
        model = Scripted([calls(stress.TOOL, {"worlds": [TWICE, LONG, BOTH]}, "one"), says("Done."), *turns])
        return stress.run(TREE, STORY, model, lang=lang), model

    def test_each_text_is_checked_against_the_facts_of_its_own_world(self):
        peak = {world: chf(live(world).peak_financing_chf) for world in (TWICE, LONG, BOTH)}
        good = {TWICE: f"Two long spells of unemployment in a row, at 23 and at 24: the second comes with no benefit. You borrow up to {peak[TWICE]} "
                       "and keep none of your 6 goals.",
                LONG: f"Twelve months of unemployment at 27, right after your master's: you borrow up to {peak[LONG]} and keep 1 goal of 6.",
                BOTH: f"The crash at 24 is not what breaks the route: unemployment at 27 is. You borrow up to {peak[BOTH]} and lose 2 goals."}
        wrong = {**good, BOTH: f"You end with {chf(live(TWICE).net_worth_end_chf)} and lose 2 goals."}        # the net worth of another world
        result, model = self.search_then(writes(wrong), writes(good))
        explained = {world["world"]: world["explanation"] for world in result["ranking"]}
        self.assertEqual({world: (text["accepted"], text["attempts"]) for world, text in explained.items()}, {TWICE: (True, 1), LONG: (True, 1), BOTH: (True, 2)})
        self.assertEqual({world: text["text"] for world, text in explained.items()}, good)
        self.assertEqual({world: text["label"] for world, text in explained.items()},
                         {TWICE: "✓ 6 figures verified", LONG: "✓ 5 figures verified", BOTH: "✓ 4 figures verified"})
        # "Two" spells are the two crises of the world, and "none" of the goals is a count like another: zero goals kept.
        self.assertEqual([(figure["text"], figure["value"], figure["origins"][0]) for figure in explained[TWICE]["figures"]],
                         [("Two", 2.0, "Crises in this world"), ("23", 23.0, "Long unemployment at 23: start"),
                          ("24", 24.0, "Long unemployment at 24: start"), (peak[TWICE], 65024.0, "Peak borrowing in this world"),
                          ("none", 0.0, "Goals kept in this world"), ("6", 6.0, "Goals in all")])
        self.assertEqual([(figure["text"], figure["origins"]) for figure in explained[LONG]["figures"]],
                         [("Twelve months", ["Long unemployment at 27: length", "Job lost: length"]),
                          ("27", ["Long unemployment at 27: start", "Job search: start", "Going back to study: age"]),      # the engine gave 27 three times
                          (peak[LONG], ["Peak borrowing in this world"]),
                          ("1", ["Goals kept in this world"]),          # next to "keep": the goals kept, not the one crisis of this world
                          ("6", ["Goals in all"])])
        # The second request names the refused world only, and says what was refused.
        again = model.requests[3]["messages"][-1]["content"]
        self.assertEqual(again, "The checker refused these texts. Write them again, and only them.\n\nWorld krach@24+chomage_long@27\n"
                                "The checker refused this text. Copy every figure exactly as the engine gave it, with its sign and its unit. "
                                "No rounding, no ratio, no figure of your own.\n"
                                f"- “{chf(live(TWICE).net_worth_end_chf)}” is not a figure the engine gave for this text. It is a figure of another world "
                                f"({TWICE}), not of this one.")
        self.assertEqual(explained[BOTH]["refusals"], [["figure"]])

    def test_the_role_of_a_number_is_checked_in_an_explanation(self):
        result, model = self.search_then(writes({TWICE: PLAIN, LONG: "You keep 2 goals of 6.", BOTH: PLAIN}), writes(lambda world: "You keep 1 goal of 6."))
        self.assertIn("“2” stands next to “keep”: the number of goals kept in this world is 1.", model.requests[3]["messages"][-1]["content"])
        self.assertEqual([(world["explanation"]["accepted"], world["explanation"]["attempts"]) for world in result["ranking"]], [(True, 1), (True, 2), (True, 1)])

    def test_the_figures_of_the_route_with_no_crisis_have_a_sentence_of_their_own(self):
        """The model is told so, and the checker reads it so: "with no crisis the route keeps 3 goals" is checked against
        the route with no crisis, and the same 3 next to "keep" in the sentence about a world is refused."""
        slip = {TWICE: PLAIN, LONG: "You keep 3 goals, and after twelve months of unemployment only 1.", BOTH: PLAIN}
        right = lambda world: "With no crisis the route keeps 3 goals and borrows up to 14'234 CHF. Here you keep 1 goal and borrow up to 43'123 CHF."
        result, model = self.search_then(writes(slip), writes(right))
        system = model.requests[2]["system"]
        for words in ('Never put the number of goals kept with no crisis next to "keep" in the sentence that says what happens in that world.',
                      'write it in a sentence of its own that says "with no crisis": "With no crisis the route keeps 3 goals." The same holds',
                      'Next to "keep", "hold" or "lose"', 'Next to "borrow" or "finance"'):
            self.assertIn(words, system)
        self.assertIn("“3” stands next to “keep”: the number of goals kept in this world is 1. To give the figure of the route with no crisis, write it in a "
                      "sentence of its own that says “with no crisis”.", model.requests[3]["messages"][-1]["content"])
        explained = result["ranking"][1]["explanation"]
        self.assertEqual((explained["accepted"], explained["attempts"], explained["text"]), (True, 2, right(LONG)))
        self.assertEqual([(figure["text"], figure["origins"]) for figure in explained["figures"]],
                         [("3", ["Goals kept with no crisis"]), ("14'234 CHF", ["Peak borrowing with no crisis"]), ("1", ["Goals kept in this world"]),
                          ("43'123 CHF", ["Peak borrowing in this world"])])

    def test_three_refused_texts_leave_the_facts_of_the_engine_alone(self):
        result, model = self.search_then(writes(lambda world: "You borrow about 40'000 CHF."), writes(lambda world: "Your debt doubles."),
                                         writes(lambda world: "This is the best case: 99 goals."))
        self.assertEqual(len(model.requests), 5)
        for world in result["ranking"]:
            with self.subTest(world=world["world"]):
                self.assertEqual(world["explanation"], {"accepted": False, "text": None, "label": "AI explanation rejected by the checker", "verified": 0,
                                                        "figures": [], "attempts": 3,
                                                        "refusals": [["approximation", "role"], ["ratio"], ["banned", "figure"]]})
                direct = live(world["world"])
                self.assertEqual([(fact["origin"], fact["written"]) for fact in world["facts"] if fact["headline"]],
                                 [("Goals kept in this world", str(world["goals_kept"])), ("Goals lost in this world", str(len(world["goals_lost"]))),
                                  ("Peak borrowing in this world", chf(direct.peak_financing_chf)),
                                  ("Net worth at the end in this world", chf(direct.net_worth_end_chf))])
        self.assertEqual(result["rejected_label"], "AI explanation rejected by the checker")
        for words in ("40'000", "doubles", "best case", "99 goals"):
            self.assertNotIn(words, json.dumps(result, ensure_ascii=False), "No word of a refused text is in the result")

    def test_an_answer_that_is_not_the_json_asked_or_a_refusal_is_no_text(self):
        result, model = self.search_then(says("Here is what I think: it is bad."), Reply((), "refusal"), writes(lambda world: PLAIN))
        self.assertEqual([(world["explanation"]["accepted"], world["explanation"]["attempts"], world["explanation"]["refusals"]) for world in result["ranking"]],
                         [(True, 3, [["empty"], ["empty"]])] * 3)
        self.assertEqual(model.requests[3]["messages"][-1]["content"].count("- The text is empty."), 3)

    def test_the_facts_given_to_the_model_are_the_facts_the_checker_uses(self):
        result, model = self.search_then(writes(lambda world: PLAIN))
        request = model.requests[2]
        brief = request["messages"][0]["content"]
        self.assertEqual((request["tools"], request["effort"], asked(request)), ([], "medium", [TWICE, LONG, BOTH]))
        self.assertIn("in English", request["system"])
        for world in result["ranking"]:
            section = brief.split(f"World {world['world']}: {world['name']}\n")[1].split("\n\n")[0].splitlines()
            shown = [f"- {fact['origin']} (quote): “{fact['written']}”" if fact["quote"] else f"- {fact['origin']}: {fact['written']}" for fact in world["facts"]]
            with self.subTest(world=world["world"]):
                self.assertTrue(set(section) <= set(shown))
                self.assertEqual(section[:4], shown[:4])
        self.assertIn("- Note of the ledger (quote): “No unemployment benefit: 0 months contributed out of 24, 12 are required”", brief)
        self.assertIn("Figures common to every world\n- Goals in all: 6\n- Goals kept with no crisis: 3\n- Goals lost with no crisis: 0\n"
                      "- Peak borrowing with no crisis: 14'234 CHF", brief)
        self.assertIn("- Career change: amount asked: 39'366 CHF\n- Career change: amount reached with no crisis: 42'200 CHF", brief)

    def test_the_prompt_of_the_explanations_names_the_words_of_one_language_only(self):
        """The instructions are in English for both languages. The words to mind and the example are those of the language
        the model writes in: a request for an English text holds no French, and a request for a French text names the
        French words the checker looks at."""
        english = stress.EXPLAIN.format(**stress.WORDS["en"])
        french = stress.EXPLAIN.format(**stress.WORDS["fr"])
        self.assertEqual(set(stress.WORDS["en"]), set(stress.WORDS["fr"]))
        self.assertNotIn("{", english + french)
        self.assertIsNone(re.search(r"[àâçéèêëîïôöùûüœ«»]|\b(?:garde\w*|tenir|perdre|emprunt\w*|financer|moitié|risque|meilleur|sans crise|mois|objectifs)\b", english),
                          "no French in the prompt for an English text")
        for words in ('in English', 'addressed to Alexia ("you")', "43'123 CHF, −5'145 CHF, 12 months", '"double", "half", "twice", "a third"',
                      "chance, probability, likely, odds, risk, best, recommend, advise, guarantee. Do not rank"):
            self.assertIn(words, english)
        for words in ("in French", "addressed to Alexia (« tu »)", "43'123 CHF, −5'145 CHF, 12 mois", "« double », « moitié », « deux fois », « un tiers »",
                      "Next to « garder », « tenir » or « perdre », in any of their forms, a number of goals", "Next to « emprunter », « emprunt » or « financer », an amount",
                      "next to « garder » in the sentence", "that says « sans crise »: « Sans crise, le trajet garde 3 objectifs. » The same holds",
                      "chance, probabilité, probable, risque, meilleur, recommander, conseiller, garantir. Do not rank"):
            self.assertIn(words, french)
        self.assertIsNone(re.search(r'"keep"|"hold"|"lose"|"borrow"|"with no crisis"|probability|recommend', french), "and no English word to mind in the other")
        # In both: the name of a world comes from the quote given, and its identifier stays out of the text.
        for prompt in (english, french):
            self.assertIn('To name a world or one of its crises, copy the name given as a quote. The identifier of a world, the code with an "@", goes in the '
                          'field "world" of your answer and nowhere in your text.', prompt)
        # Every word the prompt tells the model to mind is one the checker does mind, in that language.
        for lang, text, kinds in (("en", "You keep 2 goals.", "role"), ("fr", "Tu gardes 2 objectifs.", "role"), ("fr", "Tu tiens 2 objectifs.", "role"),
                                  ("en", "You borrow 9 CHF.", "role"), ("fr", "Tu empruntes 9 CHF.", "role"), ("fr", "Un emprunt de 9 CHF.", "role"),
                                  ("en", "This is the best route.", "banned"), ("fr", "C'est le meilleur trajet.", "banned"), ("fr", "Le risque est là.", "banned"),
                                  ("en", "Twice as hard.", "ratio"), ("fr", "Deux fois plus dur, la moitié en moins.", "ratio")):
            facts = [Fact.count(1, "kept", "w", "kept"), Fact.chf(43123, "borrowed", "w", "borrowed"), Fact.count(2, "crises", "w"), Fact.chf(9, "other", "w")]
            report = check(text, facts, [], [], lang)
            with self.subTest(text=text):
                self.assertIn(kinds, {problem.kind for problem in report.problems})

    def test_the_explanation_is_asked_in_the_language_of_the_screen_with_the_same_figures(self):
        french, model = self.search_then(writes(lambda world: "Cette crise arrive au pire moment."), lang="fr")
        english, _ = self.search_then(writes(lambda world: PLAIN), lang="en")
        request = model.requests[2]
        self.assertIn("in French", request["system"])
        for words in ("Explique ces mondes, une ou deux phrases pour chacun.", "Monde chomage_long@27: Chômage long à 27 ans",
                      "- Objectifs gardés dans ce monde: 1", "- Emprunt maximal dans ce monde: 43'123 CHF", "- Chômage long à 27 ans : durée: 12 mois",
                      "- Note du registre (citation): “Pas d'indemnité de chômage : 0 mois cotisés sur 24, il en faut 12”", "Chiffres communs à tous les mondes"):
            self.assertIn(words, request["messages"][0]["content"])
        self.assertEqual((french["language"], french["ranking"][1]["name"], french["ranking"][1]["goals_lost_names"], french["ranking"][1]["explanation"]["label"],
                          french["rejected_label"]),
                         ("fr", "Chômage long à 27 ans", ["Reconversion", "Résilience"], "✓ Aucun chiffre à vérifier", "Explication de l'IA rejetée par le contrôleur"))
        # The language changes the sentences, never a figure.
        figures = lambda result: [(world["world"], world["goals_kept"], world["goals_lost"], world["severity"], world["peak_financing_chf"],
                                   world["net_worth_end_chf"], [(fact["written"].split(" ")[0], fact["headline"]) for fact in world["facts"] if not fact["quote"]][:4])
                                  for world in result["ranking"]]
        self.assertEqual(figures(french), figures(english))
        self.assertEqual((french["tested"][0]["goals_lost"], french["verification"]["single_crises"]["max_goals_lost"]),
                         (english["tested"][0]["goals_lost"], english["verification"]["single_crises"]["max_goals_lost"]))


class TheModules(unittest.TestCase):
    def test_the_sdk_is_loaded_in_one_function_and_nothing_else_opens_a_connection(self):
        """The SDK is imported in one place: inside `build_client` of ai/model.py, the function the tests forbid. Nothing
        else in ai/ or in the scripts imports a client of any kind, so no test can reach a model by accident.
        One script is not of the AI layer: scripts/demo_gif.py makes the picture of the README. It starts Chrome and
        writes addresses of this machine: it imports what that takes, nothing more, and no client either."""
        forbidden = {"anthropic", "openai", "httpx", "httpx2", "requests", "urllib", "http", "socket", "ssl", "aiohttp", "subprocess"}

        def imports(node, inside=None) -> set:
            found = set()
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.Import):
                    found |= {(alias.name.split(".")[0], inside) for alias in child.names}
                elif isinstance(child, ast.ImportFrom) and child.module:
                    found.add((child.module.split(".")[0], inside))
                found |= imports(child, child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else inside)
            return found

        files = sorted((ROOT / "ai").glob("*.py")) + sorted((ROOT / "scripts").glob("*.py"))
        self.assertGreater(len(files), 9)
        for file in files:
            found = {(name, where) for name, where in imports(ast.parse(file.read_text(encoding="utf-8"))) if name in forbidden}
            with self.subTest(file=file.name):
                self.assertEqual(found, {"model.py": {("anthropic", "build_client")}, "demo_gif.py": {("subprocess", None), ("urllib", None)}}.get(file.name, set()))


if __name__ == "__main__":
    unittest.main()
