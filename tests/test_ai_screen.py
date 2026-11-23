"""The screen of the AI layer: the row of the route bar and the two sheets (web/ask.js, web/stress.js), as Chrome shows
them. No model is called: the recorded answers of these tests are made by a stand-in, in a folder of their own.

What is checked: the state with nothing recorded is said plainly and still shows what the engine finds on its own;
every answer says where it comes from; a text of the model is shown with its verified figures or not at all; nothing
is computed before “Compute”; and what the page shows is what the server gave.
"""
from __future__ import annotations

import offline  # noqa: F401  the recorded mode, and no client of the SDK: before anything else

import contextlib
import html
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import quote

from ai import benchmark, recordings, service
from ai import stress as stressing
from engine import tree
from engine.blocks import normalize
from engine.simulate import load_scenario
from engine.tree import Tree

import understudy

try:
    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
    from api.main import app
except ImportError:  # pragma: no cover
    uvicorn = None

try:
    import test_english
except ImportError:  # pragma: no cover
    test_english = None

ROOT = Path(__file__).resolve().parents[1]
ALEXIA = load_scenario(ROOT / "engine/scenarios/alexia.json")
TREE = Tree(ALEXIA)
STORY = normalize(benchmark.ROUTES["story_a"], ALEXIA.horizon_months)
CHROME = next((p for p in ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                           shutil.which("google-chrome") or "", shutil.which("chromium") or ""] if p and Path(p).exists()), None)
SHAPED = "sk-" + "ant-" + "api03-" + "k" * 60          # the shape of a key, put together here: it is not one
EN, FR = understudy.SENTENCES["en"], understudy.SENTENCES["fr"]
LABEL = "Recorded answer · claude-sonnet-5-5 · 2026-11-23"
RECORDED_MODE = "Recorded mode: no request leaves this machine. The live mode takes DOORS_AI=live and a key (ANTHROPIC_API_KEY) on the server."


HIDDEN = re.compile(r'<(\w+)\b[^>]*\shidden=""[^>]*>.*?</\1>', re.DOTALL)


def text(fragment: str) -> str:
    """What a reader sees of a piece of the page: its words, without its tags and without what the page hides."""
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", HIDDEN.sub(" ", fragment)))).strip()


def sheet(dom: str, name: str) -> str:
    """What a sheet holds, as HTML. A closed sheet holds nothing."""
    return re.search(rf'<dialog class="sheet[^"]*" id="{name}-sheet"[^>]*>(.*?)</dialog>', dom, re.DOTALL).group(1)


# A page of these tests only, never served by Doors itself: it loads the real page in a frame and does there what a test
# asks, as a reader would with a mouse and a keyboard. Then it writes what the page has become where the test reads it,
# with the state of each field (ticked or not, the value typed) written as the reader sees it.
# It waits in real time, one answer of the server after another: Chrome runs these pages on a clock of its own, which
# stands still while a request is pending and otherwise runs ahead of the frames of the browser. One short timer in each
# round lets the timers of the page run too.
DRIVER = """<!doctype html>
<meta charset="utf-8">
<title>The driver of the tests</title>
<body>
<iframe id="page" width="1440" height="900"></iframe>
<textarea id="dump"></textarea>
<script>
const params = new URLSearchParams(location.search), frame = document.getElementById('page');
const pause = async (rounds = 1) => {
  for (let round = 0; round < rounds; round += 1) {
    await fetch('/driver/tick');
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
};
const until = async (test) => {
  for (let round = 0; round < 400; round += 1) {
    if (test()) return;
    await pause();
  }
  throw new Error(`waited in vain for ${test}`);
};
frame.src = params.get('page');
(async () => {
  try {
    await until(() => frame.contentDocument?.body?.dataset.ready === '1');
    const doc = frame.contentDocument, $ = (selector) => doc.querySelector(selector);
    const type = (selector, value) => {
      $(selector).value = value;
      $(selector).dispatchEvent(new frame.contentWindow.Event('input', { bubbles: true }));
    };
    const closed = (name) => until(() => !$(`#${name}-sheet`).open && !(name in doc.body.dataset));
    const act = new (Object.getPrototypeOf(async () => {}).constructor)('doc', '$', 'type', 'until', 'closed', 'pause', params.get('act'));
    await act(doc, $, type, until, closed, pause);
    doc.querySelectorAll('input').forEach((input) => {
      if (input.type === 'checkbox' || input.type === 'radio') input.toggleAttribute('checked', input.checked);
      else input.setAttribute('value', input.value);
    });
    document.getElementById('dump').textContent = doc.documentElement.outerHTML;
    document.body.dataset.done = '1';
  } catch (error) {
    document.body.dataset.done = `no: ${error.message}`;
  }
})();
</script>
"""


OPEN_DRAWER = """
        $('#drawer-open').click();
        await until(() => $('.assumption[data-key="loyer"]'));"""
# The route cannot be computed any more: the server no longer answers that one request.
BROKEN = """
        const page = doc.defaultView, real = page.fetch;
        page.fetch = (address, ...rest) => (String(address).startsWith('/path?') ? Promise.reject(new TypeError('down')) : real(address, ...rest));
        $('#ask-compute').click();
        await until(() => $('#status').textContent);"""
# The server answers again. She closes the sheet and looks at two other worlds, one after the other: the second look
# draws the route as the engine computed it for the first, so what the page then shows is what it last asked for.
NEXT = """
        let pending = 0;
        page.fetch = async (...asked) => {
          pending += 1;
          try {
            const answer = await real(...asked);
            await answer.clone().text();
            return answer;
          } finally {
            pending -= 1;
          }
        };
        $('#ask-cancel').click();
        await closed('ask');
        for (const type of ['chomage_6_mois', 'krach']) {
          $(`.pill[data-world^="${type}"]`).click();
          await until(() => pending === 0);
          await pause(3);
        }"""
RETURN = "rendement_placements_annuel"          # the key of the return on investments, among the engine's assumptions


swiss = tree._chf          # an amount as the engine writes it in its sentences, and so as the page writes it: 27'281 CHF


def row_of(seen: dict, world: str = "reference") -> str:
    """The line of a world in the card of the route, with the engine's figures: stations open, peak financing, net worth at the end."""
    row = seen["by_world"][world]
    return f"{row['doors_open']} / {row['doors_total']} {swiss(row['peak_financing_chf'])} {swiss(row['net_worth_end_chf'])}"


def assumption(dom: str, key: str) -> tuple[bool, str]:
    """How the drawer shows an assumption: whether it is marked as changed, and the value in its field."""
    found = re.search(rf'<div class="assumption( modified)?" data-key="{key}"><label><span>[^<]*</span><span class="field">'
                      rf'<input type="number" step="any" class="num" data-key="{key}" value="([^"]*)">', dom)
    return bool(found.group(1)), found.group(2)


def pills(dom: str) -> list[tuple[str, str]]:
    """The worlds of the bar, each with whether it is the one shown."""
    return re.findall(r'<button type="button" class="pill" data-world="([^"]+)" aria-pressed="(true|false)">', dom)


def marker(dom: str, name: str) -> str | None:
    """A marker the page leaves on itself for whoever reads it: data-world, data-ask, data-stress…"""
    found = re.search(rf'<body[^>]*\bdata-{name}="([^"]*)"', dom)
    return html.unescape(found.group(1)) if found else None


FOLDERS: dict[str, Path] = {}


