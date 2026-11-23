"""Without Google Chrome, the tests that read the page in a browser are skipped, and everything else goes on.

A machine with no Chrome, such as a runner of the continuous integration that lacks one, or the computer of someone
who has just cloned the repository, must get green tests with some of them skipped: not errors.

Here the browser is hidden for real. CHROME_BIN points nowhere, and the tests that need the browser run in a process
of their own, once with unittest and once with pytest. Every one of them must be skipped, with the reason written next
to it. The rest of this file tests how the browser is found, and the script that makes the picture of the README, which
asks for the same browser, and for Pillow, which the project does not.
"""
from __future__ import annotations

import offline  # noqa: F401  the recorded mode, and no client of the SDK: before anything else

import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import browser

ROOT = Path(__file__).resolve().parents[1]
# The tests that need the browser: three classes, and the whole module of the screen of the AI layer.
NEEDING = ("test_web.InChrome", "test_english.PageInChrome", "test_combined.ThePage", "test_ai_screen")
NOWHERE = str(Path(tempfile.gettempdir()) / "no-chrome-here" / "chrome")


def the_script():
    """scripts/demo_gif.py, loaded as a module: it makes the picture of the README."""
    spec = importlib.util.spec_from_file_location("demo_gif", ROOT / "scripts/demo_gif.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TheSearch(unittest.TestCase):
    def test_the_browser_named_by_chrome_bin_is_the_one_used_even_when_others_are_installed(self):
        which = {"google-chrome": "/usr/bin/google-chrome", "mine": "/opt/mine/chrome", "/opt/mine/chrome": "/opt/mine/chrome"}.get
        self.assertEqual(browser.find({"CHROME_BIN": "mine"}, which), "/opt/mine/chrome")                 # a command
        self.assertEqual(browser.find({"CHROME_BIN": "/opt/mine/chrome"}, which), "/opt/mine/chrome")     # a path
        self.assertIsNone(browser.find({"CHROME_BIN": NOWHERE}, which))                                   # leads nowhere: no browser, though one is installed
        self.assertEqual(browser.find({"CHROME_BIN": ""}, which), "/usr/bin/google-chrome")              # empty is not set

    def test_the_usual_places_are_looked_at_in_order(self):
        installed = lambda *names: {name: f"/found/{number}" for number, name in enumerate(names)}.get
        self.assertEqual(browser.find({}, installed(*browser.USUAL)), "/found/0")                         # macOS first
        self.assertEqual(browser.find({}, installed("chromium", "google-chrome-stable")), "/found/1")     # Chrome before Chromium
        self.assertEqual(browser.find({}, installed("chromium-browser")), "/found/0")
        self.assertIsNone(browser.find({}, installed()))
        self.assertEqual(browser.USUAL[0], "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        self.assertEqual(set(browser.USUAL[1:]), {"google-chrome", "google-chrome-stable", "chromium", "chromium-browser"})

    def test_the_command_starts_the_browser_without_a_window_with_the_flags_of_the_environment_first(self):
        with mock.patch.object(browser, "CHROME", "/x/chrome"), mock.patch.dict(os.environ):
            os.environ.pop("CHROME_ARGS", None)
            self.assertEqual(browser.command("--dump-dom", "http://127.0.0.1:1/"), ["/x/chrome", "--headless=new", "--dump-dom", "http://127.0.0.1:1/"])
            os.environ["CHROME_ARGS"] = "--no-sandbox --disable-dev-shm-usage"
            self.assertEqual(browser.command("--dump-dom"), ["/x/chrome", "--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--dump-dom"])

    def test_a_test_that_reaches_the_command_with_no_browser_fails_loudly(self):
        with mock.patch.object(browser, "CHROME", None), self.assertRaises(AssertionError):
            browser.command("--dump-dom")

    def test_the_reason_of_a_skip_says_which_browser_is_missing_and_how_to_name_it(self):
        self.assertEqual((browser.WHY.count("Google Chrome"), browser.WHY.count("CHROME_BIN")), (1, 1))


class WithoutChrome(unittest.TestCase):
    """The tests that need the browser, run in a process of their own with the browser hidden."""

    @classmethod
    def setUpClass(cls):
        cls.expected = unittest.defaultTestLoader.loadTestsFromNames(NEEDING).countTestCases()
        cls.environment = {**{name: value for name, value in os.environ.items() if name not in ("ANTHROPIC_API_KEY", "CHROME_ARGS")},
                           "CHROME_BIN": NOWHERE, "DOORS_AI": "recorded", "PYTHONDONTWRITEBYTECODE": "1",
                           "PYTHONPATH": os.pathsep.join([str(ROOT), str(ROOT / "tests")])}

    def in_a_process(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, *arguments], cwd=ROOT, env=self.environment, capture_output=True, text=True, timeout=300)

    def test_each_of_the_four_places_has_tests_that_need_the_browser(self):
        counts = {name: unittest.defaultTestLoader.loadTestsFromName(name).countTestCases() for name in NEEDING}
        self.assertTrue(all(counts.values()), counts)
        self.assertEqual(sum(counts.values()), self.expected)

    def test_with_unittest_every_one_of_them_is_skipped_with_its_reason(self):
        done = self.in_a_process("-m", "unittest", "-v", *NEEDING)
        self.assertEqual(done.returncode, 0, done.stderr[-1500:])
        listed = [line for line in done.stderr.splitlines() if " ... " in line]
        self.assertEqual(len(listed), self.expected, done.stderr[-1500:])
        for line in listed:
            with self.subTest(line=line[:100]):
                self.assertRegex(line, r" \.\.\. skipped '[^']*Chrome[^']*'$")
        self.assertRegex(done.stderr, rf"\nOK \(skipped={self.expected}\)\n")

    def test_with_pytest_the_same_tests_are_all_skipped(self):
        done = self.in_a_process("-m", "pytest", "-q", "-p", "no:cacheprovider", "-rs", "tests/test_web.py::InChrome", "tests/test_english.py::PageInChrome",
                                 "tests/test_combined.py::ThePage", "tests/test_ai_screen.py")
        self.assertEqual(done.returncode, 0, done.stdout[-1500:])
        self.assertRegex(done.stdout, rf"\n{self.expected} skipped in [\d.]+s")
        self.assertNotRegex(done.stdout, r"\d+ (passed|failed|errors?)\b")
        reasons = [line for line in done.stdout.splitlines() if line.startswith("SKIPPED")]
        self.assertTrue(reasons and all("Chrome" in line for line in reasons), reasons)


class TheScriptOfThePicture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = the_script()

    def test_it_looks_for_the_browser_where_the_tests_do(self):
        self.assertEqual(self.script.USUAL, browser.USUAL)
        for named in (sys.executable, NOWHERE, None):
            with self.subTest(CHROME_BIN=named), mock.patch.dict(os.environ):
                os.environ.pop("CHROME_BIN", None)
                if named:
                    os.environ["CHROME_BIN"] = named
                expected = browser.find()
                if expected is None:
                    with self.assertRaises(SystemExit):
                        self.script.chrome()
                else:
                    self.assertEqual(self.script.chrome(), expected)
        with mock.patch.dict(os.environ, {"CHROME_BIN": sys.executable}):
            self.assertEqual((self.script.chrome(), browser.find()), (sys.executable, sys.executable))

    def test_without_pillow_it_stops_before_it_starts_a_server_or_a_browser_and_says_how_to_install_it(self):
        out = Path(tempfile.gettempdir()) / "never-written-demo.gif"
        with mock.patch.dict(sys.modules, {"PIL": None}), mock.patch.object(self.script, "serve", side_effect=AssertionError("a server was started")), \
                mock.patch.object(self.script.subprocess, "run", side_effect=AssertionError("a browser was started")), self.assertRaises(SystemExit) as stopped:
            self.script.main(["--out", str(out)])
        said = " ".join(str(stopped.exception.code).split())
        for words in ("Pillow is needed to put the pictures together, and it is not one of the project's dependencies.",
                      "`.venv/bin/pip install pillow`", "`pip install --target some/folder pillow`", "PYTHONPATH=some/folder"):
            self.assertIn(words, said)
        self.assertFalse(out.exists())

    def test_pillow_is_not_a_dependency_of_the_project_and_the_docstring_says_so_and_how_to_install_it(self):
        self.assertNotIn("pillow", (ROOT / "requirements.txt").read_text(encoding="utf-8").lower())
        documented = " ".join(self.script.__doc__.split())
        for words in ("Pillow, which is NOT one of the project's dependencies: requirements.txt does not list it, and nothing but this script imports it.",
                      "Install it where the script runs: .venv/bin/pip install pillow",
                      "install it in a folder of its own and point the script to it: .venv/bin/pip install --target some/folder pillow "
                      "PYTHONPATH=some/folder .venv/bin/python scripts/demo_gif.py",
                      "Without Pillow the script stops at once, before it starts a server or a browser, and says so.",
                      "Google Chrome or Chromium. CHROME_BIN names the browser when it is not in one of the usual places."):
            self.assertIn(words, documented)
        skipped = {".venv", ".git", "__pycache__", ".pytest_cache"}
        importing = sorted(str(file.relative_to(ROOT)) for file in ROOT.rglob("*.py")
                           if not skipped & set(file.relative_to(ROOT).parts) and re.search(r"^\s*(?:from|import) PIL\b", file.read_text(encoding="utf-8"), re.MULTILINE))
        self.assertEqual(importing, ["scripts/demo_gif.py"])


if __name__ == "__main__":
    unittest.main()
