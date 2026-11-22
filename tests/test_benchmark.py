"""The benchmark of the stress-test agent (ai/benchmark.py, scripts/benchmark_agent.py, benchmarks/).

The true answer of each route comes from a full scan of the 49,140 worlds, made offline and kept in
benchmarks/truth.json. These tests do not run that scan again: they check its method on a space small enough to be
done by hand, and they check what is kept against the engine as it is today. No test calls a model.
"""
from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from ai import benchmark, stress
from ai import vocabulary as V
from ai.model import Scripted, calls, says
from engine import worlds as W
from engine.simulate import load_scenario, theta_for

ROOT = Path(__file__).resolve().parents[1]
ALEXIA = load_scenario(ROOT / "engine/scenarios/alexia.json")
TH = theta_for(ALEXIA)
H, AGE0 = ALEXIA.horizon_months, ALEXIA.profile.age
TWICE, LONG = "chomage_long@23+chomage_long@24", "chomage_long@27"
TRUTH = benchmark.load()["routes"]


class TheSpace(unittest.TestCase):
    """What the agent may propose: one crisis or two, seven types, nine ages, five severities."""

    def test_the_space_is_counted_and_every_world_of_it_can_be_listed(self):
        singles, pairs = V.singles(TH, H, AGE0), list(V.pairs(TH, H, AGE0))
        self.assertEqual((len(V.kinds(TH, H, AGE0)), W.ages(H, AGE0), V.SEVERITIES), (7, (21, 29), (50, 75, 100, 125, 150)))
        self.assertEqual((len(singles), 7 * 9 * 5, len(pairs), len(set(pairs)), V.size(TH, H, AGE0)), (315, 315, 48825, 48825, 49140))
        self.assertEqual(sum(1 for _ in V.worlds(TH, H, AGE0)), 49140)
        # All the pairs of single crises, less the same type at the same age twice: that would be a severity.
        self.assertEqual(len(pairs), math.comb(315, 2) - 7 * 9 * math.comb(5, 2))
        self.assertEqual((singles[0], singles[2], singles[-1]), ("chomage_6_mois@21~50", "chomage_6_mois@21", "perte_job_etudiant@29~150"))
        self.assertIn(TWICE, pairs)
        self.assertNotIn("krach@24~50+krach@24", pairs)
        # Each world is listed under the name the engine gives it: listed once, found again whatever the order it is asked in.
        for world in singles[::9] + pairs[::97]:
            with self.subTest(world=world):
                self.assertEqual(V.accept(world, TH, H, AGE0), W.canonical(world, TH, H, AGE0))
                if "+" in world:
                    self.assertEqual(W.canonical(world, TH, H, AGE0), world)
                    self.assertEqual(V.accept("+".join(reversed(world.split("+"))), TH, H, AGE0), world)

    def test_the_severity_and_the_types_of_a_world_are_read_in_its_name(self):
        for world, severity, types in (("krach", 100, ("krach",)), ("krach@24~150", 150, ("krach",)), (TWICE, 200, ("chomage_long", "chomage_long")),
                                       ("krach@24+chomage_long@25~50", 150, ("chomage_long", "krach")), ("inflation~75+krach@24~125", 200, ("inflation", "krach"))):
            with self.subTest(world=world):
                self.assertEqual((V.severity(world), V.types(world)), (severity, types))
                self.assertEqual(V.severity(world), sum(crisis["gravity"] for crisis in W.crises(TH, world, H, AGE0)))
                self.assertEqual(V.types(world), tuple(sorted(crisis["type"] for crisis in W.crises(TH, world, H, AGE0))))