def setUpModule():
    """The folders of recordings these pages are read with, made once by the stand-in:
    none      nothing recorded;
    all       what the recording script would record, with one text refused once by the checker, then written again;
    rejected  a stress test whose first explanation the checker refuses every time;
    weak      a search that looks in the wrong place: the engine's own check finds harder;
    severe    a search that finds as hard as the hardest single crisis, with a crisis more severe than needed;
    mixed     one sentence with a route, a crisis, an assumption and savings."""
    if uvicorn is None or CHROME is None:
        return
    root = Path(tempfile.mkdtemp(prefix="doors-screen-"))
    FOLDERS.update({name: root / name for name in ("none", "all", "rejected", "weak", "severe", "mixed")})
    understudy.record_all(Tree(ALEXIA), FOLDERS["all"], slips=1)
    understudy.record(Tree(ALEXIA), "stress", "en", slips=3, folder=FOLDERS["rejected"])
    for lang in ("en", "fr"):
        understudy.record(Tree(ALEXIA), "stress", lang, folder=FOLDERS["weak"], worlds=understudy.MILD)
    understudy.record(Tree(ALEXIA), "stress", "en", folder=FOLDERS["severe"], worlds=["chomage_long@27~150"] + understudy.MILD[1:])
    understudy.record(Tree(ALEXIA), "ask", "en", understudy.MIXED["en"], folder=FOLDERS["mixed"])


def tearDownModule():
    if FOLDERS:
        shutil.rmtree(FOLDERS["none"].parent, ignore_errors=True)
        FOLDERS.clear()
    service._hour.times.clear()         # nothing of these pages stays in the memory of the service
    service._played.clear()
    recordings._read.clear()


@unittest.skipIf(uvicorn is None or CHROME is None, "FastAPI and Chrome are needed to read the page")
class Screen(unittest.TestCase):
    """One server for all the pages of a class, in a thread of this process."""
    folders = FOLDERS

    @classmethod
    def application(cls):
        """What the server of the class serves: Doors, as it is."""
        return app

    @classmethod
    def setUpClass(cls):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            cls.port = probe.getsockname()[1]
        cls.server = uvicorn.Server(uvicorn.Config(cls.application(), host="127.0.0.1", port=cls.port, log_level="error"))
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        for _ in range(200):
            if cls.server.started:
                break
            time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=5)

    def chrome(self, address: str, recorded: str | None, **environment) -> str:
        """The document Chrome ends with at an address of the server, with one of the folders of recordings. `recorded`
        None: the folder of the repository itself. `environment`: what the server finds in its environment; a name
        given as None is one it does not find."""
        folder = mock.patch.object(recordings, "DIR", self.folders[recorded]) if recorded else contextlib.nullcontext()
        with folder, mock.patch.dict(os.environ, {"DOORS_AI": "recorded", **{name: value for name, value in environment.items() if value is not None}}):
            for name in (name for name, value in environment.items() if value is None):
                os.environ.pop(name, None)
            dom = subprocess.run([CHROME, "--headless=new", "--window-size=1440,900", "--virtual-time-budget=12000", "--dump-dom",
                                  f"http://127.0.0.1:{self.port}/{address}"], capture_output=True, text=True, timeout=120).stdout
        self.assertNotIn(SHAPED, dom)
        return dom

    def page(self, query: str = "", recorded: str | None = "all", **environment) -> str:
        """The document Chrome shows at an address of Doors. `environment`: for the mode."""
        dom = self.chrome(query, recorded, **environment)
        self.assertEqual(marker(dom, "ready"), "1", f"the page did not start: {query}")
        return dom

    def served(self, call, recorded: str = "all"):
        """What the server answers, asked directly, with the same folder of recordings."""
        with mock.patch.object(recordings, "DIR", self.folders[recorded]), mock.patch.dict(os.environ, {"DOORS_AI": "recorded"}):
            return call()


class TheRow(Screen):
    def test_with_nothing_recorded_the_row_says_so_and_both_functions_are_there(self):
        dom = self.page(recorded="none")
        row = re.search(r'<div class="trip-row ai-row" id="ai-row">(.*?)</div>', dom, re.DOTALL).group(1)
        self.assertEqual(text(row), "Ask in your own words Read it No answer recorded yet Find what breaks my plan")
        self.assertIn('placeholder="What if I lost my job for 9 months at 27?"', row)
        self.assertIn('aria-label="One sentence about your route, a crisis, an assumption or your savings"', row)
        self.assertIn('maxlength="400"', row)
        self.assertRegex(row, r'<button type="button" class="link" id="ask-recorded" hidden="">')
        self.assertIn(f'<span class="mode" id="ai-mode" title="{html.escape(RECORDED_MODE)}">No answer recorded yet</span>', row)
        self.assertEqual((marker(dom, "ai"), marker(dom, "ask"), marker(dom, "stress")), ("none", None, None))
        self.assertEqual((sheet(dom, "ask"), sheet(dom, "stress")), ("", ""))                 # neither sheet opens by itself
        french = self.page("?lang=fr", recorded="none")
        row = re.search(r'<div class="trip-row ai-row" id="ai-row">(.*?)</div>', french, re.DOTALL).group(1)
        self.assertEqual(text(row), "Demande avec tes mots Lire Aucune réponse enregistrée pour l’instant Trouver ce qui casse mon plan")
        self.assertIn('placeholder="Et si je perdais mon emploi pendant 9 mois à 27 ans ?"', row)

    def test_the_page_of_the_repository_says_what_its_own_folder_of_recordings_holds(self):
        """With ai/recorded/ as it is in the repository, and not a folder of these tests: nothing there today, real
        answers of the model once they are recorded."""
        dom = self.page(recorded=None)
        held = recordings.listing("alexia")
        here = [each for kind in ("ask", "stress") for each in held[kind] if (each["language"], each["path"], each["assumptions"]) == ("en", STORY, {})]
        words = "Recorded answers" if here else "No answer recorded for this route" if held["ask"] or held["stress"] else "No answer recorded yet"
        self.assertEqual(marker(dom, "ai"), "recorded" if here else "none")
        self.assertIn(f">{words}</span>", dom)
        if not here:                        # and the stress test then shows what the engine finds on its own, and says it is not an answer
            shown = text(sheet(self.page("?stress=1", recorded=None), "stress"))
            self.assertIn("No answer of the model to show", shown)
            self.assertIn("What the engine finds on its own This is not an answer of the model: only the engine ran.", shown)

    def test_with_recorded_answers_the_row_offers_their_sentences_for_the_route_on_screen_only(self):
        dom = self.page()
        row = re.search(r'<div class="trip-row ai-row" id="ai-row">(.*?)</div>', dom, re.DOTALL).group(1)
        self.assertEqual(text(row), "Ask in your own words Read it 7 recorded sentences Recorded answers Find what breaks my plan")
        self.assertEqual(marker(dom, "ai"), "recorded")
        self.assertNotIn('id="ask-recorded" hidden', row)
        french = self.page("?lang=fr")
        self.assertIn("7 phrases enregistrées", french)
        self.assertIn(">Réponses enregistrées</span>", french)
        # Another route, or another assumption: the recordings are not answers to it, and the row says so.
        for query in ("?trajet=emploi", "?hyp=loyer:1500"):
            other = self.page(query)
            row = re.search(r'<div class="trip-row ai-row" id="ai-row">(.*?)</div>', other, re.DOTALL).group(1)
            with self.subTest(query=query):
                self.assertEqual(text(row), "Ask in your own words Read it No answer recorded for this route Find what breaks my plan")
                self.assertEqual(marker(other, "ai"), "none")


