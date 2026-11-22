"""Ce que le dépôt publié contient, et ce qu'il ne dit pas.

Le projet a été réalisé pour le UBS AI Financial Twin Challenge (LauzHack 2026). Les données synthétiques et le
starter-kit viennent de l'autrice du défi : ils sont inclus tels quels, avec sa permission, et rien dans nos
fichiers ne les présente comme des données ou un produit de la banque.
"""
from __future__ import annotations

import hashlib
import re
import unittest
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
        disclaimer = (ROOT / "DISCLAIMER.md").read_text(encoding="utf-8")
        for phrase in ("built for the UBS AI Financial Twin Challenge (LauzHack 2026)", "not affiliated with, endorsed by, or reviewed by UBS",
                       "challenge author and information owner", "included with her permission", "Nothing in this project is financial advice"):
            self.assertIn(phrase, disclaimer)
        self.assertIn("challenge author", (ROOT / "NOTICE").read_text(encoding="utf-8"))

    def test_no_local_path_and_no_personal_address_is_left_in_our_files(self):
        for file in ours():
            with self.subTest(file=str(file.relative_to(ROOT))):
                self.assertIsNone(LOCAL.search(file.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