class TheScan(unittest.TestCase):
    """The true answer: every world simulated by the engine."""

    @classmethod
    def setUpClass(cls):
        cls.story = benchmark.route_of("story_a")

    def test_on_a_space_small_enough_to_be_done_by_hand_the_scan_finds_what_we_know(self):
        """Three worlds: twelve months of unemployment at 23, at 24, and both. Each alone loses “Career change”; both lose
        three goals (tests/test_combined.py)."""
        found = benchmark.scan(self.story, ["chomage_long@23", "chomage_long@24", TWICE])
        self.assertEqual((found["worlds"], found["calm"], found["max_goals_lost"], found["histogram"], found["hardest_count"], found["least_severity"]),
                         (3, {"goals_kept": 3, "goals_total": 6}, 3, {"1": 2, "3": 1}, 1, 200))
        self.assertEqual(found["hardest"], [{"world": TWICE, "severity": 200, "types": ["chomage_long", "chomage_long"], "goals_kept": 0, "goals_total": 6,
                                             "goals_lost": ["coussin", "reconversion", "resilience"], "peak_financing_chf": 65024.31,
                                             "net_worth_end_chf": 24451.71}])
        # A space where nothing breaks has no hardest world.
        calm = benchmark.scan(self.story, ["franc_faible@22", "crise_immobiliere@24"])
        self.assertEqual((calm["max_goals_lost"], calm["hardest"], calm["hardest_count"], calm["least_severity"], calm["histogram"]), (0, [], 0, None, {"0": 2}))

    def test_the_single_crises_are_scanned_whole_and_the_mildest_of_the_hardest_comes_first(self):
        found = benchmark.scan(self.story, V.singles(TH, H, AGE0))
        self.assertEqual((found["worlds"], found["max_goals_lost"], found["histogram"], found["hardest_count"], found["least_severity"]),
                         (315, 2, {"0": 193, "1": 118, "2": 4}, 4, 100))
        self.assertEqual([(world["world"], world["severity"]) for world in found["hardest"]],
                         [(LONG, 100), ("chomage_long@27~125", 125), ("chomage_long@27~150", 150), ("chomage_long@23~150", 150)])

    def test_the_true_answers_kept_in_the_repository_are_what_the_full_scan_found(self):
        self.assertEqual(list(TRUTH), ["story_a", "work_only", "berlin"])
        self.assertEqual(benchmark.load()["space"], {"worlds": 49140, "types": list(V.kinds(TH, H, AGE0)), "ages": [21, 29],
                                                    "severities": [50, 75, 100, 125, 150], "crises_per_world": 2})
        expected = {"story_a": (3, 3, 47, 200, {"0": 18296, "1": 28133, "2": 2664, "3": 47}, 2),
                    "work_only": (6, 5, 21, 250, {"0": 13972, "1": 33302, "2": 1379, "3": 421, "4": 45, "5": 21}, 3),
                    "berlin": (5, 4, 53, 225, {"0": 37841, "1": 8107, "2": 2877, "3": 262, "4": 53}, 2)}
        for key, (kept, most, count, mildest, histogram, single) in expected.items():
            truth = TRUTH[key]
            with self.subTest(route=key):
                self.assertEqual((truth["path"], truth["worlds"], truth["calm"]), (stress.Route(benchmark.route_of(key).tree, benchmark.ROUTES[key]).path, 49140,
                                                                                    {"goals_kept": kept, "goals_total": 6}))
                self.assertEqual((truth["max_goals_lost"], truth["hardest_count"], truth["least_severity"], truth["histogram"]), (most, count, mildest, histogram))
                self.assertEqual((sum(truth["histogram"].values()), truth["histogram"][str(most)], truth["single_crises"]["max_goals_lost"]), (49140, count, single))
                self.assertEqual(len(truth["hardest"]), min(count, benchmark.LISTED))
                self.assertEqual([world["severity"] for world in truth["hardest"]], sorted(world["severity"] for world in truth["hardest"]))
        # Pairs are harder than single crises on every route: this is what the agent has to find.
        self.assertTrue(all(TRUTH[key]["max_goals_lost"] > TRUTH[key]["single_crises"]["max_goals_lost"] for key in TRUTH))
        self.assertEqual(TRUTH["story_a"]["hardest"][0]["world"], TWICE)
        # On the three routes, every hardest world listed holds two spells of unemployment, and the mildest are two long ones.
        self.assertTrue(all(set(V.types(world["world"])) <= {"chomage_long", "chomage_6_mois"} and "+" in world["world"]
                            for key in TRUTH for world in TRUTH[key]["hardest"]))
        self.assertTrue(all(V.types(TRUTH[key]["hardest"][0]["world"]) == ("chomage_long", "chomage_long") for key in TRUTH))

    def test_what_is_kept_is_still_what_the_engine_computes_today(self):
        """The file is a record: if the engine changed, it would be stale. Every hardest world listed is simulated again,
        and so is one world in 163 of the whole space: none may lose more goals than the answer kept."""
        for key, truth in TRUTH.items():
            route = benchmark.route_of(key)
            for world in truth["hardest"]:
                with self.subTest(route=key, world=world["world"]):
                    self.assertEqual(route.measure(world["world"]), world)
                    self.assertEqual(len(world["goals_lost"]), truth["max_goals_lost"])
            sample = [route.measure(world) for index, world in enumerate(V.worlds(route.th, route.h, route.age0)) if index % 163 == 0]
            counts = {lost: sum(len(world["goals_lost"]) == lost for world in sample) for lost in range(7)}
            with self.subTest(route=key):
                self.assertEqual(len(sample), 302)
                self.assertLessEqual(max(len(world["goals_lost"]) for world in sample), truth["max_goals_lost"])
                self.assertTrue(all(counts[lost] <= truth["histogram"].get(str(lost), 0) for lost in counts))
            for world in truth["single_crises"]["hardest"]:
                self.assertEqual(route.measure(world["world"]), world)

    def test_the_true_answer_is_only_given_for_a_route_of_the_benchmark_with_unchanged_assumptions(self):
        given = benchmark.truth_for(benchmark.ROUTES["story_a"])
        self.assertEqual({name: given[name] for name in given if name != "hardest"},
                         {"route": "story_a", "worlds": 49140, "max_goals_lost": 3, "hardest_count": 47, "least_severity": 200})
        self.assertEqual([world["world"] for world in given["hardest"]], [world["world"] for world in TRUTH["story_a"]["hardest"][:3]])
        self.assertEqual(benchmark.truth_for([{"block": "job", "years": 10}])["route"], "work_only")
        self.assertIsNone(benchmark.truth_for(benchmark.ROUTES["story_a"], {"loyer": 1000}), "With a changed assumption the scan no longer applies")
        self.assertIsNone(benchmark.truth_for([{"block": "master", "years": 2}, {"block": "job", "years": 8}]), "Not a route of the benchmark")