class TheLiveMode(Screen):
    """The live mode as the page shows it. The model is a stand-in and the key a text with the shape of one: `page`
    refuses any document that holds it."""

    def live(self, query: str = "", sentence: str | None = None, recorded: str = "all", **environment) -> str:
        service._hour.times.clear()
        with mock.patch.object(service, "live_model", lambda: understudy.Understudy(Tree(ALEXIA), "en", sentence)):
            return self.page(query, recorded, DOORS_AI="live", ANTHROPIC_API_KEY=SHAPED, **environment)

    def test_in_live_mode_the_row_names_the_model_and_each_answer_says_it_is_live(self):
        dom = self.live("?stress=1")
        row = re.search(r'<div class="trip-row ai-row" id="ai-row">(.*?)</div>', dom, re.DOTALL).group(1)
        self.assertEqual(text(row), "Ask in your own words Read it Live · claude-sonnet-5-5 Find what breaks my plan")
        self.assertIn('title="Live mode: the model (claude-sonnet-5-5) is called for each request."', row)
        self.assertEqual((marker(dom, "ai"), marker(dom, "stress")), ("live", "answer"))
        self.assertTrue(text(sheet(dom, "stress")).startswith("What breaks this route Close Live answer · claude-sonnet-5-5 The model proposes and writes."))
        # A sentence is read by the model, whatever is recorded: no list of recorded sentences in this mode.
        dom = self.live(f"?ask={quote(EN[0])}", EN[0], recorded="none")
        self.assertTrue(text(sheet(dom, "ask")).startswith(f"Ask in your own words Close “{EN[0]}” Live answer · claude-sonnet-5-5 The model proposes and writes."))
        self.assertIn("Crisis Six months of unemployment at 27, severity 150%", text(sheet(dom, "ask")))
        empty = self.live("?ask=")
        self.assertEqual(marker(empty, "ask"), "answer")
        self.assertIn("Write a sentence: what would you like to try?", text(sheet(empty, "ask")))
        self.assertNotIn('class="pill pick"', empty)

    def test_a_key_alone_or_doors_ai_alone_is_not_the_live_mode(self):
        # A key exported in the terminal of the server, and nothing else: the page stays on recorded answers, and nothing is spent.
        alone = self.page("?stress=1", ANTHROPIC_API_KEY=SHAPED, DOORS_AI=None)
        self.assertEqual((marker(alone, "ai"), marker(alone, "stress")), ("recorded", "answer"))
        self.assertIn(f'<p class="source">{LABEL}</p>', sheet(alone, "stress"))
        self.assertIn(f'title="{html.escape(RECORDED_MODE)}">Recorded answers</span>', alone)
        # DOORS_AI=live with no key: recorded too, and the row says what is missing.
        asked = self.page(DOORS_AI="live", ANTHROPIC_API_KEY=None)
        self.assertEqual(marker(asked, "ai"), "recorded")
        self.assertIn('title="Recorded mode: DOORS_AI=live is set, but the server has no key (ANTHROPIC_API_KEY).">Recorded answers</span>', asked)

    def test_past_the_hourly_limit_the_sheets_say_so_next_to_the_recorded_answer(self):
        notice = "The limit of 0 live requests per hour is reached."
        dom = self.live("?stress=1", DOORS_AI_PER_HOUR="0")
        self.assertTrue(text(sheet(dom, "stress")).startswith(f"What breaks this route Close {LABEL} {notice} The model proposes and writes."))
        dom = self.live(f"?ask={quote(EN[0])}", EN[0], DOORS_AI_PER_HOUR="0")
        self.assertTrue(text(sheet(dom, "ask")).startswith(f"Ask in your own words Close “{EN[0]}” {LABEL} {notice} The model proposes and writes."))
        # With nothing recorded either: the same sentence, and no answer.
        dom = self.live("?stress=1", recorded="none", DOORS_AI_PER_HOUR="0")
        self.assertTrue(text(sheet(dom, "stress")).startswith(f"What breaks this route Close {notice} No answer of the model to show"), text(sheet(dom, "stress"))[:200])
        self.assertEqual(marker(dom, "stress"), "none")


