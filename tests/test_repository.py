"""Ce que le dépôt publié contient, et ce qu'il ne dit pas.

Le projet a été réalisé pour le UBS AI Financial Twin Challenge (LauzHack 2026). Les données synthétiques et le
starter-kit viennent de l'autrice du défi : ils sont inclus tels quels, avec sa permission, et rien dans nos
fichiers ne les présente comme des données ou un produit de la banque.
"""
from __future__ import annotations

import hashlib
import re
import unittest
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHALLENGE_FILES = {
    "Data/scenario-assumptions.csv": "afaa83170c4d10fa02b6066fdad130167a617890f90afe0216b1165cda161715",
    "Data/scenario-catalog.csv": "64d05bcb0059780f7dca2fef5665350180ae7a257fea5211130cca2cb5d06b7a",
    "Data/synthetic-cash-balances.csv": "1b83b4bd8187a4577acc592fdd57621c39aa4a9f78f1130ce964f94f0afa31ca",
    "Data/synthetic-goals.csv": "d98e43d317cd2a4aeceb42a531b39d7da5b08df92a9897fd43d8919e474a4067",
    "Data/synthetic-profiles.csv": "c4bccfae18582f405739e307968f537c28b21de0c0222ca5ff6245bf207c59da",
    "starter-kit/QUICKSTART.md": "7c3ea30d4f424cc5c86bf2c8d70a51ab3f94ae9ef3d99743669a07334f9c3956",
    "starter-kit/README.md": "356d1696a52a36a58b3a06ea8a168c95f0ca6ecb53d5daaac5080de0938978c6",
    "starter-kit/financial_twin.py": "7fc1a4e015582e25b28ad651a8de2122c3282ce83fc346516fe701bc0feee745",
    "starter-kit/gitignore": "2cbebf5f5b0bcf89768e0b4f315998a4ea051c24a541e3d7d2780ae0d0dc148b",
    "starter-kit/run_example.py": "d6c34ff8106a6a0e6d872fd794fb87be50434781a58a29c58585f5f486ccc329",
    "starter-kit/sample_profile.json": "d1e244a1c676a6d5bf32ce5e024b18b0c2373b8444ad441de0bd74c6bbed65be",
    "starter-kit/scenario_config.json": "f4cdd091ff2625540fbe1b1f02ff31f5daa6dc63b9a0d7bb00960b0c99ea3c87",
    "starter-kit/test_financial_twin.py": "4cffce8f8ebec1b6d0eb294e2a308745fc4b3923ac797d4253aae91b8746cd03",
}
SKIPPED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "Data", "starter-kit", "vendor", "node_modules"}
TEXT = {".py", ".js", ".css", ".html", ".md", ".json", ".txt", ".ini", ".yml", ".yaml", ".toml", ".sh", ".cfg", ""}
# Le nom de la banque n'apparaît que dans le nom du défi, et dans la phrase qui dit que le projet n'y est pas lié.
ALLOWED = ("UBS AI Financial Twin Challenge", "not affiliated with, endorsed by, or reviewed by UBS")
BANK = re.compile(r"\bU" r"BS\b", re.IGNORECASE)
# La forme d'une clé de l'API, écrite en deux morceaux pour que ce fichier n'en contienne pas une lui-même.
KEY = re.compile("sk-" + r"ant-[A-Za-z0-9_\-]{12,}")
# L'autrice du défi, telle qu'elle est créditée : son nom et son lien.
AUTHOR = ("Stefania Stan", "https://www.linkedin.com/in/stefania-s/")
# Les emplacements qui tenaient la place de ce nom et de ce lien, écrits en deux morceaux pour que ce fichier ne les contienne pas.
BLANKS = ("[" + "Nom]", "[lien " + "LinkedIn]")
LOCAL = re.compile(r"/Us" r"ers/|/ho" r"me/[a-z]|[\w.+-]+@(?!users\.noreply\.github\.com|anthropic\.com)[\w-]+\.(?:com|ch|org|fr|net)\b")


def ours() -> list[Path]:
    """Nos fichiers de texte : tout le dépôt, sauf les fichiers du défi, les polices et les dossiers de travail."""
    return [f for f in ROOT.rglob("*") if f.is_file() and not SKIPPED_DIRS & set(f.relative_to(ROOT).parts)
            and f.suffix in TEXT and f.name != ".DS_Store"]


