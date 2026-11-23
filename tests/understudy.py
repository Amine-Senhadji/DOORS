"""A stand-in for the model that says something worth showing, for the tests of the screen.

It plays both parts with no model. In a search it tests worlds chosen in advance, the hardest of the route among them.
For the explanations it reads the facts it is given, as a model would, and writes a sentence with two of the engine's
figures copied as they are written. For “Ask” it fills the form a careful reader would fill for a few known sentences.

What it produces is written to a folder of the test, never to ai/recorded/: those files are not answers of the model,
and nothing in the repository presents them as such.
"""
from __future__ import annotations

import re

from ai import ask as asking
from ai import benchmark, recordings, rehearsal
from ai import stress as stressing
from ai.model import MODEL, Recorder, Reply, answers
from engine.blocks import normalize
from engine.tree import Tree

RECORDED_AT = "2026-11-23"
FIRST = ["chomage_long@27", "chomage_long@23+chomage_long@24", "krach@24", "inflation@22", "chomage_6_mois@27~150", "perte_job_etudiant@26",
         "franc_faible@21", "crise_immobiliere@24"]                    # the first call of the search: worlds worth a look on the demo route
KEPT = {"en": "Goals kept in this world", "fr": "Objectifs gardés dans ce monde"}
BORROWED = {"en": "Peak borrowing in this world", "fr": "Emprunt maximal dans ce monde"}
TOTAL = {"en": "Goals in all", "fr": "Objectifs en tout"}
TEXT = {"en": "You keep {kept} of your {total} goals in this world, and you borrow up to {borrowed}.",
        "fr": "Dans ce monde tu gardes {kept} de tes {total} objectifs, et tu empruntes jusqu'à {borrowed}."}
EMPTY = rehearsal.EMPTY
# The six sentences of the demo, in both languages, and the form a careful reader fills for each.
SENTENCES = {
    "en": ["What if I lost my job for 9 months at 27?", "What if I did my master's first, then worked?", "What if I moved to Berlin at 23?",
           "A market crash of 40% at 24, then a year without a job right after my master's.",
           "With a rent of 1'500 CHF and a return of 5%, and 40'000 CHF set aside at 26.", "What if I had a child at 28 and moved to London?"],
    "fr": ["Et si je perdais mon emploi pendant 9 mois à 27 ans ?", "Et si je faisais mon master d'abord, puis un emploi ?", "Et si je partais à Berlin à 23 ans ?",
           "Un krach de 40 % à 24 ans, puis un an sans emploi juste après mon master.",
           "Avec un loyer de 1'500 CHF et un rendement de 5 %, et 40'000 CHF de côté à 26 ans.", "Et si j'avais un enfant à 28 ans et que je partais à Londres ?"],
}
RATE = {"en": "What if the return were 0.05?", "fr": "Et si le rendement était de 0,05 ?"}      # a rate with no unit: two readings
# One sentence with a setting of each kind: a route, a crisis with no size given, an assumption and savings.
MIXED = {"en": "What if I did my master's first, then worked, with a market crash at 24, a rent of 1'500 CHF and 40'000 CHF set aside at 26?",
         "fr": "Et si je faisais mon master d'abord, puis un emploi, avec un krach à 24 ans, un loyer de 1'500 CHF et 40'000 CHF de côté à 26 ans ?"}
# A search that looks in the wrong place: market crashes and inflation only, never a job lost.
MILD = [f"{kind}@{age}~{severity}" for kind in ("krach", "inflation") for age in range(21, 30) for severity in (50, 75, 100)][:stressing.CALLS * stressing.PER_CALL]


def form_for(sentence: str, lang: str) -> dict:
    """The form for one of the known sentences. Its quotes are words of the sentence, as the model is asked to give them."""
    quote = lambda en, fr: en if lang == "en" else fr
    if sentence == RATE[lang]:
        return {**EMPTY, "assumptions": [{"key": "rendement_placements_annuel", "value": 0.05, "unit": "none", "quote": quote("the return were 0.05", "le rendement était de 0,05")}]}
    if sentence == MIXED[lang]:
        return {**EMPTY, "route": [{"block": "master", "years": None, "quote": quote("my master's first", "mon master d'abord")},
                                   {"block": "job", "years": None, "quote": quote("then worked", "puis un emploi")}],
                "crises": [{"type": "krach", "age": 24, "size": None, "unit": "none", "quote": quote("a market crash at 24", "un krach à 24 ans")}],
                "assumptions": [{"key": "loyer", "value": 1500, "unit": "chf", "quote": quote("a rent of 1'500 CHF", "un loyer de 1'500 CHF")}],
                "savings": {"age": 26, "amount_chf": 40000, "quote": quote("40'000 CHF set aside at 26", "40'000 CHF de côté à 26 ans")}}
    number = SENTENCES[lang].index(sentence) + 1
    if number == 1:
        return {**EMPTY, "crises": [{"type": "chomage_6_mois", "age": 27, "size": 9, "unit": "months",
                                     "quote": quote("I lost my job for 9 months at 27", "je perdais mon emploi pendant 9 mois à 27 ans")}]}
    if number == 2:
        return {**EMPTY, "route": [{"block": "master", "years": None, "quote": quote("my master's first", "mon master d'abord")},
                                   {"block": "job", "years": None, "quote": quote("then worked", "puis un emploi")}]}
    if number == 3:
        return {**EMPTY, "change": {"at_age": 23, "branch": "berlin", "quote": quote("I moved to Berlin at 23", "je partais à Berlin à 23 ans")}}
    if number == 4:
        return {**EMPTY, "crises": [{"type": "krach", "age": 24, "size": 40, "unit": "percent", "quote": quote("A market crash of 40% at 24", "Un krach de 40 % à 24 ans")},
                                    {"type": "chomage_long", "age": 27, "size": 1, "unit": "years",
                                     "quote": quote("a year without a job right after my master's", "un an sans emploi juste après mon master")}]}
    if number == 5:
        return {**EMPTY, "assumptions": [{"key": "loyer", "value": 1500, "unit": "chf", "quote": quote("a rent of 1'500 CHF", "un loyer de 1'500 CHF")},
                                         {"key": "rendement_placements_annuel", "value": 5, "unit": "percent", "quote": quote("a return of 5%", "un rendement de 5 %")}],
                "savings": {"age": 26, "amount_chf": 40000, "quote": quote("40'000 CHF set aside at 26", "40'000 CHF de côté à 26 ans")}}
    return {**EMPTY, "not_understood": [{"quote": quote("I had a child at 28", "j'avais un enfant à 28 ans"), "why": "no_such_event"},
                                        {"quote": quote("moved to London", "je partais à Londres"), "why": "london"}]}