class WhatBreaksThisRoute(Screen):
    def test_with_nothing_recorded_the_sheet_says_so_and_shows_what_the_engine_finds_on_its_own(self):
        dom = self.page("?stress=1", recorded="none")
        shown = text(sheet(dom, "stress"))
        answer = self.served(lambda: service.stress(TREE, STORY, None, "en"), "none")
        self.assertEqual((marker(dom, "stress"), answer["available"]), ("none", False))
        self.assertTrue(shown.startswith("What breaks this route Close No answer of the model to show No recorded answer for this route with these assumptions. "
                                         "Outside the live mode, Doors plays real answers of the model again: each was recorded once, and is checked again on the "
                                         f"engine before it is shown. When there is none, nothing is made up. {RECORDED_MODE} "
                                         "To get answers: record them with scripts/record_ai.py, or start the server in live mode. "
                                         "What the engine finds on its own This is not an answer of the model: only the engine ran. "
                                         "With no crisis, this route keeps 3 of its 6 goals. A goal is a station of the map. "
                                         "The engine simulated the 315 single crises itself. The hardest make this route lose 2 goals: "
                                         "Long unemployment at 27 2 goals lost: Career change and Resilience. Show on the map "
                                         "For this route, every world with one crisis or two was simulated offline: 49'140 worlds. "
                                         "The hardest make it lose 3 goals, and there are 47 of them. The mildest of these: "
                                         "Long unemployment at 23 + long unemployment at 24 3 goals lost: Emergency savings, Career change and Resilience. Show on the map"), shown)
        # Nothing here is labelled as an answer of the model, and every world listed is one the server gave.
        for words in ("Recorded answer", "Live answer", "✓", "Explanation written by the model"):
            self.assertNotIn(words, shown)
        listed = re.findall(r'<li data-world="([^"]+)">', sheet(dom, "stress"))
        self.assertEqual(listed, [world["world"] for world in answer["engine"]["single_crises"]["hardest"]] + [world["world"] for world in answer["scan"]["hardest"]])
        french = text(sheet(self.page("?stress=1&lang=fr", recorded="none"), "stress"))
        for words in ("Ce qui casse ce trajet", "Aucune réponse du modèle à montrer", "Pas de réponse enregistrée pour ce trajet avec ces hypothèses.",
                      "Ce que le moteur trouve seul", "Ce n’est pas une réponse du modèle : seul le moteur a tourné.",
                      "Sans crise, ce trajet garde 3 de ses 6 objectifs.", "Le moteur a simulé lui-même les 315 crises seules. Les plus dures font perdre 2 objectifs à ce trajet :",
                      "Chômage long à 27 ans 2 objectifs perdus : Reconversion et Résilience. Voir sur la carte", "49'140 mondes"):
            self.assertIn(words, french)
        # A route that is not one of the benchmark: the engine's own scan of the single crises, and no full scan to cite.
        other = text(sheet(self.page("?stress=1&trajet=master", recorded="none"), "stress"))
        self.assertIn("The engine simulated the 315 single crises itself.", other)
        self.assertNotIn("was simulated offline", other)

    def test_a_recorded_answer_shows_the_engine_s_ranking_the_checked_texts_and_the_engine_s_signposts(self):
        dom = self.page("?stress=1")
        held, shown = sheet(dom, "stress"), text(sheet(dom, "stress"))
        result = self.served(lambda: service.stress(TREE, STORY, None, "en"))["result"]
        self.assertEqual(marker(dom, "stress"), "answer")
        self.assertTrue(shown.startswith(f"What breaks this route Close {LABEL} The model proposes and writes. The engine computes, ranks and checks every figure. "
                                         "The model proposed 40 worlds in 5 calls, out of 49'140 possible worlds with one crisis or two. The engine simulated each one "
                                         "and ranked them: the ranking is the engine’s, not the model’s. With no crisis, this route keeps 3 of its 6 goals."), shown[:500])
        # The worlds, in the order the engine ranked them, each with what the server gave for it.
        self.assertEqual(re.findall(r'<article class="world" data-world="([^"]+)">', held), [world["world"] for world in result["ranking"]])
        self.assertEqual([world["world"] for world in result["ranking"]][:2], ["chomage_long@23+chomage_long@24", "chomage_long@27"])
        for index, world in enumerate(result["ranking"]):
            card = text(re.search(rf'<article class="world" data-world="{re.escape(world["world"])}">(.*?)</article>', held, re.DOTALL).group(1))
            explanation = world["explanation"]
            with self.subTest(world=world["world"]):
                self.assertTrue(card.startswith(f"{world['name']} Show on the map"), card[:120])
                # Under the name, the engine's own figures for this world: its headline facts, and only those. The other
                # facts given to the model are shown where a text uses them, with the figure.
                listed = re.search(rf'<article class="world" data-world="{re.escape(world["world"])}">.*?<dl class="num">(.*?)</dl>', held, re.DOTALL).group(1)
                headline = [(fact["origin"], fact["written"]) for fact in world["facts"] if fact["headline"]]
                self.assertEqual([(html.unescape(origin), html.unescape(written)) for origin, written in re.findall(r"<dt>(.*?)</dt><dd>(.*?)</dd>", listed)], headline)
                self.assertTrue(4 <= len(headline) < len(world["facts"]), (len(headline), len(world["facts"])))
                self.assertIn(f"Explanation written by the model {explanation['text']} ✓ 3 figures verified Each figure of the text, and where the engine gave it:", card)
                for figure in explanation["figures"]:
                    self.assertIn(f"{figure['text']} {' · '.join(figure['origins'])}", card)
                # The first text was refused once by the checker and written again: the sheet says which attempt was accepted.
                self.assertIn(f"Text accepted by the checker at attempt {2 if index == 0 else 1}.", card)
                self.assertEqual(explanation["attempts"], 2 if index == 0 else 1)
                for signpost in world["signposts"]:
                    self.assertIn(signpost["text"], card)
                if not world["signposts"]:
                    self.assertIn("Signpost to watch, in the engine’s own words The engine has no signpost to watch for this world.", card)
        self.assertIn("You keep 0 of your 6 goals in this world, and you borrow up to 65'024 CHF.", shown)
        self.assertNotIn("99'999", dom)                             # the text the checker refused is nowhere on the page
        for words in ("The engine checks the search The engine simulated the 315 single crises itself. None is harder than what the search found.",
                      "The search found a world as hard as the hardest of the full scan.", "Details: the path of the search Call 1: 8 worlds simulated",
                      "The search stopped when its calls were used up.", "Tokens: 7'000 sent, 700 answered."):
            self.assertIn(words, shown)
        french = text(sheet(self.page("?stress=1&lang=fr"), "stress"))
        for words in ("Ce qui casse ce trajet Fermer Réponse enregistrée · claude-sonnet-5-5 · 2026-11-23 Le modèle propose et écrit. Le moteur calcule, classe et contrôle chaque chiffre.",
                      "Le modèle a proposé 40 mondes en 5 appels, sur 49'140 mondes possibles à une ou deux crises.",
                      "Explication écrite par le modèle Dans ce monde tu gardes 0 de tes 6 objectifs, et tu empruntes jusqu'à 65'024 CHF. ✓ 3 chiffres vérifiés",
                      "Signal à surveiller, dans les mots du moteur", "Le moteur vérifie la recherche", "La recherche a trouvé un monde aussi dur que les plus durs du balayage complet."):
            self.assertIn(words, french)

    def test_a_text_the_checker_refuses_every_time_is_not_shown_and_the_engine_s_figures_stand_alone(self):
        dom = self.page("?stress=1", recorded="rejected")
        result = self.served(lambda: service.stress(TREE, STORY, None, "en"), "rejected")["result"]
        first, second = result["ranking"][0], result["ranking"][1]
        self.assertEqual((first["explanation"]["accepted"], first["explanation"]["text"], first["explanation"]["attempts"], second["explanation"]["accepted"]),
                         (False, None, 3, True))
        card = text(re.search(rf'<article class="world" data-world="{re.escape(first["world"])}">(.*?)</article>', sheet(dom, "stress"), re.DOTALL).group(1))
        self.assertIn("AI explanation rejected by the checker The checker refused every text the model wrote for this world. Only the figures of the engine are shown.", card)
        self.assertIn("Peak borrowing in this world 65'024 CHF", card)
        for words in ("Explanation written by the model", "✓", "99'999", "You keep"):
            self.assertNotIn(words, card)
        self.assertNotIn("99'999", dom)

    def test_an_answer_recorded_for_other_assumptions_is_never_shown_in_their_place(self):
        dom = self.page("?hyp=loyer:1500&stress=1")
        answer = self.served(lambda: service.stress(TREE, STORY, {"loyer": 1500.0}, "en"))
        shown = text(sheet(dom, "stress"))
        self.assertEqual((marker(dom, "stress"), answer["available"], answer["scan"]), ("none", False, None))
        self.assertIn("No answer of the model to show No recorded answer for this route with these assumptions.", shown)
        # What the engine finds on its own is found with her assumptions: with this rent the route keeps one goal less with
        # no crisis, and other crises are the hardest. The scan made offline was made with the engine's assumptions, and is not cited.
        alone, usual = (stressing.alone(TREE, STORY, overrides, "en") for overrides in ({"loyer": 1500.0}, None))
        hardest = [world["world"] for world in alone["single_crises"]["hardest"]]
        self.assertNotEqual((alone["calm"]["goals_kept"], hardest), (usual["calm"]["goals_kept"], [world["world"] for world in usual["single_crises"]["hardest"]]))
        self.assertIn("With no crisis, this route keeps 2 of its 6 goals.", shown)
        self.assertIn("The engine simulated the 315 single crises itself. The hardest make this route lose 1 goal:", shown)
        self.assertEqual(re.findall(r'<li data-world="([^"]+)">', sheet(dom, "stress")), hardest)
        for words in ("Recorded answer", "was simulated offline"):
            self.assertNotIn(words, shown)

    def test_when_the_search_looked_in_the_wrong_place_the_engine_s_own_check_says_so(self):
        # The search only tried market crashes and inflation: what it found costs one goal.
        shown = text(sheet(self.page("?stress=1", recorded="weak"), "stress"))
        result = self.served(lambda: service.stress(TREE, STORY, None, "en"), "weak")["result"]
        single = result["verification"]["single_crises"]
        self.assertEqual([len(world["goals_lost"]) for world in result["ranking"]], [1, 1])
        self.assertEqual((single["harder_than_found"], single["max_goals_lost"], result["verification"]["benchmark"]["found"]), (True, 2, False))
        self.assertIn("The engine checks the search The engine simulated the 315 single crises itself. At least one is harder than what the search found. "
                      "The hardest make this route lose 2 goals: Long unemployment at 27 2 goals lost: Career change and Resilience. Show on the map "
                      "For this route, every world with one crisis or two was simulated offline: 49'140 worlds. The hardest make it lose 3 goals, and there are 47 of them.", shown)
        self.assertIn("The search did not find a world as hard as the hardest of the full scan.", shown)
        for words in ("None is harder than what the search found.", "The search found a world as hard"):
            self.assertNotIn(words, shown)
        french = text(sheet(self.page("?stress=1&lang=fr", recorded="weak"), "stress"))
        self.assertIn("Le moteur vérifie la recherche Le moteur a simulé lui-même les 315 crises seules. Au moins une est plus dure que ce que la recherche a trouvé. "
                      "Les plus dures font perdre 2 objectifs à ce trajet : Chômage long à 27 ans 2 objectifs perdus : Reconversion et Résilience. Voir sur la carte", french)
        self.assertIn("La recherche n’a pas trouvé de monde aussi dur que les plus durs du balayage complet.", french)
        # A search that found as hard, with a crisis more severe than it takes: the engine shows the milder world, and only that one.
        dom = self.page("?stress=1", recorded="severe")
        result = self.served(lambda: service.stress(TREE, STORY, None, "en"), "severe")["result"]
        single = result["verification"]["single_crises"]
        self.assertEqual((result["ranking"][0]["world"], single["harder_than_found"], single["as_hard_and_milder"]), ("chomage_long@27~150", False, True))
        self.assertIn("The engine checks the search The engine simulated the 315 single crises itself. One breaks as much as what the search found, and is milder: "
                      "Long unemployment at 27 2 goals lost: Career change and Resilience. Show on the map For this route, every world with one crisis or two",
                      text(sheet(dom, "stress")))

    def test_show_on_the_map_makes_the_world_the_one_shown_as_one_more_pill(self):
        dom = self.page("?stress=1&show=2")                         # the second world listed: long unemployment at 27, a crisis the bar does not hold
        self.assertEqual((marker(dom, "world"), marker(dom, "stress"), sheet(dom, "stress")), ("chomage_long@27", None, ""))
        bar = re.findall(r'<button type="button" class="pill" data-world="([^"]+)" aria-pressed="(true|false)">([^<]+)</button>', dom)
        self.assertEqual(len(bar), 8)
        self.assertEqual(bar[-1], ("chomage_long@27", "true", "Long unemployment"))
        self.assertEqual([pressed for _, pressed, _ in bar[:-1]], ["false"] * 7)
        self.assertIn('<span class="break" aria-hidden="true"></span><button type="button" class="pill" data-world="chomage_long@27"', dom)
        self.assertIn("Job lost from age 27 to age 28.", text(re.search(r'<p class="traffic-note num" id="traffic-note">(.*?)</p>', dom, re.DOTALL).group(1)))
        # Two crises: the world of the first line, shown the same way.
        both = self.page("?stress=1&show=1")
        self.assertEqual(marker(both, "world"), "chomage_long@23+chomage_long@24")
        self.assertIn('aria-pressed="true">Long unemployment at 23 + long unemployment at 24</button>', both)


