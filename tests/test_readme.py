"""The README says nothing that the repository does not say: every figure of the page is computed again here.

The value table and the table of the benchmark are written again from the engine and from the files, line by line,
and each line must be in the page as it is. The other figures are looked for where they come from: the engine, the
tests, the reports. A figure of the engine that changes makes one of these tests fail until the page is brought up to
date; so does the day the AI layer is first run with a real model, and the page still says that it was not.
"""
from __future__ import annotations

import offline  # noqa: F401  the recorded mode, and no client of the SDK: before anything else

import importlib.util
import json
import re
import struct
import unittest
from pathlib import Path

from ai import benchmark, recordings
from ai import stress as stressing
from ai import vocabulary as V
from ai.model import MODEL
from engine import i18n
from engine import worlds as W
from engine.blocks import blocks_to_ops, normalize
from engine.explore import doors_of
from engine.simulate import load_scenario, run_ops, theta_for
from engine.tree import Tree, _chf

try:
    from fastapi.testclient import TestClient
    from api.main import app
except ImportError:  # pragma: no cover
    TestClient = None

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "README.md").read_text(encoding="utf-8")
FLAT = " ".join(PAGE.split())                           # the page on one line: a sentence is found whatever its line breaks
ALEXIA = load_scenario(ROOT / "engine/scenarios/alexia.json")
TH = theta_for(ALEXIA)
H, AGE0 = ALEXIA.horizon_months, ALEXIA.profile.age
STORY = normalize(benchmark.ROUTES["story_a"], H)       # the demo route: job five years, a master's at 25, job again
WORK = normalize(benchmark.ROUTES["work_only"], H)      # ten years of work in Lausanne
MASTER = {"termine": "master's finished at {age}", "pas_commence": "master's not started", "arrete": "master's stopped at {age}",
          "termine_en_travaillant": "master's finished at {age}, while working"}
REPOSITORY = "Amine-Senhadji/DOORS"                                  # where the repository is, as the badge says
WORKFLOW_PAGE = f"https://github.com/{REPOSITORY}/actions/workflows/tests.yml"
BADGE = f"{WORKFLOW_PAGE}/badge.svg?branch=main"
ROUTES = {"story_a": "Demo route", "work_only": "Ten years of work in Lausanne", "berlin": "Ten years in Berlin"}


def cents(amount: float) -> str:
    """An amount with its cents, as the page writes it: −64'427.29."""
    return ("−" if amount < 0 else "") + f"{abs(amount):,.2f}".replace(",", "'")


def whole(number: int) -> str:
    return f"{number:,}".replace(",", "'")


def live(path: list[dict], world_id: str):
    """The engine, with no tree and no route in between: the route simulated from the start, in this world."""
    return run_ops(ALEXIA.profile, blocks_to_ops(path, TH, H), H, TH, W.build(TH, world_id, H, AGE0))


def gif(file: Path) -> tuple[tuple[int, int], list[int]]:
    """The size of a GIF, and how long each of its pictures stays, in hundredths of a second."""
    data = file.read_bytes()
    assert data[:6] in (b"GIF87a", b"GIF89a"), "not a GIF"
    width, height, flags = struct.unpack("<HHB", data[6:11])
    at = 13 + (3 * 2 ** ((flags & 7) + 1) if flags & 0x80 else 0)          # the header, and the palette of the whole file
    delays, pictures = [], 0
    while data[at] != 0x3B:                                                # until the end mark of the file
        if data[at] == 0x21:                                               # an extension; 0xF9 says how long the next picture stays
            if data[at + 1] == 0xF9:
                delays.append(struct.unpack("<H", data[at + 4:at + 6])[0])
            at += 2
        else:                                                              # a picture: its header, its own palette, the size of its codes
            assert data[at] == 0x2C, "not a GIF this reader understands"
            flags = data[at + 9]
            at += 11 + (3 * 2 ** ((flags & 7) + 1) if flags & 0x80 else 0)
            pictures += 1
        while data[at]:                                                    # the blocks that follow, each with its length first
            at += data[at] + 1
        at += 1
    assert pictures == len(delays), "a picture has no duration"
    return (width, height), delays


