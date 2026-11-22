"""L'interface (web/) : servie par le même serveur que les routes de calcul, sans rien charger depuis
internet, sans formule financière, et fidèle à ce que l'API renvoie.

Lancer depuis la racine du dépôt :
    .venv/bin/python -m unittest discover -s tests
"""
from __future__ import annotations

from engine import i18n

i18n.set_default("fr")      # ces tests attendent les phrases du moteur en français ; l'anglais est testé dans tests/test_english.py

import html
import re
import shutil
import socket
import subprocess
import threading
import time
import unittest
from pathlib import Path

try:
    import uvicorn
    from fastapi.testclient import TestClient
    from api.main import app
except ImportError:  # pragma: no cover
    TestClient = None

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
OURS = [f for f in WEB.rglob("*") if f.is_file() and "vendor" not in f.parts and f.suffix in {".html", ".css", ".js"}]
NEEDS_FASTAPI = "FastAPI non installé : .venv/bin/pip install -r requirements.txt"
CHROME = next((p for p in ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                           shutil.which("google-chrome") or "", shutil.which("chromium") or ""] if p and Path(p).exists()), None)


def read(file: Path) -> str:
    return file.read_text(encoding="utf-8")


class Files(unittest.TestCase):
    """Ce que les fichiers de web/ contiennent, sans lancer de serveur."""

    def test_nothing_is_loaded_from_the_internet(self):
        """La démo doit marcher en mode avion : aucun de nos fichiers ne pointe vers l'extérieur."""
        self.assertGreaterEqual(len(OURS), 7)
        for file in OURS:
            with self.subTest(file=file.name):
                self.assertIsNone(re.search(r"https?://|//cdn|@import", read(file)))

    def test_every_local_reference_exists(self):
        patterns = [r"""from\s+['"](\.[^'"]+)['"]""", r"""import\s+['"](\.[^'"]+)['"]""",
                    r"""(?:src|href)=["'](\.[^"']+)["']""", r"""url\(["']?(\.[^"')]+)["']?\)"""]
        found = 0
        for file in OURS:
            for pattern in patterns:
                for target in re.findall(pattern, read(file)):
                    self.assertTrue((file.parent / target).resolve().is_file(), f"{file.name} -> {target}")
                    found += 1
        self.assertGreaterEqual(found, 15)

    def test_the_only_third_party_files_are_the_fonts_with_their_licence(self):
        vendor = sorted(p.relative_to(WEB / "vendor").as_posix() for p in (WEB / "vendor").rglob("*") if p.is_file())
        self.assertEqual(vendor, ["barlow/LICENSE", "barlow/LICENSE-condensed",
                                  "barlow/barlow-condensed-latin-600-normal.woff2",
                                  "barlow/barlow-condensed-latin-700-normal.woff2", "barlow/barlow-latin-400-normal.woff2",
                                  "barlow/barlow-latin-500-normal.woff2", "barlow/barlow-latin-600-normal.woff2"])
        for licence in ("LICENSE", "LICENSE-condensed"):
            self.assertIn("SIL Open Font License", read(WEB / "vendor" / "barlow" / licence))

    def test_the_night_palette_and_the_fonts_of_the_specification(self):
        css = read(WEB / "style.css")
        for colour in ("#0E1936", "#0B1530", "#1C2B57", "#16244D", "#2B3D70", "#2A3B6B", "#F2F5FB", "#C9D3EA",
                       "#A9B6D3", "#3DDC84", "#FFC53D", "#FF5A52", "#8291BD", "#FFE9A8"):
            with self.subTest(colour=colour):
                self.assertIn(colour, css)
        self.assertIn("Barlow Condensed", css)

    def test_no_financial_formula_in_the_interface(self):
        """L'interface ne recopie pas le moteur : ni hasard, ni puissance, ni taux ou seuil d'une règle financière."""
        forbidden = ["Math.random", "Math.pow", "**", "taux_", "lpp_", "impot_", "rendement_", "lamal_"]
        for file in OURS:
            if file.suffix != ".js":
                continue
            for word in forbidden:
                with self.subTest(file=file.name, word=word):
                    self.assertNotIn(word, read(file).replace("/**", ""))

    def test_the_interface_never_says_chances_probability_or_risk(self):
        """Règle du projet : ni hasard chiffré, ni conseil, ni classement des branches."""
        for file in OURS:
            with self.subTest(file=file.name):
                self.assertIsNone(re.search(r"chance|probabilit|risque|meilleur|conseill|recommand|garanti", read(file), re.IGNORECASE))
        texts = read(WEB / "texts.fr.js")
        for sentence in ("Ni prévision, ni conseil", "mondes testés", "Prendre cette branche", "quoi qu’il arrive dans les mondes testés"):
            self.assertIn(sentence, texts)

    def test_the_train_is_only_an_animation_and_can_be_switched_off(self):
        train, css = read(WEB / "train.js"), read(WEB / "style.css")
        self.assertIn("from './train.js'", read(WEB / "app.js"))
        self.assertNotIn("fetch", train)
        self.assertNotIn("chf", train.lower(), "Le métro ne lit aucun montant")
        self.assertRegex(css, r"prefers-reduced-motion: reduce\) \{[^}]*\}\s*#train \{ display: none; \}")

    def test_each_colour_has_a_single_meaning(self):
        """Vert, orange, rouge : l'état d'une station. Jaune : la dernière correspondance utile, et rien d'autre."""
        css = read(WEB / "style.css")
        yellow = [line for line in css.splitlines() if "var(--lamp)" in line]
        self.assertTrue(yellow and all(".last" in line for line in yellow), yellow)
        section = next(line for line in css.splitlines() if line.startswith("#tracks .section {"))
        self.assertIn("stroke: var(--train)", section)
        self.assertNotIn('class="section ${', read(WEB / "map.js"))

    def test_every_number_comes_through_the_api_module(self):
        """Un seul fichier appelle le serveur : web/api.js."""
        for file in OURS:
            if file.suffix == ".js" and file.name != "api.js":
                with self.subTest(file=file.name):
                    self.assertNotIn("fetch(", read(file))