class AskInYourOwnWords(Screen):
    def read(self, sentence: str, more: str = "", recorded: str = "all") -> str:
        return self.page(f"?ask={quote(sentence)}{more}", recorded)

    def test_a_sentence_is_shown_as_settings_before_anything_is_computed(self):
        dom = self.read(EN[0])
        shown = text(sheet(dom, "ask"))
        self.assertEqual(shown, f"Ask in your own words Close “{EN[0]}” {LABEL} The model proposes and writes. The engine computes, ranks and checks every figure. "
                                "Here is what I understood Nothing is computed yet. Keep, change or untick each setting, then compute. "
                                "Crisis Six months of unemployment at 27, severity 150% "
                                "You ask for 9 months: severity 150% of “Six months of unemployment”, usually 6 months. The engine builds 9 months. "
                                "Job loss for six months, for someone who has a job at that time. Job lost from age 27 to 27 years 9 months. "
                                "Compute Cancel")
        # The line said when nothing is ticked is there, and hidden: one setting is ticked.
        self.assertIn('<p class="small" id="ask-none-ticked" hidden="">Nothing is ticked: there is nothing to compute.</p>', sheet(dom, "ask"))
        self.assertIn('<input type="checkbox" name="world" checked="">', sheet(dom, "ask"))
        # Nothing has gone to the engine: the page is as it was.
        self.assertEqual((marker(dom, "ask"), marker(dom, "world"), marker(dom, "overrides"), marker(dom, "trip")),
                         ("answer", "reference", "0", "Job in Lausanne 5 years, then master's 2 years, then job in Lausanne"))
        self.assertIn('id="ask-input" autocomplete="off" spellcheck="false" placeholder="What if I lost my job for 9 months at 27?"', dom)
        french = text(sheet(self.read(FR[0], "&lang=fr"), "ask"))
        self.assertEqual(french, f"Demande avec tes mots Fermer « {FR[0]} » Réponse enregistrée · claude-sonnet-5-5 · 2026-11-23 Le modèle propose et écrit. "
                                 "Le moteur calcule, classe et contrôle chaque chiffre. Voici ce que j’ai compris Rien n’est encore calculé. Garde, modifie ou décoche "
                                 "chaque réglage, puis calcule. Crise Six mois de chômage à 27 ans, gravité 150 % "
                                 "Tu demandes 9 mois : gravité 150 % de « Six mois de chômage », d'habitude 6 mois. Le moteur construit 9 mois. "
                                 "Perte d'emploi pendant six mois, pour qui a un emploi à ce moment-là. Perte d'emploi de 27 ans à 27 ans et 9 mois. "
                                 "Calculer Annuler")

    def test_compute_hands_the_settings_to_the_engine_and_the_whole_page_follows(self):
        dom = self.read(EN[0], "&compute=1")
        self.assertEqual((marker(dom, "world"), marker(dom, "ask"), sheet(dom, "ask")), ("chomage_6_mois@27~150", None, ""))
        self.assertEqual(len(pills(dom)), 7)                        # one of the engine's own crises, resized: it takes the place of its pill
        self.assertIn('data-world="chomage_6_mois@27~150" aria-pressed="true">Six months of unemployment</button>', dom)
        self.assertIn("Job lost from age 27 to 27 years 9 months.", dom)
        # The crisis keeps its severity when its age is moved in the bar: the buttons offer 26 and 28, and the way back to 22.
        self.assertRegex(dom, r'data-age="26"[^>]*>−</button><output id="crisis-age"[^>]*>age 27</output><button type="button" class="step" data-age="28"')
        # Two crises: one more pill, on a line of its own. A route: the route on screen changes. Values and savings: the engine recomputes with them.
        two = self.read(EN[3], "&compute=1")
        self.assertEqual(marker(two, "world"), "krach@24~133+chomage_long@27")
        self.assertIn('aria-pressed="true">Market crash at 24, severity 133% + long unemployment at 27</button>', two)
        route = self.read(EN[1], "&compute=1")
        self.assertEqual((marker(route, "trip"), marker(route, "world"), marker(route, "ai")), ("Master's 2 years, then job in Lausanne", "reference", "none"))
        berlin = self.read(EN[2], "&compute=1")
        self.assertEqual(marker(berlin, "trip"), "Job in Lausanne 3 years, then job in Berlin")
        values = self.read(EN[4], "&compute=1")
        self.assertEqual((marker(values, "overrides"), marker(values, "observed"), marker(values, "trip")),
                         ("2", "72:40000", "Job in Lausanne 5 years, then master's 2 years, then job in Lausanne"))
        # The card of the route holds the engine's figures for exactly these settings, and they are not the figures of the route before.
        seen = TREE.path_view(STORY, "reference", {"loyer": 1500.0, RETURN: 0.05}, ["reference"], {"gare_month": 72, "value_chf": 40000.0})
        self.assertNotEqual(row_of(seen), row_of(TREE.path_view(STORY, "reference", None, ["reference"])))
        self.assertIn(row_of(seen), text(values))

    def test_one_sentence_may_hold_a_route_a_crisis_an_assumption_and_savings(self):
        sentence = understudy.MIXED["en"]
        held = sheet(self.read(sentence, recorded="mixed"), "ask")
        self.assertTrue(text(held).endswith(
            "Here is what I understood Nothing is computed yet. Keep, change or untick each setting, then compute. "
            "Route Master's (age 20 → age 22) → Job search (age 22 → 22 years 3 months) → Job in Lausanne (22 years 3 months → age 30) "
            "Master's: 2 years, its length in the engine. Job in Lausanne: until 30, the end of the route. "
            "Crisis Market crash at 24 Market crash at 24: you did not say the size. The engine takes its usual value. "
            "Investments fall sharply, within one month. Return on investments, per month: −30% (+0.2% in the reference world), at age 24. "
            "Rent CHF/month On screen now: 900 CHF/month. Set aside at 26 CHF Compute Cancel"), text(held))
        self.assertEqual(re.findall(r'<input type="checkbox" name="([a-z]+)"[^>]*checked="">', held), ["route", "world", "assumption", "savings"])
        dom = self.read(sentence, "&compute=1", "mixed")
        self.assertEqual((marker(dom, "trip"), marker(dom, "world"), marker(dom, "overrides"), marker(dom, "observed")),
                         ("Master's 2 years, then job in Lausanne", "krach@24", "1", "72:40000"))

    def test_a_new_route_from_a_sentence_drops_the_savings_given_on_the_route_before(self):
        # ?gare=72&epargne=40000: she has said what she really had at 26, on the route on screen.
        kept = self.page(f"?gare=72&epargne=40000&ask={quote(EN[0])}&compute=1")
        self.assertEqual((marker(kept, "observed"), marker(kept, "world")), ("72:40000", "chomage_6_mois@27~150"))     # a crisis: the same route, her savings stay
        dropped = self.page(f"?gare=72&epargne=40000&ask={quote(EN[1])}&compute=1")
        self.assertEqual((marker(dropped, "observed"), marker(dropped, "trip")), ("", "Master's 2 years, then job in Lausanne"))

    def test_an_answer_recorded_for_another_route_or_other_assumptions_is_not_the_answer_to_this_sentence(self):
        for query in ("?hyp=loyer:1500", "?trajet=emploi"):
            dom = self.page(f"{query}&ask={quote(EN[0])}")
            shown = text(sheet(dom, "ask"))
            with self.subTest(query=query):
                self.assertEqual(marker(dom, "ask"), "none")
                self.assertIn("No answer of the model to show No recorded answer for this sentence on this route.", shown)
                self.assertTrue(shown.endswith("Sentences are recorded for another route or other assumptions, not for what is on screen."), shown[-200:])
                for words in ("Recorded answer ·", "Here is what I understood", "Six months of unemployment"):
                    self.assertNotIn(words, shown)

    def test_values_can_be_changed_and_a_rate_with_no_unit_shows_both_readings(self):
        held = sheet(self.read(EN[4]), "ask")
        shown = text(held)
        for words in ("Rent CHF/month On screen now: 900 CHF/month.", "Return on investments (reference world) %/year On screen now: 3 %/year. 5% is stored as 0.05.",
                      "Set aside at 26 CHF"):
            self.assertIn(words, shown)
        fields = re.findall(r'<input type="number" step="any"([^>]*)>', held)
        self.assertEqual(len(fields), 3)
        self.assertRegex(fields[0], r'min="0" class="num" data-key="loyer" value="1500"')
        self.assertRegex(fields[1], r'min="0" max="100" class="num" data-key="[a-z_]+" value="5"')            # a rate stays between 0 and 100 percent
        self.assertRegex(fields[2], r'class="num" id="ask-savings" value="40000"')
        self.assertEqual(held.count('type="checkbox"'), 3)
        rate = sheet(self.read(understudy.RATE["en"]), "ask")
        self.assertIn("On screen now: 3 %/year. 0.05% is stored as 0.0005. To check. No unit: read as 0.05%. It could also be 5%. 0.05% 5%", text(rate))
        self.assertRegex(rate, r'<input type="radio" name="reading-[a-z_]+" value="0.05" checked="">0.05%</label>')
        self.assertRegex(rate, r'<input type="radio" name="reading-[a-z_]+" value="5">5%</label>')
        # Applied as it stands, it is the reading of the drawer: one assumption changed.
        self.assertEqual(marker(self.read(understudy.RATE["en"], "&compute=1"), "overrides"), "1")
        french = text(sheet(self.read(understudy.RATE["fr"], "&lang=fr"), "ask"))
        self.assertIn("À vérifier. Sans unité : lu comme 0,05 %. Cela pourrait aussi être 5 %.", french)

    def test_what_was_inferred_or_left_to_the_engine_is_said_next_to_the_setting(self):
        two = text(sheet(self.read(EN[3]), "ask"))
        self.assertIn("Two crises in the same world Market crash at 24, severity 133% + long unemployment at 27 "
                      "You ask for 40%: severity 133% of “Market crash”, usually 30%. The engine builds 40%. "
                      "You ask for 1 year, that is 12 months: severity 100% of “Long unemployment”, usually 12 months. The engine builds 12 months. "
                      "Long unemployment at 27: the age is not in your sentence. Check it.", two)
        route = text(sheet(self.read(EN[1]), "ask"))
        # The route as the engine builds it: the months of job search after the studies are the engine's, and they are shown.
        self.assertIn("Route Master's (age 20 → age 22) → Job search (age 22 → 22 years 3 months) → Job in Lausanne (22 years 3 months → age 30) "
                      "Master's: 2 years, its length in the engine. Job in Lausanne: until 30, the end of the route.", route)
        berlin = text(sheet(self.read(EN[2]), "ask"))
        self.assertIn("Route Job in Lausanne (age 20 → age 23) → Job in Berlin (age 23 → age 30) At 23: Move to Berlin.", berlin)

    def test_what_doors_cannot_set_is_said_with_her_words_and_no_button_to_compute(self):
        dom = self.read(EN[5])
        self.assertEqual(text(sheet(dom, "ask")), f"Ask in your own words Close “{EN[5]}” {LABEL} The model proposes and writes. The engine computes, ranks and checks "
                                                 "every figure. Nothing in this sentence that Doors can set What Doors cannot set "
                                                 "I had a child at 28 Doors has no such event. It knows studies, jobs in Lausanne or in Berlin, seven types of crisis, "
                                                 "and its assumptions. moved to London London is refused, the engine only knows the franc and the euro. Abroad means Berlin.")
        self.assertNotIn('id="ask-compute"', sheet(dom, "ask"))
        self.assertEqual(marker(dom, "ask"), "answer")

    def test_a_sentence_with_no_recorded_answer_says_so_and_offers_the_recorded_ones(self):
        dom = self.read("What if I won the lottery?")
        shown = text(sheet(dom, "ask"))
        self.assertEqual(marker(dom, "ask"), "none")
        self.assertTrue(shown.startswith("Ask in your own words Close “What if I won the lottery?” No answer of the model to show "
                                         "No recorded answer for this sentence on this route. Outside the live mode, Doors plays real answers of the model again"), shown)
        self.assertIn(f"{RECORDED_MODE} To get answers: record them with scripts/record_ai.py, or start the server in live mode. "
                      "These sentences have a recorded answer for the route on screen:", shown)
        offered = [html.unescape(sentence) for sentence in re.findall(r'<button type="button" class="pill pick" data-sentence="([^"]+)">', sheet(dom, "ask"))]
        self.assertEqual(offered, sorted(EN + [understudy.RATE["en"]]))
        for words in ("Recorded answer ·", "Here is what I understood", "Compute"):
            self.assertNotIn(words, shown)
        # The link of the row opens the same list, with no sentence.
        listed = self.page("?ask=")
        self.assertEqual((marker(listed, "ask"), text(sheet(listed, "ask")).startswith("Ask in your own words Close These sentences have a recorded answer for the route on screen:")),
                         ("list", True))
        # With nothing recorded at all: the same plain state, and no sentence to offer.
        empty = self.read("What if I lost my job?", recorded="none")
        self.assertEqual(marker(empty, "ask"), "none")
        self.assertTrue(text(sheet(empty, "ask")).endswith("To get answers: record them with scripts/record_ai.py, or start the server in live mode."))
        nothing = self.page("?ask=", recorded="none")
        self.assertIn("Nothing in this sentence that Doors can set What Doors cannot set Write a sentence: what would you like to try?", text(sheet(nothing, "ask")))