class ThePage(unittest.TestCase):
    def test_every_link_and_every_picture_of_the_page_is_a_file_of_the_repository(self):
        targets = re.findall(r"\]\(([^)\s]+)\)", PAGE)
        self.assertGreater(len(targets), 20)
        for target in targets:
            with self.subTest(target=target):
                if target.startswith("https://"):
                    continue
                self.assertFalse(target.startswith(("http:", "/")), "a link of the page leaves the repository")
                self.assertTrue((ROOT / target.split("#")[0]).exists())
        # Outside the repository, the page only points to the profile of the challenge author, and to the workflow of its badge.
        self.assertEqual({target for target in targets if target.startswith("https://")}, {"https://www.linkedin.com/in/stefania-s/", BADGE, WORKFLOW_PAGE})

    def test_the_badge_stands_under_the_title_and_is_the_one_of_the_workflow_of_the_repository(self):
        lines = PAGE.splitlines()
        self.assertEqual(lines[0], "# Doors")
        self.assertEqual(lines[2], f"[![tests]({BADGE})]({WORKFLOW_PAGE})")
        self.assertTrue(lines[4].startswith("**Doors is a financial twin that computes policies, not plans"))           # the hook, then the picture
        self.assertTrue(lines[6].startswith("![Fifteen seconds of Doors"))
        # The badge names the file of the workflow, the branch it shows, and the name the workflow gives itself.
        workflow = ROOT / ".github/workflows/tests.yml"
        self.assertTrue(workflow.is_file())
        self.assertEqual(BADGE, f"https://github.com/{REPOSITORY}/actions/workflows/{workflow.name}/badge.svg?branch=main")
        self.assertIn("\nname: tests\n", workflow.read_text(encoding="utf-8"))
        self.assertIn("branches: [main]", workflow.read_text(encoding="utf-8"))
        for words in ("Every push to `main` and every pull request runs both suites on GitHub Actions ([`.github/workflows/tests.yml`](.github/workflows/tests.yml)): "
                      "`unittest` and `pytest`, side by side, with the Google Chrome of the runner.",
                      "Where there is no Chrome, the tests that read the page in a browser are skipped and the rest runs. No secret is needed: no test calls a model.",
                      "`CHROME_BIN` names it when it is not in one of the usual places."):
            self.assertIn(words, FLAT)

    def test_every_line_of_a_table_has_as_many_cells_as_its_head(self):
        tables, lines = [], PAGE.splitlines()
        for number, line in enumerate(lines):
            if line.startswith("|") and (number == 0 or not lines[number - 1].startswith("|")):
                tables.append([row for row in lines[number:] if row][:next((i for i, row in enumerate(lines[number:]) if not row.startswith("|")), None)])
        self.assertEqual(len(tables), 4)
        for table in tables:
            cells = [len(re.findall(r"(?<!\\)\|", row)) for row in table]
            with self.subTest(table=table[0][:60]):
                self.assertEqual(set(cells), {cells[0]})
                self.assertRegex(table[1], r"^\|(-+:?\|)+$")

    def test_the_picture_of_the_demo_lasts_fifteen_seconds_one_scene_after_another(self):
        spec = importlib.util.spec_from_file_location("demo_gif", ROOT / "scripts/demo_gif.py")
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        size, delays = gif(ROOT / "docs/demo.gif")
        self.assertEqual(size, (script.WIDTH, script.HEIGHT + script.STRIP))
        self.assertEqual(delays, [round(seconds * 100) for seconds, _, _ in script.SCENES])
        self.assertEqual((len(delays), sum(delays)), (5, 1500))
        self.assertLess((ROOT / "docs/demo.gif").stat().st_size, 2_000_000)
        self.assertIn("](docs/demo.gif)", PAGE)
        # The scenes are the ones the page announces, and no caption holds a figure of the engine: only ages and counts of scenes.
        self.assertEqual([address for _, address, _ in script.SCENES],
                         ["/", "/?monde=krach@24", "/?monde=krach@24&station=reconversion", "/?monde=krach@24&gare=72", "/?politiques=1"])
        for _, _, caption in script.SCENES:
            self.assertNotRegex(caption, r"CHF|\d'\d{3}")

    def test_the_bank_is_named_once_in_the_name_of_the_challenge_and_the_credits_are_whole(self):
        self.assertEqual(PAGE.count("U" + "BS"), 1)                    # written in two pieces: this file does not name the bank either
        for words in ("Built for the UBS AI Financial Twin Challenge (LauzHack 2026).", "not a forecast, not advice",
                      "[Stefania Stan](https://www.linkedin.com/in/stefania-s/), challenge author and information owner",
                      "included unchanged, with her permission, and are not covered by this project's licence",
                      "Amine Senhadji (interface, decision policies, AI layer and portfolio)",
                      "The engine was co-written with a teammate during the hackathon; his name will be added with his agreement.",
                      "This project was built with Claude Code, Anthropic's coding agent.", "MIT for the project's own code, see [LICENSE](LICENSE)"):
            self.assertIn(words, FLAT)