class Repository(unittest.TestCase):
    def test_the_challenge_files_are_included_unchanged(self):
        """Les données synthétiques et le starter-kit : exactement les fichiers attendus, à l'octet près."""
        found = sorted(str(f.relative_to(ROOT)) for d in ("Data", "starter-kit") for f in (ROOT / d).rglob("*")
                       if f.is_file() and "__pycache__" not in f.parts and f.name != ".DS_Store")
        self.assertEqual(found, sorted(CHALLENGE_FILES))
        for name, expected in CHALLENGE_FILES.items():
            with self.subTest(file=name):
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected)

    def test_the_bank_is_only_named_in_the_name_of_the_challenge(self):
        """Ni nos textes, ni nos étiquettes, ni notre code ne présentent une donnée ou un produit comme venant de la banque."""
        self.assertGreater(len(ours()), 40)
        for file in ours():
            text = file.read_text(encoding="utf-8")
            for phrase in ALLOWED:
                text = text.replace(phrase, "")
            with self.subTest(file=str(file.relative_to(ROOT))):
                self.assertIsNone(BANK.search(text))

    def test_the_credits_and_the_disclaimer_are_there(self):
        disclaimer, notice = (" ".join((ROOT / name).read_text(encoding="utf-8").split()) for name in ("DISCLAIMER.md", "NOTICE"))
        for phrase in ("built for the UBS AI Financial Twin Challenge (LauzHack 2026)", "not affiliated with, endorsed by, or reviewed by UBS",
                       "challenge author and information owner", "included with her permission", "Nothing in this project is financial advice"):
            self.assertIn(phrase, disclaimer)
        # L'autrice du défi est nommée, avec son lien, partout où ses fichiers sont crédités.
        for text in (disclaimer, notice):
            for part in AUTHOR + ("challenge author and information owner",):
                self.assertIn(part, text)
        for phrase in ("They are included with her permission.", "They are not covered by the licence of this project's own code, and they are not ours to relicense.",
                       "SIL Open Font License 1.1"):
            self.assertIn(phrase, notice)

    def test_the_licence_is_the_mit_text_alone_and_its_two_notes_are_in_the_notice(self):
        """LICENSE ne contient que le texte MIT, au nom d'Amine Senhadji : rien avant, rien après. Ce qu'il faut savoir
        en plus est dans NOTICE : le moteur est co-écrit et l'accord du coéquipier est attendu ; la licence ne couvre
        ni les fichiers du défi ni les polices."""
        licence = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(licence.startswith("MIT License\n\nCopyright (c) 2026 Amine Senhadji\n\nPermission is hereby granted, free of charge, to any person"))
        self.assertTrue(licence.endswith("OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\nSOFTWARE.\n"))
        self.assertEqual((len(licence.split()), licence.count("Copyright"), licence.count("engine")), (169, 1, 0))
        notice = " ".join((ROOT / "NOTICE").read_text(encoding="utf-8").split())
        for phrase in ("MIT: see LICENSE. Two notes go with it:",
                       "1. The engine (`engine/`) was co-written with a teammate, whose agreement to this licence is awaited.",
                       "2. The licence covers the project's own code and documents. It does not cover the challenge material in `Data/` and `starter-kit/`, "
                       "nor the fonts in `web/vendor/barlow/`",
                       "The engine in `engine/` was co-written with a teammate during the hackathon. "
                       "Interface, decision policies, AI layer and portfolio: Amine Senhadji."):
            self.assertIn(phrase, notice)

    def test_what_is_still_to_complete_is_plain_to_see_and_nothing_else_is_left_blank(self):
        """Ce qui reste à compléter avant la publication est écrit en clair dans NOTICE : le nom du co-auteur et son
        accord. Le nom et le lien de l'autrice du défi, eux, sont remplis partout."""
        notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
        self.assertIn("\nCo-author: [à confirmer]\n", notice)
        self.assertIn("Still to complete\n-----------------\n- Co-author: [à confirmer].", notice)
        self.assertIn("- His agreement to the MIT licence for `engine/`: see the first note under", notice)
        waiting = [str(file.relative_to(ROOT)) for file in ours() if "[à confirmer]" in file.read_text(encoding="utf-8") and file.name != "test_repository.py"]
        self.assertEqual(waiting, ["NOTICE"])
        for file in ours():
            text = file.read_text(encoding="utf-8")
            with self.subTest(file=str(file.relative_to(ROOT))):
                for blank in BLANKS:
                    self.assertNotIn(blank, text)

    def test_no_local_path_and_no_personal_address_is_left_in_our_files(self):
        for file in ours():
            with self.subTest(file=str(file.relative_to(ROOT))):
                self.assertIsNone(LOCAL.search(file.read_text(encoding="utf-8")))


class TheKeyAndTheSdk(unittest.TestCase):
    def test_no_file_holds_anything_shaped_like_a_key(self):
        """La clé de l'API n'est lue que dans l'environnement, par le SDK. Aucun fichier du dossier n'en contient une,
        suivi par git ou non : ni le code, ni les réponses enregistrées, ni le journal des commandes en direct."""
        skipped = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"}
        files = [f for f in ROOT.rglob("*") if f.is_file() and not skipped & set(f.relative_to(ROOT).parts) and f.stat().st_size < 20_000_000]
        self.assertGreater(len(files), 100)
        for file in files:
            with self.subTest(file=str(file.relative_to(ROOT))):
                self.assertIsNone(KEY.search(file.read_text(encoding="utf-8", errors="ignore")))
        self.assertIsNotNone(KEY.search("sk-" + "ant-" + "api03-" + "x" * 40))          # le motif reconnaît bien la forme d'une clé

    def test_every_dependency_is_pinned_and_the_sdk_installed_is_the_one_pinned(self):
        lines = [line for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
        pinned = dict(line.split("==") for line in lines)                               # une ligne sans « == » ferait échouer ce test
        self.assertEqual(sorted(pinned), ["anthropic", "fastapi", "httpx", "pytest", "uvicorn"])
        try:
            self.assertEqual(metadata.version("anthropic"), pinned["anthropic"])
        except metadata.PackageNotFoundError:  # pragma: no cover
            self.skipTest("le SDK n'est pas installé : pip install -r requirements.txt")

    def test_what_the_live_commands_write_on_this_machine_is_not_published(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        for line in (".venv/", ".env", ".env.*", "reports/ai_live.log", "reports/ai_dry_run.*.json"):
            self.assertIn(line, ignored)


if __name__ == "__main__":
    unittest.main()
