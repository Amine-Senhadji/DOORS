"""Sert l'interface (web/) à la racine du serveur.

Aucun calcul ici : tout chiffre affiché vient des routes de api/main.py, donc de engine/.
Ce fichier est séparé de api/main.py pour que les routes de calcul et l'interface évoluent sans se gêner.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

WEB = Path(__file__).resolve().parents[1] / "web"

# The fonts of the page are .woff2 files. Python takes the types of files from the system (/etc/mime.types) and, in 3.12, does not know
# this one by itself: a slim Linux image, such as the one of the container, would serve them as application/octet-stream.
mimetypes.add_type("font/woff2", ".woff2")


class Page(StaticFiles):
    """Les fichiers de web/, jamais gardés en cache : la page affichée est toujours la dernière écrite."""

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response


def attach(app: FastAPI) -> None:
    """À appeler en dernier : ce montage attrape toute adresse qu'aucune route n'a reconnue."""
    app.mount("/", Page(directory=WEB, html=True), name="web")
