"""Deux langues pour les phrases que le moteur écrit : l'anglais par défaut, le français sur demande.

Le moteur calcule les mêmes chiffres dans les deux langues ; seule l'écriture des phrases change. Chaque phrase est
écrite dans les deux langues au même endroit, avec `say(en, fr)`. La langue courante est celle de la demande en
cours (`use`), sinon la langue par défaut. Les libellés du registre restent en français dans la simulation, qui est
gardée en mémoire, et sont traduits à la sortie (`ledger`, `months`).
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar

LANGUAGES = ("en", "fr")
_default = "en"
_asked: ContextVar[str | None] = ContextVar("doors_language", default=None)


def _known(lang: str) -> str:
    if lang not in LANGUAGES:
        raise ValueError(f"Unknown language '{lang}'. Languages: {list(LANGUAGES)}")
    return lang


def current() -> str:
    """La langue des phrases en ce moment : celle de la demande en cours, sinon la langue par défaut."""
    return _asked.get() or _default


def set_default(lang: str) -> None:
    """Change la langue par défaut du processus. Les tests qui attendent des phrases en français s'en servent."""
    global _default
    _default = _known(lang)


@contextmanager
def use(lang: str):
    """Écrit les phrases dans cette langue le temps d'un bloc : une demande de l'API, un test."""
    token = _asked.set(_known(lang))
    try:
        yield
    finally:
        _asked.reset(token)


def say(en: str, fr: str) -> str:
    """Une phrase du moteur, dans la langue courante."""
    return fr if current() == "fr" else en


def decimal(value: float, digits: int = 1) -> str:
    """Un nombre à virgule, écrit comme la langue l'écrit : 24.8 en anglais, 24,8 en français."""
    text = f"{value:.{digits}f}"
    return text.replace(".", ",") if current() == "fr" else text


def percent(share: float) -> str:
    """Une part écrite en pour cent : 30% en anglais, 30 % en français."""
    return f"{share * 100:.0f} %" if current() == "fr" else f"{share * 100:.0f}%"


def ledger(label: str) -> str:
    """Le libellé d'une ligne du registre dans la langue courante. Un libellé inconnu est rendu tel quel."""
    if current() == "fr":
        return label
    from engine.english import LEDGER, LEDGER_PATTERNS, PLACES
    if label in LEDGER:
        return LEDGER[label]
    for pattern, english in LEDGER_PATTERNS:
        found = re.fullmatch(pattern, label)
        if found:
            return english.format(*(PLACES.get(group, ledger(group)) for group in found.groups()))
    return label


def months(records: list[dict]) -> list[dict]:
    """Les mois d'une vie, prêts à sortir : mêmes chiffres, libellés du registre dans la langue courante."""
    if current() == "fr":
        return records
    return [{**month, "flows": [{**flow, "label": ledger(flow["label"])} for flow in month["flows"]]} for month in records]