@unittest.skipIf(TestClient is None, NEEDS_FASTAPI)
class Served(unittest.TestCase):
    """La page et les routes de calcul vivent sur le même serveur."""

    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(app)

    def test_the_page_and_its_modules_are_served(self):
        page = self.c.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn('<html lang="en">', page.text)          # la page s'annonce en anglais ; ?lang=fr la passe en français
        for path, kind in [("/app.js", "javascript"), ("/api.js", "javascript"), ("/map.js", "javascript"),
                           ("/card.js", "javascript"), ("/i18n.js", "javascript"), ("/texts.en.js", "javascript"),
                           ("/texts.fr.js", "javascript"), ("/style.css", "text/css"),
                           ("/vendor/barlow/barlow-latin-400-normal.woff2", "font/woff2")]:
            with self.subTest(path=path):
                response = self.c.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(kind, response.headers["content-type"])
                self.assertEqual(response.headers["cache-control"], "no-store")

    def test_the_page_does_not_hide_the_routes_of_the_engine(self):
        self.assertEqual(app.routes[-1].name, "web", "Le service de la page doit rester la dernière route déclarée")
        self.assertEqual(self.c.get("/scenario/alexia").json()["profile"]["name"], "Alexia")
        self.assertIsInstance(self.c.get("/assumptions").json(), list)
        self.assertEqual(self.c.post("/simulate", json={"line_id": "master"}).status_code, 200)
        self.assertEqual(self.c.get("/fichier-inconnu.js").status_code, 404)

    def test_the_page_calls_the_real_routes_of_the_version_3(self):
        self.assertEqual(len(self.c.get("/worlds").json()), 7)
        self.assertEqual(self.c.post("/node", json={"path": [], "gare_month": 0}).status_code, 200)
        self.assertIn("const V3 = '';", read(WEB / "api.js"))
        self.assertEqual(self.c.get("/pont/worlds").status_code, 404, "Le pont provisoire a disparu")

    def test_the_routes_of_the_archived_engine_are_gone(self):
        for path in ("/api/catalogue", "/api/checks"):
            self.assertEqual(self.c.get(path).status_code, 404)
        # En écriture, une adresse inconnue tombe sur le service de la page, qui ne sait que lire : 405.
        for path in ("/api/plan", "/api/explain", "/api/compare", "/api/ticket"):
            self.assertEqual(self.c.post(path, json={"blocks": []}).status_code, 405)