class Understudy(rehearsal.StandIn):
    """Plays the model for the screen: a search that finds something, explanations with the engine's figures, and the
    forms of the known sentences. `slips`: write a figure the engine never gave in the text of the first world, as many
    times, so that the checker refuses it and a rewrite is asked. `worlds`: what the search tests, when it is not the
    search that finds something."""
    name = MODEL

    def __init__(self, tree: Tree, lang: str = "en", sentence: str | None = None, slips: int = 0, worlds: list[str] | None = None):
        if worlds is None:
            sample = [world for world in rehearsal.sample(tree) if world not in FIRST]
            worlds = FIRST + sample[:stressing.CALLS * stressing.PER_CALL - len(FIRST)]
        super().__init__(worlds)
        self.lang, self.sentence, self.slips = lang, sentence, slips

    def reply(self, *, system: str, messages: list[dict], tools: list[dict], output: dict | None, effort: str) -> Reply:
        fields = (output or {}).get("properties") or {}
        played = self.explained(messages, fields) if "explanations" in fields else answers(form_for(self.sentence, self.lang)) if "route" in fields \
            else super().reply(system=system, messages=messages, tools=tools, output=output, effort=effort)
        return Reply(played.content, played.stop_reason, {"input_tokens": 1000, "output_tokens": 100}, MODEL)

    def explained(self, messages: list[dict], fields: dict) -> Reply:
        """One sentence per world, made of the figures listed for that world, read in the facts as a model reads them."""
        facts, lang = messages[0]["content"], self.lang
        written = lambda block, origin: re.search(rf"^- {re.escape(origin)}: (.+)$", block, re.MULTILINE).group(1)
        total, texts = written(facts, TOTAL[lang]), []
        asked = fields["explanations"]["items"]["properties"]["world"]["enum"]
        for index, world in enumerate(asked):
            block = facts.split(f" {world}: ", 1)[1].split("\n\n", 1)[0]          # the facts of that world, up to the next blank line
            text = TEXT[lang].format(kept=written(block, KEPT[lang]), total=total, borrowed=written(block, BORROWED[lang]))
            if index == 0 and self.slips > 0:
                text = text.replace(written(block, BORROWED[lang]), "99'999 CHF")
            texts.append({"world": world, "text": text})
        self.slips -= 1
        return answers({"explanations": texts})


def record(tree: Tree, kind: str, lang: str, sentence: str | None = None, path: list[dict] | None = None, slips: int = 0, folder=None,
           worlds: list[str] | None = None) -> dict:
    """One exchange played by the understudy and written as a recording, in the folder given."""
    path = normalize(path or benchmark.ROUTES["story_a"], tree.h)
    recorder = Recorder(Understudy(tree, lang, sentence, slips, worlds))
    if kind == "stress":
        stressing.run(tree, path, recorder, {}, lang, benchmark.truth_for(path, {}, tree.h))
    else:
        asking.ask(tree, sentence, recorder, path, {}, lang)
    recording = {"kind": kind, "language": lang, "scenario": "alexia", "label": "story_a", "path": path, "assumptions": {}, "sentence": sentence,
                 "model": MODEL, "served_by": [MODEL], "recorded_at": RECORDED_AT, "sdk": "2.12.0", "seconds": 1.0, "usage": {}, "cost_usd": 0.0,
                 "turns": recorder.turns}
    recordings.write(recording, folder)
    return recording


def record_all(tree: Tree, folder, languages=("en", "fr"), slips: int = 0) -> None:
    """What the recording script records for real: one stress test and the six sentences, in each language. Plus the
    sentence with a rate that has no unit."""
    for lang in languages:
        record(tree, "stress", lang, slips=slips, folder=folder)
        for sentence in SENTENCES[lang] + [RATE[lang]]:
            record(tree, "ask", lang, sentence, folder=folder)