class WithHerHands(Screen):
    """What an address cannot show: she unticks a setting, types a value, picks a reading, presses a button."""

    @classmethod
    def application(cls):
        """Doors as it is, behind one more page that belongs to these tests: the driver."""
        outer = FastAPI()
        outer.add_api_route("/driver", lambda: HTMLResponse(DRIVER), methods=["GET"])
        outer.add_api_route("/driver/tick", lambda: time.sleep(0.025) or {}, methods=["GET"])       # a moment of real time
        outer.mount("/", app)
        return outer

    def after(self, query: str, act: str, recorded: str = "all") -> str:
        """The page at an address of Doors once she has done `act` there, written as the script of a page."""
        outer = self.chrome(f"driver?page={quote('/' + query, safe='')}&act={quote(act, safe='')}", recorded)
        self.assertEqual(marker(outer, "done"), "1", f"what she does did not come to its end: {act}")
        return html.unescape(re.search(r'<textarea id="dump">(.*?)</textarea>', outer, re.DOTALL).group(1))

    def read(self, sentence: str, act: str, recorded: str = "all") -> str:
        return self.after(f"?ask={quote(sentence)}", act, recorded)

    def test_what_she_unticks_stays_out_and_what_she_types_goes_to_the_engine(self):
        # The rent: unticked. The return: 7% typed over the 5% of her sentence. The savings: unticked, then ticked again by the amount she types.
        dom = self.read(EN[4], f"""
        $('.part[data-key="loyer"] input[type="checkbox"]').click();
        type('.part[data-key="{RETURN}"] input[type="number"]', '7');
        $('input[name="savings"]').click();
        type('#ask-savings', '30000');
        $('#ask-compute').click();
        await closed('ask');{OPEN_DRAWER}""")
        self.assertEqual((marker(dom, "overrides"), marker(dom, "observed"), marker(dom, "ask"), sheet(dom, "ask")), ("1", "72:30000", None, ""))
        self.assertEqual((assumption(dom, "loyer"), assumption(dom, RETURN)), ((False, "900"), (True, "7")))          # 7 %/year: 0.07 for the engine
        self.assertIn("<strong>1 value changed.</strong>", dom)
        # The route on screen is the one the engine computes with exactly these settings, and not with the ones of her sentence.
        seen = TREE.path_view(STORY, "reference", {RETURN: 0.07}, ["reference"], {"gare_month": 72, "value_chf": 30000.0})
        as_said = TREE.path_view(STORY, "reference", {"loyer": 1500.0, RETURN: 0.05}, ["reference"], {"gare_month": 72, "value_chf": 40000.0})
        self.assertNotEqual(row_of(seen), row_of(as_said))
        self.assertIn(row_of(seen), text(dom))

    def test_each_part_of_a_sentence_is_kept_or_left_out_on_its_own(self):
        sentence, story = understudy.MIXED["en"], "Job in Lausanne 5 years, then master's 2 years, then job in Lausanne"
        # The route and the crisis unticked: only the rent and the savings go to the engine.
        dom = self.read(sentence, """
        $('input[name="route"]').click();
        $('input[name="world"]').click();
        $('#ask-compute').click();
        await closed('ask');""", "mixed")
        self.assertEqual((marker(dom, "trip"), marker(dom, "world"), marker(dom, "overrides"), marker(dom, "observed"), len(pills(dom))),
                         (story, "reference", "1", "72:40000", 7))
        # The rent and the savings unticked: only the route and the crisis.
        dom = self.read(sentence, """
        $('input[name="assumption"]').click();
        $('input[name="savings"]').click();
        $('#ask-compute').click();
        await closed('ask');""", "mixed")
        self.assertEqual((marker(dom, "trip"), marker(dom, "world"), marker(dom, "overrides"), marker(dom, "observed")),
                         ("Master's 2 years, then job in Lausanne", "krach@24", "0", ""))

    def test_with_nothing_ticked_there_is_nothing_to_compute(self):
        dom = self.read(EN[0], """
        $('input[name="world"]').click();
        $('#ask-compute').click();
        await pause(8);""")
        held = sheet(dom, "ask")
        self.assertIn('<p class="small" id="ask-none-ticked">Nothing is ticked: there is nothing to compute.</p>', held)
        self.assertIn('<button type="submit" class="pill" id="ask-compute" disabled="">Compute</button>', held)
        self.assertIn('<input type="checkbox" name="world">', held)
        self.assertEqual((marker(dom, "ask"), marker(dom, "world")), ("answer", "reference"))
        # Ticked again, the setting is computed.
        again = self.read(EN[0], """
        $('input[name="world"]').click();
        $('input[name="world"]').click();
        $('#ask-compute').click();
        await closed('ask');""")
        self.assertEqual((marker(again, "world"), sheet(again, "ask")), ("chomage_6_mois@27~150", ""))

    def test_the_reading_she_picks_is_the_one_the_engine_gets(self):
        sentence = understudy.RATE["en"]
        pick = """
        $('input[type="radio"][value="5"]').click();"""
        # The reading she picks goes into the field, where she sees it before computing.
        shown = sheet(self.read(sentence, pick), "ask")
        self.assertRegex(shown, rf'<input type="number" step="any" min="0" max="100" class="num" data-key="{RETURN}" value="5" required="">')
        self.assertRegex(shown, r'<input type="radio" name="reading-[a-z_]+" value="5" checked="">5%</label>')
        picked = self.read(sentence, f"""{pick}
        $('#ask-compute').click();
        await closed('ask');{OPEN_DRAWER}""")
        left = self.after(f"?ask={quote(sentence)}&compute=1", OPEN_DRAWER)
        self.assertEqual((assumption(picked, RETURN), marker(picked, "overrides")), ((True, "5"), "1"))              # 5 %/year
        self.assertEqual((assumption(left, RETURN), marker(left, "overrides")), ((True, "0.05"), "1"))               # 0.05 %/year: the reading of the drawer
        five, drawer = (row_of(TREE.path_view(STORY, "reference", {RETURN: rate}, ["reference"])) for rate in (0.05, 0.0005))
        self.assertNotEqual(five, drawer)
        self.assertIn(five, text(picked))
        self.assertIn(drawer, text(left))
        # With 5%, the engine ends on a half franc. The page writes it as the engine does in its sentences: to the even franc.
        self.assertEqual(TREE.path_view(STORY, "reference", {RETURN: 0.05}, ["reference"])["by_world"]["reference"]["net_worth_end_chf"], 103330.5)
        self.assertIn("Net worth at 30: 103'330 CHF.", text(picked))
        self.assertNotIn("103'331", picked)

    def test_a_server_that_fails_while_computing_leaves_nothing_half_applied(self):
        before = self.page()
        # A crisis: the engine had already described the world when the route could not be computed.
        dom = self.read(EN[0], BROKEN)
        self.assertIn('The server does not answer. Run "python -m api", then reload the page.', text(dom))
        self.assertEqual((marker(dom, "world"), marker(dom, "ask"), pills(dom)), ("reference", "answer", pills(before)))
        self.assertIn("Six months of unemployment at 27, severity 150%", text(sheet(dom, "ask")))            # the sheet is still there: she can compute again
        # Values and savings: back to what they were. And when the server answers again, they are applied.
        dom = self.read(EN[4], f"""{BROKEN}
        doc.body.dataset.failed = [doc.body.dataset.overrides, doc.body.dataset.observed, doc.body.dataset.ai, $('#ask-sheet').open].join('|');
        page.fetch = real;
        $('#ask-compute').click();
        await closed('ask');{OPEN_DRAWER}""")
        self.assertEqual((marker(dom, "failed"), marker(dom, "overrides"), marker(dom, "observed"), marker(dom, "ai")),
                         ("0||recorded|true", "2", "72:40000", "none"))
        self.assertEqual((assumption(dom, "loyer"), assumption(dom, RETURN)), ((True, "1500"), (True, "5")))
        self.assertNotIn("The server does not answer.", text(dom))

    def test_after_a_computation_that_failed_the_page_goes_on_with_what_is_on_screen(self):
        """What a sentence would have set is given back whole: the worlds tested and the assumptions that go with each
        request to the engine, not only what the page shows of them."""
        worlds = [world for world, _ in pills(self.page())]
        seen = TREE.path_view(STORY, "krach", None, worlds)
        as_said = TREE.path_view(STORY, "krach", {"loyer": 1500.0, RETURN: 0.05}, worlds)
        self.assertNotEqual(row_of(seen), row_of(as_said))
        for sentence in (EN[0], EN[4]):                 # a crisis; values and savings
            dom = self.read(sentence, BROKEN + NEXT)
            shown = text(dom)
            with self.subTest(sentence=sentence):
                self.assertEqual((marker(dom, "world"), [world for world, _ in pills(dom)], marker(dom, "overrides"), marker(dom, "observed") or ""),
                                 ("krach", worlds, "0", ""))
                for world in worlds:
                    self.assertIn(row_of(seen, world), shown)
                self.assertNotIn(row_of(as_said), shown)
                self.assertNotIn("Request refused by the engine.", shown)

    def test_the_row_opens_both_sheets_and_a_world_shown_from_a_sheet_moves_in_the_bar(self):
        dom = self.after("", f"""
        type('#ask-input', {json.dumps(EN[0])});
        $('#ask-read').click();
        await until(() => doc.body.dataset.ask === 'answer');
        doc.body.dataset.read = $('#ask-sheet .said').textContent;
        $('#ask-cancel').click();
        await closed('ask');
        doc.body.dataset.cancelled = doc.body.dataset.world;
        $('#stress').click();
        await until(() => doc.body.dataset.stress === 'answer');
        doc.querySelectorAll('#stress-sheet [data-show]')[1].click();
        await closed('stress');
        doc.body.dataset.shown = doc.body.dataset.world;
        $('.step[data-age="28"]').click();
        await until(() => doc.body.dataset.world !== doc.body.dataset.shown);
        doc.body.dataset.moved = [doc.body.dataset.world, doc.querySelectorAll('.pill[data-world]').length, $('#traffic-note').textContent].join('|');
        $('#stress').click();
        await until(() => doc.body.dataset.stress === 'answer');
        doc.querySelectorAll('#stress-sheet [data-show]')[0].click();
        await closed('stress');""")
        self.assertEqual((marker(dom, "read"), marker(dom, "cancelled"), marker(dom, "shown")), (f"“{EN[0]}”", "reference", "chomage_long@27"))
        # Moved in the bar, the crisis shown from the sheet is still the one more pill.
        moved = marker(dom, "moved")
        self.assertTrue(moved.startswith("chomage_long@28|8|") and moved.endswith(" Job lost from age 28 to age 29."), moved)
        # Another world shown from the sheet takes its place: there is never more than one such pill.
        self.assertEqual((marker(dom, "world"), len(pills(dom)), pills(dom)[-1]),
                         ("chomage_long@23+chomage_long@24", 8, ("chomage_long@23+chomage_long@24", "true")))

    def test_a_sheet_closed_by_the_browser_lets_go_too_and_a_sheet_opened_again_is_left_alone(self):
        # The Escape key: the browser closes the sheet itself, and says so a moment later.
        dom = self.read(EN[0], """
        $('#ask-sheet').close();
        await closed('ask');""")
        self.assertEqual((marker(dom, "ask"), sheet(dom, "ask"), marker(dom, "world")), (None, "", "reference"))
        # Closed and read again at once: the word of the closing comes after the new reading, which is left as it is.
        dom = self.read(EN[0], """
        $('#ask-cancel').click();
        $('#ask-read').click();
        await until(() => doc.body.dataset.ask === 'answer');
        await pause(6);""")
        self.assertEqual(marker(dom, "ask"), "answer")
        self.assertIn("Crisis Six months of unemployment at 27, severity 150%", text(sheet(dom, "ask")))
        self.assertIn(' open=""', re.search(r'<dialog class="sheet[^"]*" id="ask-sheet"[^>]*>', dom).group(0))

    def test_a_crisis_keeps_its_severity_when_its_age_is_moved_in_the_bar(self):
        dom = self.after(f"?ask={quote(EN[0])}&compute=1", """
        $('.step[data-age="28"]').click();
        await until(() => doc.body.dataset.world !== 'chomage_6_mois@27~150');""")
        self.assertEqual(marker(dom, "world"), "chomage_6_mois@28~150")
        self.assertIn("Job lost from age 28 to 28 years 9 months.", text(re.search(r'<p class="traffic-note num" id="traffic-note">(.*?)</p>', dom, re.DOTALL).group(1)))

    def test_the_link_of_the_row_lists_the_recorded_sentences_and_one_click_reads_one(self):
        dom = self.after("", f"""
        $('#ask-recorded').click();
        await until(() => doc.body.dataset.ask === 'list');
        doc.body.dataset.listed = doc.querySelectorAll('#ask-sheet .pick').length;
        [...doc.querySelectorAll('#ask-sheet .pick')].find((pick) => pick.dataset.sentence === {json.dumps(EN[3])}).click();
        await until(() => doc.body.dataset.ask === 'answer');""")
        shown = text(sheet(dom, "ask"))
        self.assertEqual(marker(dom, "listed"), "7")
        self.assertTrue(shown.startswith(f"Ask in your own words Close “{EN[3]}” {LABEL}"), shown[:200])
        self.assertIn("Two crises in the same world Market crash at 24, severity 133% + long unemployment at 27", shown)
        self.assertIn(f'value="{EN[3]}"', re.search(r'<input type="text" id="ask-input"[^>]*>', dom).group(0))     # the row holds the sentence she picked
        self.assertEqual(marker(dom, "world"), "reference")                                                        # and nothing is computed
        # “Close”: the sheet keeps nothing, and nothing was computed.
        shut = self.read(EN[3], """
        $('#ask-close').click();
        await closed('ask');""")
        self.assertEqual((marker(shut, "ask"), sheet(shut, "ask"), marker(shut, "world")), (None, "", "reference"))