@unittest.skipIf(TestClient is None, "FastAPI is not installed: .venv/bin/pip install -r requirements.txt")
class TheFiguresOfTheEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        client = TestClient(app)
        ask = lambda route, **body: client.post(f"/{route}?lang=en", json={"path": STORY, "assumptions": {}, **body}).json()
        cls.policies = ask("policies")
        cls.route = ask("path", world_id="reference")
        cls.pathways = ask("pathways", gare_month=0, mondes=["reference", "krach@24"])
        cls.worlds = client.get("/worlds?lang=en").json()
        cls.served = {route.path for route in app.routes}

    def test_the_problem_is_told_with_the_figures_of_the_engine(self):
        calm, target = self.route["by_world"]["reference"], self.policies["target"]
        crash = self.policies["cells"]["fige"]["krach@24"]
        self.assertEqual((ALEXIA.profile.age, _chf(ALEXIA.profile.cash_chf), _chf(target["required_chf"]), target["age"]), (20, "8'000 CHF", "39'366 CHF", 28))
        self.assertEqual((_chf(calm["net_worth_end_chf"]), calm["doors_open"], crash["target_holds"], _chf(crash["regret_chf"])), ("96'749 CHF", 3, False, "6'268 CHF"))
        for words in ("Alexia is 20, lives in Lausanne and has 8'000 CHF set aside.", "enough set aside at 28 to change career: 39'366 CHF",
                      "ends at 96'749 CHF at 30", "A market crash at 24 is enough for this plan to miss the career change by 6'268 CHF."):
            self.assertIn(words, FLAT)

    def test_the_worlds_the_goals_and_the_signpost_are_the_ones_of_the_engine(self):
        worlds = self.worlds if isinstance(self.worlds, list) else self.worlds["worlds"]
        crises = [world for world in worlds if world["id"] != "reference"]
        self.assertEqual((len(worlds), len(crises), sum(world["catalog_id"] is not None for world in crises)), (7, 6, 5))
        self.assertEqual({(world["min_age"], world["max_age"]) for world in crises}, {(21, 29)})
        listed = ", ".join(world["name"].lower() for world in crises)
        self.assertIn(f"seven worlds: a reference world and six crises ({listed}). Five come from the challenge's catalogue of scenarios; the sixth, the student job lost, is ours",
                      FLAT)
        self.assertIsNone(next(world for world in crises if world["type"] == "perte_job_etudiant")["catalog_id"])
        # The signpost of the plan when the market crashes at 24, as the engine writes it.
        told = next(door for door in self.pathways["by_world"]["krach@24"]["doors"] if door["key"] == "reconversion")
        self.assertEqual((told["holds"], told["last_transfer"]["age"]), (False, 26))
        self.assertIn(f"With a market crash at 24, the signpost of the plan reads: “{told['signpost']['text']}”", FLAT)
        # The six goals, with the amounts and the ages of their rules.
        rules = {door["key"]: door["rule"] for door in self.route["doors"]}
        for key, parts, words in (("coussin", ("At 25", "12'800 CHF"), "emergency savings of 12'800 CHF at 25"),
                                  ("reconversion", ("At 28", "39'366 CHF"), "39'366 CHF at 28 for a career change"),
                                  ("etudes", ("At 27", "2 years of student life"), "two years of student life covered at 27"),
                                  ("resilience", ("At 29", "30% fall in investments", "6 months"), "six months of expenses left at 29 after a 30% fall in investments"),
                                  ("logement", ("500'000 CHF home",), "the own funds for a 500'000 CHF home at 30"),
                                  ("jamais_rouge", ("No overdraft financing",), "never go into the red")):
            with self.subTest(goal=key):
                for part in parts:
                    self.assertIn(part, rules[key])
                self.assertIn(words, FLAT)
        self.assertEqual(len(rules), 6)
        self.assertEqual([door["kind"] for door in self.route["doors"]].count("observe"), 2)        # two goals come from the challenge's data

    def test_the_value_table_is_written_line_by_line_from_the_engine(self):
        told, worlds = self.policies, self.policies["worlds"]
        heads = ["No shock" if world["id"] == "reference" else f"{world['name']} at {world['age']}" for world in worlds]
        self.assertIn("| | " + " | ".join(heads) + " |", PAGE)
        fate = lambda master: MASTER[master["state"]].format(age=master["age"])
        for policy in told["policies"]:
            row = told["cells"][policy["id"]]
            label = policy["rule"]["text"] if policy["rule"] else "The route, with nothing changed."
            cells = [f"{row[world['id']]['doors_open']} goals of {row[world['id']]['doors_total']}<br>{fate(row[world['id']]['master'])}<br>"
                     f"regret {_chf(row[world['id']]['regret_chf'])}" for world in worlds]
            with self.subTest(policy=policy["id"]):
                self.assertIn(f"| **{policy['name']}**<br>{label} | " + " | ".join(cells) + " |", PAGE)
        seer = told["clairvoyant"]
        cells = [f"{seer[world['id']]['doors_open']} goals of {seer[world['id']]['doors_total']}<br>{fate(seer[world['id']]['master'])}<br>"
                 f"{seer[world['id']]['label'][0].lower()}{seer[world['id']]['label'][1:]}" for world in worlds]
        self.assertIn("| *Clairvoyant benchmark*<br>What one would have chosen knowing the world in advance. | " + " | ".join(cells) + " |", PAGE)
        self.assertEqual([policy["name"] for policy in told["policies"]], ["Fixed plan", "Safety", "Balance", "Ambition"])
        self.assertEqual(told["target"]["name"], "Career change")

    def test_what_is_said_of_the_table_is_true_of_it(self):
        cells, crises = self.policies["cells"], [world["id"] for world in self.policies["worlds"] if world["id"] != "reference"]
        holds = lambda policy: [cells[policy][world]["target_holds"] for world in ["reference", *crises]]
        regrets = lambda policy: [cells[policy][world]["regret_chf"] for world in crises]
        self.assertEqual((holds("fige"), holds("equilibre"), holds("securite")), ([True, False, False, False], [True] * 4, [True] * 4))
        self.assertEqual((_chf(max(regrets("fige"))), _chf(min(regrets("ambition"))), _chf(max(regrets("ambition")))), ("12'474 CHF", "789 CHF", "8'329 CHF"))
        self.assertEqual([cells[policy]["reference"]["applies"] for policy in ("securite", "equilibre", "ambition")], [False] * 3)
        rules = {policy["id"]: policy["rule"] for policy in self.policies["policies"] if policy["rule"]}
        self.assertEqual((rules["securite"]["age"], rules["equilibre"]["age"], rules["ambition"]["age"]), (25, 26, 26))
        for words in ("The fixed plan loses “Career change” in the three crises. Its regret is what is missing for the goal: up to 12'474 CHF.",
                      "It keeps the goal in all four worlds, and with no shock it simply follows the plan.",
                      "“Safety” decides a year earlier, before the master's starts.", "misses the goal by 789 to 8'329 CHF"):
            self.assertIn(words, FLAT)
        # The thresholds tried on crises they were not fitted on.
        drawn = self.policies["validation"]["random"]
        self.assertEqual((drawn["draws"], drawn["kept"], drawn["clairvoyant_kept"]), (200, {"securite": 163, "equilibre": 169, "ambition": 112}, 200))
        self.assertEqual({len(policy["leave_one_out"]) for policy in self.policies["policies"] if policy["rule"]}, {4})
        self.assertIn("200 crises drawn at random with a fixed seed. On those 200, “Balance” keeps the goal in 169, “Safety” in 163 and “Ambition” in 112, "
                      "where the clairvoyant keeps it in all 200.", FLAT)

    def test_two_long_unemployment_spells_in_a_row_cost_far_more_than_their_sum(self):
        calm = live(WORK, "reference")
        names = {door["key"]: door["name"] for door in self.route["doors"]}
        gap = lambda world: round(live(WORK, world).net_worth_end_chf - calm.net_worth_end_chf, 2)
        lost = lambda world: [names[key] for key, held in doors_of(live(WORK, world), TH, AGE0).items() if doors_of(calm, TH, AGE0)[key] and not held]
        first, second, both = "chomage_long@23", "chomage_long@24", "chomage_long@23+chomage_long@24"
        self.assertEqual((gap(first), gap(second), round(gap(first) + gap(second), 2), gap(both)), (-15001.97, -15111.56, -30113.53, -64427.29))
        self.assertIn(f"## Two crises in a row: {cents(gap(both))} CHF, against {cents(round(gap(first) + gap(second), 2))} for their sum", PAGE)
        for line in (f"| Long unemployment at 23 | {cents(gap(first))} CHF | {len(lost(first))}: {', '.join(lost(first))} |",
                     f"| Long unemployment at 24 | {cents(gap(second))} CHF | {len(lost(second))}: {', '.join(lost(second))} |",
                     f"| The sum of the two | {cents(round(gap(first) + gap(second), 2))} CHF | |",
                     f"| **Both in the same world** | **{cents(gap(both))} CHF** | **{len(lost(both))}: {', '.join(lost(both))}** |"):
            self.assertIn(line, PAGE)
        self.assertEqual((len(lost(first)), len(lost(both))), (1, 4))
        # The reason, as the ledger of the second year writes it: eleven months with no benefit, one contributed month less each time.
        refused = [(month.month, flow.label) for month in live(WORK, both).months for flow in month.flows if flow.label.startswith("Pas d'indemnité")]
        self.assertEqual([month for month, _ in refused], list(range(49, 60)))
        with i18n.use("en"):
            notes = [i18n.ledger(label) for _, label in refused]
        self.assertEqual([int(re.search(r"(\d+) months contributed out of 24, 12 are required", note).group(1)) for note in notes], list(range(11, 0, -1)))
        self.assertIn(f"For eleven months of the second year, a line says so: “{notes[0]}”, then 10, then 9, down to 1.", FLAT)
        self.assertEqual([live(WORK, world).months[49].flows[0].label.startswith("Pas d'indemnité") for world in (first, second)], [False, False])
        # And the other way: a long unemployment, then a market crash, cost less than their sum.
        alone, together = round(gap("chomage_long@24") + gap("krach@25"), 2), gap("chomage_long@24+krach@25")
        self.assertIn(f"costs {cents(-together)} CHF, which is {cents(round(together - alone, 2))} CHF less than the sum of the two taken alone", FLAT)

    def test_the_routes_the_page_names_are_served(self):
        for route in ("/path", "/node", "/pathways", "/policies", "/worlds", "/ai/stress", "/ai/ask"):
            self.assertIn(f"`{route}`", PAGE)
            self.assertIn(route, self.served)