class TheMeasures(unittest.TestCase):
    """How a run of the search is measured, on scripted models whose path is known."""
    MILD = [LONG, "krach@24", "inflation@21", "franc_faible@22"]                              # two goals lost at most: not the answer
    FOUND = [LONG, "krach@24", "chomage_long@22~125+chomage_long@24", "krach@24+krach@25"]     # the third loses three goals, with a severity of 225

    @staticmethod
    def model(*calls_of_worlds):
        return Scripted([calls(stress.TOOL, {"worlds": worlds}, f"call_{turn}") for turn, worlds in enumerate(calls_of_worlds)] + [says("Done.")])

    def test_a_run_is_measured_against_the_true_answer(self):
        truth, route = TRUTH["story_a"], benchmark.route_of("story_a")
        missed = benchmark.measure(stress.search(route, self.model(self.MILD)), truth)
        self.assertEqual(missed, {"found": False, "goals_lost": 2, "world": LONG, "worlds_tested": 4, "calls_used": 1, "stopped": "model",
                                  "severity_gap": None, "tokens": {}})
        found = benchmark.measure(stress.search(route, self.model(self.MILD, self.FOUND)), truth)
        self.assertEqual(found, {"found": True, "goals_lost": 3, "world": "chomage_long@22~125+chomage_long@24", "worlds_tested": 6, "calls_used": 2,
                                 "stopped": "model", "severity_gap": 25, "tokens": {}})
        # The mildest of the hardest worlds has a gap of zero; a search that tested nothing found nothing.
        self.assertEqual(benchmark.measure(stress.search(route, self.model([TWICE])), truth)["severity_gap"], 0)
        nothing = benchmark.measure(stress.search(route, Scripted([says("A crash."), says("A crash.")])), truth)
        self.assertEqual((nothing["found"], nothing["goals_lost"], nothing["world"], nothing["worlds_tested"], nothing["stopped"]), (False, 0, None, 0, "no_call"))

    def test_several_runs_give_the_share_of_runs_that_found_and_what_they_cost(self):
        played = benchmark.play("story_a", lambda run: self.model(self.MILD, self.FOUND) if run % 2 else self.model(self.MILD), runs=4)
        self.assertEqual({name: played[name] for name in played if name != "each"},
                         {"route": "story_a", "runs": 4, "found": 2, "share_found": 0.5, "budget": 40, "space": 49140, "max_goals_lost": 3,
                          "mean_worlds_tested": 5.0, "share_of_space_tested": 5.0 / 49140, "mean_severity_gap": 25.0})
        self.assertEqual([(run["found"], run["worlds_tested"]) for run in played["each"]], [(False, 4), (True, 6), (False, 4), (True, 6)])
        # On another route the answer is another one: five goals lost, which these worlds do not reach.
        self.assertEqual(benchmark.play("work_only", lambda run: self.model(self.FOUND), runs=1)["found"], 0)

    def test_random_search_is_drawn_the_same_way_every_time_and_agrees_with_the_count(self):
        for key, truth in TRUTH.items():
            drawn = benchmark.random_search(truth)
            hardest, space = truth["hardest_count"], truth["worlds"]
            exact = 1 - math.comb(space - hardest, 40) / math.comb(space, 40)
            with self.subTest(route=key):
                self.assertEqual(drawn, benchmark.random_search(truth), "The same seed gives the same draws")
                self.assertEqual((drawn["budget"], drawn["repetitions"], drawn["seed"], drawn["space"], drawn["hardest_count"]), (40, 1000, 2026, 49140, hardest))
                self.assertAlmostEqual(drawn["exact_share"], exact, places=12)
                self.assertLess(abs(drawn["share_found"] - exact), 0.02, "A thousand draws stay close to the share of all possible draws")
                self.assertEqual((sum(drawn["best_goals_lost"].values()), drawn["best_goals_lost"].get(str(truth["max_goals_lost"]), 0)), (1000, drawn["found"]))
        self.assertNotEqual(benchmark.random_search(TRUTH["story_a"], seed=1)["best_goals_lost"], benchmark.random_search(TRUTH["story_a"], seed=2)["best_goals_lost"])
        # With 40 worlds out of 49,140, chance finds one of the hardest worlds in fewer than one search in twenty.
        self.assertEqual([round(benchmark.random_search(TRUTH[key])["exact_share"], 4) for key in TRUTH], [0.0376, 0.017, 0.0423])
        # A budget as large as the space always finds; a space where nothing breaks has nothing to find.
        small = {"histogram": {"0": 5, "1": 3, "2": 2}, "max_goals_lost": 2}
        self.assertEqual((benchmark.random_search(small, budget=10, repetitions=20)["share_found"], benchmark.random_search(small, budget=10)["exact_share"]), (1.0, 1.0))
        self.assertEqual(benchmark.random_search({"histogram": {"0": 10}, "max_goals_lost": 0}, budget=4, repetitions=20)["found"], 0)

    def test_the_file_of_the_random_search_is_the_one_the_script_writes(self):
        kept = json.loads((ROOT / "benchmarks/random.json").read_text(encoding="utf-8"))
        self.assertEqual(kept, {"budget": 40, "routes": {key: benchmark.random_search(TRUTH[key]) for key in benchmark.ROUTES}})
        self.assertEqual([kept["routes"][key]["found"] for key in kept["routes"]], [51, 15, 56])


if __name__ == "__main__":
    unittest.main()