@unittest.skipIf(test_english is None, "the helpers of test_english are needed")
class TheWordsOfTheScreen(Screen):
    def test_in_english_the_sheets_hold_no_french_and_none_of_the_words_doors_never_writes(self):
        pages = [*(self.page("?stress=1", recorded=folder) for folder in ("all", "none", "rejected", "weak", "severe")), self.page("?ask="),
                 *(self.page(f"?ask={quote(sentence)}") for sentence in EN + [understudy.RATE["en"], "What if I won the lottery?"]),
                 self.page(f"?ask={quote(understudy.MIXED['en'])}", recorded="mixed")]
        for dom in pages:
            row = text(re.search(r'<div class="trip-row ai-row" id="ai-row">(.*?)</div>', dom, re.DOTALL).group(1))
            for words in (row, text(re.sub(r"<code>.*?</code>", " ", sheet(dom, "ask") + sheet(dom, "stress"), flags=re.DOTALL))):
                with self.subTest(words=words[:60]):
                    self.assertIsNone(test_english.FRENCH.search(words), test_english.FRENCH.search(words))
                    self.assertIsNone(test_english.BANNED.search(words), test_english.BANNED.search(words))

    def test_the_limits_of_the_ai_layer_are_in_the_drawer_in_both_languages(self):
        for lang, words in (("en", ("AI layer: the model proposes worlds or settings and writes sentences; it computes nothing.",
                                    "the search tests 40 worlds out of 49'140", "The engine simulates the 315 single crises itself",
                                    "A number is looked for in the sentence, not its role in it",
                                    "The AI layer has not yet been evaluated with a real model in this repository")),
                            ("fr", ("Couche d'IA : le modèle propose des mondes ou des réglages et écrit des phrases ; il ne calcule rien.",
                                    "la recherche teste 40 mondes sur 49'140", "Le moteur simule lui-même les 315 crises seules",
                                    "La couche d'IA n'a pas encore été évaluée avec un vrai modèle dans ce dépôt"))):
            dom = self.page(f"?tiroir=limites&lang={lang}", recorded="none")
            for sentence in words:
                with self.subTest(lang=lang, sentence=sentence[:40]):
                    self.assertIn(html.escape(sentence, quote=False), dom)
        # The figures of those limits are the ones of the code.
        from ai import stress as stressing, vocabulary as V
        th = TREE.theta(None)
        self.assertEqual((stressing.CALLS * stressing.PER_CALL, V.size(th, TREE.h, TREE.age0), len(V.singles(th, TREE.h, TREE.age0)), len(benchmark.ROUTES)),
                         (40, 49140, 315, 3))


if __name__ == "__main__":
    unittest.main()