class HowItIsVerified(unittest.TestCase):
    def test_the_number_of_tests_is_the_number_of_tests(self):
        counted = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT / "tests")).countTestCases()
        self.assertIn(f"- **{counted} tests**, run by `unittest` and by `pytest`", PAGE)
        self.assertIn(f"# the {counted} tests; .venv/bin/python -m pytest runs the same set", PAGE)

    def test_the_reference_model_and_the_catalogue(self):
        kit = ROOT / "starter-kit"
        months = json.loads((kit / "sample_profile.json").read_text(encoding="utf-8"))["horizon_months"]
        scenarios = json.loads((kit / "scenario_config.json").read_text(encoding="utf-8"))["scenarios"]
        self.assertEqual((months, len(scenarios)), (120, 3))
        self.assertIn("Doors gives the same 120 monthly balances, to the cent, on its three scenarios", FLAT)
        covered = [row["fidelity"] for row in json.loads((ROOT / "reports/coverage.json").read_text(encoding="utf-8"))]
        self.assertEqual((len(covered), covered.count("modelise"), covered.count("approxime"), covered.count("non_couvert")), (120, 56, 42, 22))
        self.assertIn("**The challenge's catalogue of 120 scenarios**: 98 run (56 modelled, 42 approximated, with the approximation written down) and 22 are not covered",
                      FLAT)