def dom_of(path: str) -> str:
    """Le document tel que Chrome sans fenêtre l'affiche, une fois la page démarrée."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        return subprocess.run([CHROME, "--headless=new", "--window-size=1440,900", "--virtual-time-budget=9000",
                               "--dump-dom", f"http://127.0.0.1:{port}{path}"],
                              capture_output=True, text=True, timeout=60).stdout
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def swiss(amount: float) -> str:
    """Un montant comme la page l'écrit : 27'281 CHF."""
    return f"{'−' if round(amount) < 0 else ''}{abs(round(amount)):,}".replace(",", "'") + " CHF"


def light_of(key: str, by_world: dict, world: str) -> str:
    """La règle d'affichage d'une station : ouverte, fermée, ou ouverte ici et fermée dans un autre monde testé."""
    if by_world[world]["doors"][key]["state"] == "fermee":
        return "Station fermée"
    fragile = any(w["doors"][key]["state"] == "fermee" for w in by_world.values())
    return "Station ouverte ici, fermée dans un autre monde testé" if fragile else "Station ouverte"


def spans(months: list[int]) -> list[tuple[int, int]]:
    out: list[list[int]] = []
    for month in months:
        if out and month == out[-1][1] + 1:
            out[-1][1] = month
        else:
            out.append([month, month])
    return [tuple(span) for span in out]


def age_at(month: int, start: int) -> str:
    years, rest = start + month // 12, month % 12
    return f"{years} ans et {rest} mois" if rest else f"{years} ans"


@unittest.skipIf(TestClient is None, NEEDS_FASTAPI)
@unittest.skipIf(CHROME is None, "Chrome n'est pas installé sur cette machine")
class InChrome(unittest.TestCase):
    """Chrome sans fenêtre : la page démarre, et ce qu'elle affiche est ce que l'API renvoie."""

    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(app)
        cls.profile = cls.c.get("/scenario/alexia").json()["profile"]
        cls.worlds = cls.c.get("/worlds").json()
        cls.lines = {b["id"]: b for b in cls.c.post("/node", json={"path": [], "gare_month": 0}).json()["branches"]}

    def page(self, query: str = "") -> tuple[str, str]:
        dom = dom_of(f"/{query}{'&' if query else '?'}lang=fr")      # ces tests lisent la page en français
        self.assertIn('data-ready="1"', dom, dom[-800:])
        return dom, re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", dom)))

    def api(self, route: str, **body) -> dict:
        return self.c.post(f"/{route}", json=body).json()

    def test_the_first_trip_shown_is_the_one_the_api_returns(self):
        dom, text = self.page()
        first = {"path": self.c.get("/scenario/alexia").json()["default_path"]}     # le trajet par défaut : l'histoire de la démo
        self.assertEqual(first["path"], [{"block": "job", "years": 5}, {"block": "master", "years": 2}, {"block": "job", "years": 3}])
        trip = self.api("path", path=first["path"])
        shown = trip["by_world"]["reference"]
        p = self.profile
        self.assertIn(f"{p['name']}, {p['age']} ans, {p['city']}, {swiss(p['cash_chf'])[:-4]} CHF de côté", text)
        self.assertIn("Scénarios sous hypothèses, données fictives. Ni prévision, ni conseil.", text)
        # Les tronçons, dans la barre du trajet.
        for leg in trip["legs"]:
            self.assertIn(f"{leg['name']} {age_at(leg['from_month'], p['age'])} → {age_at(leg['to_month'], p['age'])}", text)
        # Un bouton par monde nommé ; le monde de référence est affiché.
        pills = re.findall(r'<button[^>]*class="pill"[^>]*data-world="([^"]+)"[^>]*aria-pressed="(true|false)"', dom)
        self.assertEqual(pills, [(w["id"], "true" if w["id"] == "reference" else "false") for w in self.worlds])
        # Chaque station porte le nom, l'âge et l'état renvoyés par l'API.
        # Les stations datées sont des feux sur le trajet ; « ne jamais passer dans le rouge » est un indicateur près du titre.
        lights = dict(re.findall(r'<button[^>]*class="(?:light|indicator)[^"]*"[^>]*data-station="([^"]+)"[^>]*aria-label="([^"]+)"', dom))
        self.assertEqual(re.findall(r'<button[^>]*class="indicator[^"]*"[^>]*data-station="([^"]+)"', dom),
                         [d["key"] for d in trip["doors"] if d["whole_trip"]])
        self.assertEqual(len(re.findall(r'<div class="head[^"]*"', dom)), sum(1 for d in trip["doors"] if not d["whole_trip"]))
        self.assertEqual(set(lights), {d["key"] for d in trip["doors"]})
        for door in trip["doors"]:
            where = "tout le trajet" if door["whole_trip"] else f"{door['age']} ans"
            self.assertEqual(html.unescape(lights[door["key"]]), f"{door['name']}, {where} : {light_of(door['key'], trip['by_world'], 'reference')}")
        stations = "station ouverte" if shown["doors_open"] < 2 else "stations ouvertes"
        self.assertIn(f"{shown['doors_open']} {stations} sur {shown['doors_total']} · Monde de référence", text)
        # Le tunnel : autant de tronçons en pointillés que de périodes de financement, et le montant du moteur.
        tunnels = spans(shown["financing_months"])
        self.assertEqual(dom.count('class="tunnel"'), len(tunnels))
        self.assertTrue(tunnels, "Le trajet par défaut doit montrer un tunnel : la reprise d'études se finance")
        self.assertIn(f"Tunnel jusqu’à {age_at(tunnels[-1][1] + 1, p['age'])} · {swiss(shown['peak_financing_chf'])} à financer au plus", text)
        # Les gares du trajet, et les lignes de départ qu'on n'a pas prises.
        gares = self.api("pathways", path=first["path"])["gares"]
        self.assertEqual(re.findall(r'data-gare="(\d+)"', dom), [str(g["gare_month"]) for g in gares])
        # Allègement : sans gare ouverte, aucune branche n'est dessinée ; le trajet n'a qu'une couleur ; une rangée de noms.
        self.assertEqual(dom.count('class="alt"'), 0)
        # Seules les voies utilisées par le trajet sont dessinées : ici les études et l'emploi en Suisse.
        self.assertEqual(dom.count('class="lane"'), 2)
        self.assertEqual(re.findall(r'<div class="lane-name used"[^>]*>([^<]+)<', dom), ["Études", "Emploi en Suisse"])
        self.assertNotIn("data-branch=", dom)
        self.assertNotRegex(dom, r'class="section (open|ajar|closed)"')
        tops = set(re.findall(r'<div class="head[^"]*"[^>]*style="[^"]*top: (\d+)px', dom))
        self.assertEqual(len(tops), 1, "Les noms des stations tiennent sur une seule rangée")
        self.assertEqual(dom.count("<summary>Détails</summary>"), 1)
        # La fiche du trajet : une ligne par monde testé, avec les montants du moteur.
        self.assertIn('data-selected="trajet"', dom)
        self.assertIn("Faire rouler le métro", text)
        self.assertNotIn("data-train=", dom, "Le métro ne part que si on le demande")
        for world in self.worlds:
            row = trip["by_world"][world["id"]]
            self.assertIn(f"{world['name']} {row['doors_open']} / {row['doors_total']} {swiss(row['peak_financing_chf'])} "
                          f"{swiss(row['net_worth_end_chf'])}", text)

    def test_an_open_gare_shows_its_branches_and_its_flexibility_in_the_world_shown(self):
        world = "chomage_6_mois"
        master = self.lines["master"]
        dom, text = self.page(f"?trajet=master&gare=12&monde={world}")
        node = self.api("node", path=master["path"], gare_month=12)
        trip = self.api("path", path=master["path"])
        self.assertIn('data-selected="gare:12"', dom)
        self.assertIn(f'data-world="{world}"', dom)
        self.assertIn(f"Gare de correspondance · {node['age']} ans", text)
        flex = node["flexibility"]
        self.assertIn(f"Depuis ici, {len(flex['robust'])} portes sur {flex['doors_total']} restent atteignables "
                      "quoi qu’il arrive dans les mondes testés", text)
        self.assertIn(f"Compté {flex['horizon']}.", text)
        # La jauge de flexibilité apparaît deux fois : sur la gare ouverte, et dans sa fiche. Une barre par porte.
        self.assertEqual(dom.count('class="gauge on-map"'), 1)
        self.assertEqual(dom.count('<i class="robust">'), 2 * len(flex["robust"]))
        self.assertEqual(dom.count('<i class="lost">'), 2 * (flex["doors_total"] - len(flex["robust"]) - len(flex["possible"])))
        here = node["state_by_world"][world]
        self.assertIn(f"{swiss(here['cash_chf'])} sur le compte, {swiss(here['debt_chf'])} de dette, patrimoine de {swiss(here['net_worth_chf'])}", text)
        # Où en sont les crises testées à cette gare : le champ avant_le_choc de chaque monde.
        self.assertEqual({w["id"]: node["state_by_world"][w["id"]]["avant_le_choc"] for w in self.worlds}["reference"], None)
        self.assertIn("À 21 ans, aucune crise testée n’a encore eu lieu.", text)
        # Chaque branche avec ses chiffres dans le monde affiché ; un seul bouton, sur la branche qu'on n'a pas prise.
        for branch in node["branches"]:
            if not branch["available"]:
                self.assertIn(f"Branche fermée. {branch['reason']}", text)
                continue
            s = branch["by_world"][world]
            self.assertIn(f"{branch['label']} " + ("ton trajet actuel " if branch["on_path"] else "")
                          + f"{s['doors_open']} stations ouvertes sur {s['doors_total']} · financement max. {swiss(s['peak_financing_chf'])}"
                          f" · patrimoine à la fin {swiss(s['net_worth_end_chf'])}", text)
        others = [b for b in node["branches"] if b["available"] and not b["on_path"]]
        self.assertEqual(dom.count("Prendre cette branche"), len(others))
        # Sur la carte : les deux lignes de départ non prises, et la branche qui part de cette gare.
        self.assertEqual(dom.count('class="alt"'), len(others), "Seules les branches de la gare ouverte sont dessinées")
        # Les petits feux d'une branche ne se voient qu'au survol ou quand elle est choisie : aucune ne l'est à l'ouverture.
        self.assertEqual(dom.count('<g class="branch"'), len(others))
        self.assertNotIn('<g class="branch picked"', dom)
        self.assertIn("#tracks .branch .dot { opacity: 0;", read(WEB / "style.css"))
        self.assertIn(f"{swiss(trip['by_world'][world]['peak_financing_chf'])} à financer au plus", text)
        self.assertNotEqual(trip["by_world"][world]["peak_financing_chf"], trip["by_world"]["reference"]["peak_financing_chf"],
                            "Ce monde doit changer un montant, sinon l'essai ne prouve rien")

    def test_a_station_card_says_where_the_trip_stops_holding_it(self):
        line = self.lines["berlin"]
        dom, text = self.page("?trajet=berlin&station=logement")
        trip = self.api("path", path=line["path"])
        door = next(d for d in trip["doors"] if d["key"] == "logement")
        row = next(r for r in self.api("pathways", path=line["path"])["by_world"]["reference"]["doors"] if r["key"] == "logement")
        self.assertIn('data-selected="station:logement"', dom)
        self.assertIn(door["rule"], text)
        states = {w["name"]: trip["by_world"][w["id"]]["doors"]["logement"]["state"] for w in self.worlds}
        self.assertEqual(states["Monde de référence"], "fermee")
        opened = sum(1 for state in states.values() if state == "ouverte")
        self.assertIn(f"Ouverte dans {opened} des {len(self.worlds)} mondes testés." if opened
                      else f"Fermée dans les {len(self.worlds)} mondes testés.", text)
        for name, state in states.items():
            self.assertIn(f"{name} : {'ouverte' if state == 'ouverte' else 'fermée'}", text)
        self.assertFalse(row["holds"])
        self.assertIn(f"Point de bascule : {age_at(row['tipping']['month'], self.profile['age'])}.", text)
        last = row["last_transfer"]
        where = f"le départ, à {last['age']} ans" if last["gare_month"] == 0 else f"la gare de {last['age']} ans"
        self.assertIn(f"Dernière correspondance utile : {where}, par la branche « {last['label']} ».", text)
        self.assertIn(f"Point de non-retour : la gare de {row['no_return']['age']} ans.", text)
        self.assertIn(f"Origine de l’objectif : hypothèse de l’équipe. {door['source']}", text)

    def test_a_station_changes_colour_with_the_world_shown_and_says_why(self):
        """Travailler, puis reprendre un master à 25 ans : « Reconversion » tient dans le monde de référence et passe au rouge
        sous un krach. La fiche donne le montant atteint et le montant demandé, la dernière correspondance utile, et le signal."""
        link = "?trajet=emploi&gare=60&branche=master&station=reconversion"
        taken = next(b for b in self.api("node", path=self.lines["emploi"]["path"], gare_month=60)["branches"] if b["id"] == "master")
        trip = self.api("path", path=taken["path"])
        calm, crisis = trip["by_world"]["reference"]["doors"]["reconversion"], trip["by_world"]["krach"]["doors"]["reconversion"]
        self.assertEqual((calm["state"], crisis["state"]), ("ouverte", "fermee"))
        row = next(r for r in self.api("pathways", path=taken["path"])["by_world"]["krach"]["doors"] if r["key"] == "reconversion")
        opened = sum(1 for w in self.worlds if trip["by_world"][w["id"]]["doors"]["reconversion"]["state"] == "ouverte")
        for world, label in (("reference", "Station ouverte ici, fermée dans un autre monde testé"), ("krach", "Station fermée")):
            dom, text = self.page(f"{link}&monde={world}")
            self.assertIn('data-selected="station:reconversion"', dom)
            self.assertIn(f'data-station="reconversion" aria-label="Reconversion, 28 ans : {label}"', html.unescape(dom))
            self.assertIn(f"Krach des marchés : fermée · {swiss(crisis['value_chf'])} pour {swiss(crisis['required_chf'])} demandés", text)
            self.assertIn(f"Ouverte dans {opened} des {len(self.worlds)} mondes testés.", text)
        # Dans le monde du krach : où le trajet cesse de tenir la station, la correspondance qui la sauve, et le signal à surveiller.
        self.assertIn("Point de bascule : 28 ans.", text)
        self.assertIn(f"Dernière correspondance utile : la gare de {row['last_transfer']['age']} ans, par la branche « {row['last_transfer']['label']} ».", text)
        self.assertIsNotNone(row["signpost"])
        self.assertIn(f"À surveiller {row['signpost']['text']}", text)
        self.assertIn(f"Dans le monde affiché : {swiss(crisis['value_chf'])} pour {swiss(crisis['required_chf'])} demandés.", text)
        # La gare de 26 ans, dernière correspondance utile : toutes les crises testées y ont commencé. Quatre ont déjà eu lieu ;
        # la poussée d'inflation et le franc plus faible durent encore, et le moteur les dit en cours.
        gare = self.api("node", path=taken["path"], gare_month=72)
        self.assertTrue(all(gare["state_by_world"][w["id"]]["avant_le_choc"] is False for w in self.worlds if w["id"] != "reference"))
        self.assertEqual({w["id"]: gare["state_by_world"][w["id"]]["crises"][0]["status"] for w in self.worlds if w["id"] != "reference"},
                         {"krach": "passee", "chomage_6_mois": "passee", "perte_job_etudiant": "passee", "inflation": "en_cours",
                          "crise_immobiliere": "passee", "franc_faible": "en_cours"})
        dom, text = self.page("?gare=72&monde=krach")
        self.assertIn("À 26 ans, ces crises testées ont déjà eu lieu : krach des marchés, six mois de chômage, perte du job étudiant "
                      "et crise immobilière. En cours : poussée d'inflation et franc plus faible.", text)
        self.assertRegex(html.unescape(dom), r'class="gare[^"]*\blast\b[^"]*"[^>]*data-gare="72"[^>]*aria-label="[^"]*dernière correspondance utile"')
        self.assertIn('class="works"', self.page(link)[0], "Un tronçon fragile s'affiche en travaux dans le monde de référence")


    def test_the_plan_panel_shows_the_fixed_plan_against_the_adaptive_plan_in_the_world_shown(self):
        """Le panneau « Plan figé ou plan adaptatif », sur l'histoire de la démo, dans le monde du krach."""
        path = self.c.get("/scenario/alexia").json()["default_path"]
        plan = self.api("adaptive", path=path)
        here, kept = plan["by_world"]["krach"], plan["summary"]["doors_kept"]["reconversion"]
        self.assertTrue(here["adaptive"]["applies"])
        dom, text = self.page("?plan=1&monde=krach")
        self.assertIn('data-selected="plan:"', dom)
        self.assertIn(f"La règle. {plan['rule']['text']}", text)
        self.assertIn(f"à {plan['rule']['age']} ans : {swiss(here['adaptive']['observed_chf'])} de côté. La règle s’applique.", text)
        self.assertIn(f"Objectifs gardés {here['fixed']['doors_open']} sur 6 {here['adaptive']['doors_open']} sur 6", text)
        self.assertIn(f"Emprunt maximal {swiss(here['fixed']['peak_financing_chf'])} {swiss(here['adaptive']['peak_financing_chf'])}", text)
        self.assertIn(f"Emprunt évité : {swiss(here['saved']['financing_avoided_chf'])}.", text)
        self.assertIn(f"La règle garde « Reconversion » dans {kept['adaptive']} mondes sur {plan['summary']['worlds']}, "
                      f"le plan figé dans {kept['fixed']}.", text)
        self.assertEqual((kept["adaptive"], kept["fixed"]), (7, 3))
        # Sur la carte : la gare de la règle est ouverte, et la branche que la règle prend est choisie (ses petits feux sont affichés).
        self.assertIn(f'<g class="branch picked" data-branch="{plan["rule"]["branch_id"]}"', dom)
        # Dans le monde de référence, la règle ne s'applique pas : aucune branche n'est choisie.
        dom, text = self.page("?plan=1")
        self.assertIn("La règle ne s’applique pas : les deux plans sont les mêmes.", text)
        self.assertNotIn('<g class="branch picked"', dom)


    # ------------------------------------------------------------------------- le tiroir
    def test_the_drawer_is_closed_by_default_and_the_map_buttons_stay_on_the_map(self):
        dom, text = self.page()
        self.assertRegex(dom, r'<aside class="drawer" id="drawer" hidden')
        self.assertNotIn("data-drawer=", dom)
        self.assertIn("Hypothèses et preuves", text)
        # Les boutons de la carte sont dans la carte : ils ne font plus passer la barre du trajet à la ligne.
        page = read(WEB / "index.html")
        self.assertLess(page.index('id="map"'), page.index('class="actions"'))
        self.assertLess(page.index('class="actions"'), page.index('id="stage"'))

    def test_the_drawer_lists_every_assumption_with_its_kind_and_source_and_marks_the_changed_ones(self):
        kinds = {"observe": "données synthétiques du défi", "starter_kit": "hypothèse illustrative du starter-kit",
                 "hypothese": "hypothèse de l’équipe", "a_verifier": "ordre de grandeur suisse, à vérifier", "regle": "règle simplifiée de l’équipe"}
        assumptions = self.c.get("/assumptions").json()
        dom, text = self.page("?tiroir=hypotheses&hyp=taxe_semestre:580")
        self.assertIn('data-drawer="hypotheses"', dom)
        self.assertEqual(len(re.findall(r'<div class="assumption(?: modified)?" data-key=', dom)), len(assumptions))
        for a in assumptions:
            self.assertIn(f"{a['label']} {a['unit']} {kinds[a['kind']]} {a['source']}", text)
        # La valeur modifiée est marquée, avec sa valeur d'origine ; les autres ne le sont pas.
        self.assertEqual(re.findall(r'<div class="assumption modified" data-key="([^"]+)"', dom), ["taxe_semestre"])
        self.assertIn('data-overrides="1"', dom)
        self.assertIn("1 valeur modifiée.", text)
        self.assertIn("Valeur saisie par toi. Valeur d’origine : 4'000 CHF.", text)
        # Et tout le trajet est recalculé par le moteur avec cette valeur.
        path = self.c.get("/scenario/alexia").json()["default_path"]
        changed = self.c.post("/path", json={"path": path, "assumptions": {"taxe_semestre": 580}}).json()["by_world"]["reference"]
        self.assertNotEqual(changed["peak_financing_chf"], self.api("path", path=path)["by_world"]["reference"]["peak_financing_chf"])
        self.assertIn(f"{swiss(changed['peak_financing_chf'])} à financer au plus", text)

    def test_the_drawer_shows_live_checks_the_ledger_of_one_month_and_the_limits(self):
        master = self.lines["master"]
        dom, text = self.page("?trajet=master&monde=chomage_6_mois&tiroir=registre&mois=27")
        self.assertIn('data-drawer="registre"', dom)
        # Les vérifications en direct : celles de /checks, et le bouton qui relance l'égalité avec le starter-kit.
        for check in self.c.get("/checks").json():
            self.assertTrue(check["ok"])
            self.assertIn(f"{check['title']} {check['detail']}", text)
        self.assertIn("Relancer l’égalité avec le starter-kit du défi", text)
        # Le registre du mois 27, dans le monde affiché : chaque ligne du moteur ; une ligne de montant 0 est une note.
        month = self.c.post("/path", json={"path": master["path"], "world_id": "chomage_6_mois"}).json()["months"][27]
        self.assertIn("Mois 27 · 22 ans et 3 mois", text)
        self.assertIn(f"Compte au début du mois {swiss(month['opening_cash_chf'])}", text)
        notes = [f for f in month["flows"] if f["amount_chf"] == 0]
        self.assertTrue(notes, "Ce mois doit contenir une note : la jeune diplômée n'a pas droit au chômage")
        for flow in month["flows"]:
            if flow["amount_chf"] == 0:
                self.assertIn(f"Note : {flow['label']}", text)
            else:
                self.assertIn(f"{flow['label']} ", text)
                self.assertIn(("+" if flow["amount_chf"] > 0 else "") + swiss(flow["amount_chf"]), text)
        self.assertEqual(dom.count('<tr class="note">'), len(notes))
        self.assertIn(f"Patrimoine à la fin du mois {swiss(month['net_worth_chf'])}", text)
        # Les limites : celles de docs/limits.fr.md, lues par le serveur.
        limits = self.c.get("/limits").json()
        self.assertGreaterEqual(len(limits["limits"]), 10)
        for limit in limits["limits"]:
            self.assertIn(limit.replace("`", "`"), text)

    def test_the_gare_card_asks_what_alexia_really_has_and_says_on_which_side_of_the_signal_it_stands(self):
        """Le jumeau qui apprend : la fiche de la gare de 26 ans, sur l'histoire de la démo."""
        path = self.c.get("/scenario/alexia").json()["default_path"]
        # Sans valeur saisie : le champ, et ce que le jumeau simule à cette gare dans le monde affiché.
        plain = self.api("node", path=path, gare_month=72)
        dom, text = self.page("?gare=72&monde=krach")
        self.assertIn("Combien as-tu vraiment de côté ?", text)
        self.assertIn(f"Le jumeau simule {swiss(plain['state_by_world']['krach']['liquidite_chf'])} de côté à cette gare", text)
        self.assertNotIn("data-side=", dom)
        for value, side in ((40000, "sous"), (60000, "au_dessus")):
            seen = {"gare_month": 72, "value_chf": value}
            node, trip = self.api("node", path=path, gare_month=72, observation=seen), self.api("path", path=path, observation=seen)
            dom, text = self.page(f"?gare=72&monde=krach&epargne={value}")
            self.assertIn(f'data-observed="72:{value}"', dom)
            self.assertRegex(dom, rf'<input id="observe-value"[^>]*value="{value}"')
            self.assertIn(f'data-side="{side}"', dom)
            self.assertIn(node["observation"]["signals"][0]["text"], text)
            self.assertIn(f"Le jumeau simulait {swiss(node['observation']['simulated_chf']['krach'])} dans le monde affiché", text)
            self.assertIn("Revenir à l’épargne simulée", text)
            # Les branches repartent de la valeur saisie ; la carte suit le trajet vécu ; la gare est marquée.
            for branch in node["branches"]:
                s = branch["by_world"]["krach"]
                self.assertIn(f"{s['doors_open']} stations ouvertes sur 6 · financement max. {swiss(s['peak_financing_chf'])} · "
                              f"patrimoine à la fin {swiss(s['net_worth_end_chf'])}", text)
            shown = trip["by_world"]["krach"]
            self.assertIn(f"{shown['doors_open']} stations ouvertes sur 6 · Krach des marchés", text)
            self.assertRegex(html.unescape(dom), r'class="gare[^"]*\bseen\b[^"]*"[^>]*data-gare="72"[^>]*aria-label="[^"]*épargne constatée"')
        # Le plan adaptatif lit la valeur saisie.
        plan = self.api("adaptive", path=path, observation={"gare_month": 72, "value_chf": 40000})
        dom, text = self.page("?gare=72&epargne=40000&plan=1")
        self.assertIn("Tu as dit avoir 40'000 CHF de côté à 26 ans : la règle lit cette valeur, dans chaque monde testé. La règle s’applique.", text)
        kept = plan["summary"]["doors_kept"]["reconversion"]
        self.assertEqual((kept["adaptive"], kept["fixed"]), (7, 0))
        self.assertIn("La règle garde « Reconversion » dans 7 mondes sur 7, le plan figé dans 0.", text)
        # Une épargne refusée par le moteur (pas de gare à ce mois) : la page s'ouvre quand même, sans elle.
        dom, _ = self.page("?gare=70&epargne=40000")
        self.assertIn('data-observed=""', dom)

    def test_the_age_of_a_crisis_is_set_in_the_traffic_bar_and_the_whole_screen_follows(self):
        """« Info trafic » : une crise est un type et un âge, de la première à la dernière gare."""
        path = self.c.get("/scenario/alexia").json()["default_path"]
        # À son âge d'origine : sept mondes, le pas à pas, et rien à remettre.
        dom, text = self.page("?monde=krach")
        self.assertEqual(len(re.findall(r'<button[^>]*data-world="', dom)), 7)
        self.assertRegex(dom, r'<body[^>]*data-world="krach"')
        self.assertIn("Début de la crise − 23 ans +", text)
        self.assertNotIn("revenir à", text)
        # Le krach déplacé à 25 ans : le moteur décrit le monde déplacé, et chaque calcul le prend à la place de l'autre.
        ids = [w["id"] if w["id"] != "krach" else "krach@25" for w in self.worlds]
        trip = self.api("path", path=path, world_id="krach@25", mondes=ids)
        node = self.api("node", path=path, gare_month=72, mondes=ids)
        dom, text = self.page("?monde=krach@25&gare=72")
        self.assertRegex(dom, r'<body[^>]*data-world="krach@25"')
        self.assertRegex(dom, r'<body[^>]*data-selected="gare:72"')
        self.assertIn("Début de la crise − 25 ans + revenir à 23 ans", text)
        self.assertIn("Rendement des placements, par mois : −30 % (+0,2 % dans le monde de référence), à 25 ans.", text)
        shown = trip["by_world"]["krach@25"]
        self.assertIn(f"{shown['doors_open']} stations ouvertes sur 6 · Krach des marchés", text)
        for branch in node["branches"]:
            s = branch["by_world"]["krach@25"]
            self.assertIn(f"{s['doors_open']} stations ouvertes sur 6 · financement max. {swiss(s['peak_financing_chf'])} · "
                          f"patrimoine à la fin {swiss(s['net_worth_end_chf'])}", text)
        # Aux bornes, le pas à pas s'arrête : pas avant 21 ans, pas après 29 ans.
        self.assertRegex(self.page("?monde=krach@29")[0], r'<button[^>]*data-age="30"[^>]*disabled')
        self.assertRegex(self.page("?monde=krach@21")[0], r'<button[^>]*data-age="20"[^>]*disabled')
        # Un âge refusé par le moteur : la crise garde le sien, et la page s'ouvre.
        self.assertRegex(self.page("?monde=krach@40")[0], r'<body[^>]*data-world="krach"')
        # La perte du job étudiant, à 25 ans, pendant le master de l'histoire de la démo : une note dans le registre.
        dom, text = self.page("?monde=perte_job_etudiant&tiroir=registre&mois=62")
        self.assertIn("Job étudiant perdu de 25 ans à 25 ans et 6 mois.", text)
        self.assertIn("Note : Job étudiant perdu : pas de revenu ce mois, et pas d'indemnité de chômage", text)

    def test_the_policies_sheet_shows_the_value_table_of_the_route_with_the_fate_of_the_master_in_every_cell(self):
        """La feuille « Des politiques, pas des plans » : chaque case est celle de /policies, objectifs et master au même niveau."""
        table = self.api("policies")
        dom, text = self.page("?politiques=1")
        self.assertRegex(dom, r'<body[^>]*data-policies="ouvert"')
        self.assertRegex(dom, r'<dialog[^>]*id="policies-sheet"[^>]*open')
        self.assertIn("Des politiques, pas des plans", text)
        self.assertIn(f"Objectif visé par les trois politiques : « Reconversion », {swiss(table['target']['required_chf'])} à 28 ans", text)
        self.assertIn("La valeur d’un diplôme au-delà de 30 ans n’est pas mesurée par les six objectifs ; comparer à 30 ans pénalise le master.", text)
        fates = {"termine": "Master terminé à {} ans", "termine_en_travaillant": "Master terminé à {} ans, en travaillant",
                 "arrete": "Master arrêté à {} ans", "pas_commence": "Master pas commencé"}
        self.assertEqual([row["id"] for row in table["policies"]], ["fige", "securite", "equilibre", "ambition"])
        self.assertEqual(len(re.findall(r'<td class="cell[^"]*" data-row=', dom)), 16)
        for row in table["policies"]:
            if row["rule"]:
                self.assertIn(row["rule"]["text"], text)
            for world in table["worlds"]:
                c = table["cells"][row["id"]][world["id"]]
                tag = "" if row["id"] == "fige" else (" la règle s’applique" if c["applies"] else " suit le plan")
                # Dans la case, à la suite : les objectifs gardés, le sort du master, l'emprunt maximal, le regret.
                found = re.search(rf'data-row="{row["id"]}" data-world="{re.escape(world["id"])}">(.*?)</td>', dom, re.S)
                shown = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", found.group(1)))).strip()
                self.assertEqual(shown, f"{c['doors_open']} objectif{'s' if c['doors_open'] > 1 else ''} sur 6 "
                                        f"{fates[c['master']['state']].format(c['master']['age'])} "
                                        f"Emprunt maximal {swiss(c['peak_financing_chf'])} Regret {swiss(c['regret_chf'])}{tag}")
                # Objectifs et master sont deux titres de même rang dans la case.
                self.assertRegex(found.group(1), r'^<strong class="kept num">[^<]+</strong><strong class="fate">[^<]+</strong>')
        # La colonne du choc long est mise en avant, et elle seule.
        long = next(w for w in table["worlds"] if w["highlight"])
        self.assertEqual(len(re.findall(r'<td class="cell long" data-row=', dom)), 4)      # une case par ligne, dans le tableau de valeur
        self.assertEqual(len(re.findall(r'<td class="cell long"', dom)), 11)               # plus la référence clairvoyante et les six écarts
        self.assertRegex(dom, rf'<th class="long" data-world="{long["id"]}">Chômage long à 24 ans \(12 mois\)')
        # La référence clairvoyante est nommée comme telle, et n'est pas présentée comme une action possible.
        self.assertIn("Référence clairvoyante Ce qu’on aurait choisi en connaissant le monde à l’avance.", text)
        self.assertIn("La référence clairvoyante n’est pas une action possible : personne ne connaît le monde à l’avance.", text)
        drawn = table["validation"]["random"]
        for row in table["policies"][1:]:
            self.assertIn(f"{row['name']} : « Reconversion » tient dans {drawn['kept'][row['id']]} des {drawn['draws']} variantes tirées", text)
        # Les trois bandes de chaque ligne : pire monde testé parmi les colonnes, central, prudent.
        self.assertIn("Trois bandes : trois mondes, pas des fréquences Pire monde testé Central Prudent", text)
        names = {"reference": "pas de choc", "krach@24": "krach des marchés à 24 ans", "chomage_6_mois@24": "six mois de chômage à 24 ans",
                 "chomage_long": "chômage long à 24 ans"}
        for row in table["policies"]:
            band = table["bands"][row["id"]]
            worst = band["pire"]
            self.assertIn(f"{row['name']} {worst['doors_open']['value']} objectifs sur 6 ({names[worst['doors_open']['world_id']]}) "
                          f"Emprunt maximal ({names[worst['peak_financing_chf']['world_id']]}) {swiss(worst['peak_financing_chf']['value'])} "
                          f"Patrimoine à la fin ({names[worst['net_worth_end_chf']['world_id']]}) {swiss(worst['net_worth_end_chf']['value'])} "
                          f"{band['central']['doors_open']['value']} objectifs sur 6 Emprunt maximal {swiss(band['central']['peak_financing_chf']['value'])} "
                          f"Patrimoine à la fin {swiss(band['central']['net_worth_end_chf']['value'])} "
                          f"{band['prudent']['doors_open']['value']} objectifs sur 6 Emprunt maximal {swiss(band['prudent']['peak_financing_chf']['value'])} "
                          f"Patrimoine à la fin {swiss(band['prudent']['net_worth_end_chf']['value'])}", text)
        self.assertIn("avec un rendement des placements diminué de 1 point par an. Aucune bande n’est une promesse.", text)
        # Le vocabulaire du cadre : une politique, pas un plan adaptatif.
        self.assertNotIn("adaptatif", read(WEB / "texts.fr.js"))

    def test_the_policies_sheet_shows_fragile_alexia_with_the_same_rules_and_the_gap_with_the_fixed_plan(self):
        """Alexia fragile : 2'000 CHF au départ, les mêmes politiques, et l'écart avec le plan figé dans les deux cas."""
        table = self.api("policies")
        fragile = table["fragile"]
        dom, text = self.page("?politiques=fragile")
        self.assertRegex(dom, r'<body[^>]*data-policies="fragile"')
        self.assertRegex(dom, r'data-case="fragile" aria-pressed="true">Alexia fragile · 2\'000 CHF de côté à 20 ans<')
        self.assertRegex(dom, r'data-case="alexia" aria-pressed="false">Alexia · 8\'000 CHF de côté à 20 ans<')
        self.assertIn("Mêmes règles, mêmes seuils pour les deux : une politique lit l’état, et c’est l’état qui change.", text)
        for row in table["policies"]:
            if row["rule"]:
                self.assertIn(row["rule"]["text"], text)               # les règles d'Alexia, inchangées
            for world in table["worlds"]:
                c = fragile["cells"][row["id"]][world["id"]]
                found = re.search(rf'<td class="cell[^"]*" data-row="{row["id"]}" data-world="{re.escape(world["id"])}">(.*?)</td>', dom, re.S)
                shown = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", found.group(1)))).strip()
                self.assertIn(f"{c['doors_open']} objectif{'s' if c['doors_open'] > 1 else ''} sur 6 Master ", shown)
                self.assertIn(f"Emprunt maximal {swiss(c['peak_financing_chf'])} Regret {swiss(c['regret_chf'])}", shown)
        # L'écart avec le plan figé, pour les deux Alexia, monde par monde.
        self.assertIn("L’écart entre chaque politique et le plan figé, pour les deux Alexia", text)
        self.assertEqual(len(re.findall(r'<tr data-policy="[a-z]+" data-case="(?:alexia|fragile)">', dom)), 6)
        signed = lambda n: "Autant d’objectifs" if n == 0 else f"{'+' if n > 0 else '−'}{abs(n)} objectif{'s' if abs(n) > 1 else ''}"
        for case, label in ((table, "Alexia, 8'000 CHF au départ"), (fragile, "Alexia fragile, 2'000 CHF au départ")):
            for row in table["policies"][1:]:
                cells = []
                for world in table["worlds"]:
                    g = case["gap"][row["id"]][world["id"]]
                    borrowing = "Même emprunt maximal" if g["financing_difference_chf"] == 0 else \
                        f"Emprunt maximal : {'+' if g['financing_difference_chf'] > 0 else ''}{swiss(g['financing_difference_chf'])}"
                    cells.append(f"{signed(g['doors_more'])} {borrowing}" + (" « Reconversion » sauvée" if g["target_saved"] else ""))
                self.assertIn(f"{label} {' '.join(cells)}", text)

    def test_the_folk_rule_sheet_shows_the_sentence_and_the_two_states_of_the_engine(self):
        """« Trois mois d'épargne de précaution suffisent » : la phrase de la diapositive, et les deux états dans les mêmes mondes."""
        answer = self.api("folk-rule")
        dom, text = self.page("?regle=1")
        self.assertRegex(dom, r'<body[^>]*data-folk="ouvert"')
        self.assertIn(f'<p class="slide num">{html.escape(answer["sentence"], quote=False)}</p>', dom.replace("&#39;", "'"))
        self.assertIn("L’épreuve : à 25 ans, exactement 3 mois de dépenses courantes sur le compte, et rien d’autre.", text)
        self.assertEqual(len(re.findall(r'<td class="cell (?:holds|breaks)">', dom)), 16)
        for state in answer["states"]:
            self.assertIn(f"{state['label']} Dépenses courantes : {swiss(state['expenses_chf'])} par mois. "
                          f"Coussin de 3 mois : {swiss(state['cushion_chf'])}. "
                          f"La règle tient dans {state['kept']} des {state['total']} mondes testés.", text)
            found = re.search(rf'<tr data-state="{state["id"]}">(.*?)</tr>', dom, re.S).group(1)
            self.assertEqual(found.count('<td class="cell holds">'), state["kept"])
            for world in answer["worlds"]:
                row = state["by_world"][world["id"]]
                if not row["holds"]:
                    self.assertIn(f"dès {age_at(row['first_red_month'], 20)}, jusqu’à {swiss(row['peak_financing_chf'])} à financer", text)
        # La feuille s'ouvre aussi depuis celle des politiques.
        self.assertIn('id="folk-open">Une règle répandue, à l’épreuve<', self.page("?politiques=1")[0])

    def test_the_trip_card_and_a_station_card_show_the_three_bands_of_the_engine(self):
        """Trois bandes : trois mondes, pas des fréquences : pire monde testé (et lequel), central, prudent."""
        path = self.c.get("/scenario/alexia").json()["default_path"]
        bands = self.api("path", path=path)["bands"]
        names = {w["id"]: w["name"].lower() for w in self.worlds}
        dom, text = self.page()
        worst = bands["pire"]
        self.assertIn("Trois bandes : trois mondes, pas des fréquences Stations ouvertes Financement max. Patrimoine à la fin "
                      f"Pire monde testé {worst['doors_open']['value']} sur 6 {names[worst['doors_open']['world_id']]} "
                      f"{swiss(worst['peak_financing_chf']['value'])} {names[worst['peak_financing_chf']['world_id']]} "
                      f"{swiss(worst['net_worth_end_chf']['value'])} {names[worst['net_worth_end_chf']['world_id']]} "
                      f"Central {bands['central']['doors_open']['value']} sur 6 {swiss(bands['central']['peak_financing_chf']['value'])} "
                      f"{swiss(bands['central']['net_worth_end_chf']['value'])} "
                      f"Prudent {bands['prudent']['doors_open']['value']} sur 6 {swiss(bands['prudent']['peak_financing_chf']['value'])} "
                      f"{swiss(bands['prudent']['net_worth_end_chf']['value'])}", text)
        self.assertEqual(len(re.findall(r'<tr data-band="', dom)), 3)
        # Une station datée : ce qu'elle atteint dans chaque bande. Une station de tout le trajet : son état.
        door = bands["doors"]["reconversion"]
        _, text = self.page("?station=reconversion")
        self.assertIn(f"Pire monde testé : {swiss(door['pire']['value_chf'])} ({names[door['pire']['world_id']]}) · "
                      f"central : {swiss(door['central']['value_chf'])} · prudent : {swiss(door['prudent']['value_chf'])}. "
                      f"Demandé : {swiss(door['central']['required_chf'])}.", text)
        red = bands["doors"]["jamais_rouge"]
        _, text = self.page("?station=jamais_rouge")
        self.assertIn(f"Pire monde testé : fermée ({names[red['pire']['world_id']]}) · central : fermée · prudent : fermée.", text)


if __name__ == "__main__":
    unittest.main()