class TheAiLayerAsItStands(unittest.TestCase):
    def test_the_budget_and_the_space_of_the_search(self):
        tree = Tree(ALEXIA)
        th = tree.theta(None)
        self.assertEqual((stressing.CALLS, stressing.PER_CALL, V.size(th, tree.h, tree.age0), len(V.singles(th, tree.h, tree.age0)), MODEL),
                         (5, 8, 49140, 315, "claude-sonnet-5-5"))
        for words in ("5 calls of 8 worlds, so 40 worlds out of 49'140", "simulating the 315 single crises on its own", "After three refusals",
                      "the server calls Claude Sonnet 5.5 through the Anthropic API: it takes both `DOORS_AI=live` and a key"):
            self.assertIn(words, FLAT)

    def test_the_true_answer_and_the_yardstick_are_the_ones_of_the_files(self):
        truth = json.loads((ROOT / "benchmarks/truth.json").read_text(encoding="utf-8"))
        chance = json.loads((ROOT / "benchmarks/random.json").read_text(encoding="utf-8"))
        self.assertEqual(list(truth["routes"]), list(ROUTES))
        for key, label in ROUTES.items():
            scanned, drawn = truth["routes"][key], chance["routes"][key]
            self.assertEqual((drawn["budget"], drawn["space"], scanned["worlds"]), (40, 49140, 49140))
            line = (f"| {label} | {scanned['calm']['goals_kept']} goals of {scanned['calm']['goals_total']} | "
                    f"{scanned['max_goals_lost']} goals lost, in {scanned['hardest_count']} worlds of {whole(scanned['worlds'])} | "
                    f"finds one in {drawn['found']} draws of {whole(drawn['repetitions'])} ({drawn['exact_share']:.2%} of all possible draws) | not measured yet |")
            with self.subTest(route=key):
                self.assertIn(line, PAGE)

    def test_the_page_says_that_no_real_model_was_run_for_as_long_as_none_was(self):
        """The day answers of the model are recorded, or the agent is run, these sentences are no longer true: this test
        then fails until the page says what was measured."""
        measured = bool(recordings.every()) or benchmark.AGENT.exists()
        for words in ("written and tested, and has not yet been evaluated with a real model", "No answer is recorded yet",
                      "The last column is empty on purpose.", "**The AI layer is not yet evaluated with a real model**"):
            with self.subTest(words=words):
                self.assertEqual(words in FLAT, not measured)
        self.assertEqual(PAGE.count("| not measured yet |"), 0 if measured else 3)


if __name__ == "__main__":
    unittest.main()
