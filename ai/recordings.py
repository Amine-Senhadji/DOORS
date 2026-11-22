"""The recorded answers: real exchanges with the model, kept as files in ai/recorded/ and played again without it.

A recording holds what Doors asked, turn by turn, and what the model answered: its texts and its tool calls. It says
which route, which assumptions, which language and, for “Ask”, which sentence it is the answer to. That is how one is
found: nothing is approached, and a route or a sentence with no recording has no recorded answer.

A recording is never shown as it is. It is played again by the loop that made it (ai/service.py): the tools run on
the engine of today, the checker reads the texts again, and the recording is refused if Doors would not ask today,
to the letter, what it asked then.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "ai" / "recorded"
LOG = ROOT / "reports" / "ai_live.log"         # what the live commands did on this machine; it is not part of the repository
FORMAT = 1
# The shape of a key of the API. A text that goes to a file is passed through `scrub`, so that no key can be written
# by accident with the message of an error. The pattern is written in two pieces so that it is not itself that shape.
KEY = re.compile("sk-" + r"ant-[A-Za-z0-9_\-]{8,}")
_read: dict = {}                    # the recordings of a directory, kept until one of its files changes


def scrub(text: str) -> str:
    """A text with anything shaped like a key taken out."""
    return KEY.sub("[key removed]", str(text))


def describe(error: Exception) -> dict:
    """An error as a file may keep it: its kind, the status the API gave if any, and its message with anything shaped
    like a key taken out. No trace: a trace holds the paths of the machine."""
    status = getattr(error, "status_code", None)
    return {"type": type(error).__name__, "status": status if isinstance(status, int) else None,
            "message": scrub(getattr(error, "message", None) or str(error))[:600]}


def log(entry: dict, file: Path | None = None) -> None:
    """One line added to the log of the live commands: what was asked, whether it went well, the tokens and the cost.
    Anything shaped like a key is taken out before the line is written."""
    file = file or LOG
    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open("a", encoding="utf-8") as lines:
        lines.write(scrub(json.dumps({"at": datetime.now().isoformat(timespec="seconds"), **entry}, ensure_ascii=False)) + "\n")


def shown(file: Path) -> str:
    """A file as it is named to the reader: from the root of the repository, never from the root of the machine."""
    try:
        return str(file.relative_to(ROOT))
    except ValueError:
        return file.name


def slug(words: str, length: int = 48) -> str:
    """Words as a part of a file name: plain letters and digits, with dashes."""
    plain = unicodedata.normalize("NFKD", words).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")[:length].strip("-") or "x"


def same_sentence(one: str | None, other: str | None) -> bool:
    return " ".join((one or "").split()) == " ".join((other or "").split())


def file_name(recording: dict) -> str:
    label = recording.get("label") or hashlib.sha256(json.dumps(recording["path"], sort_keys=True).encode()).hexdigest()[:8]
    if recording["kind"] == "ask":
        return f"ask.{recording['language']}.{slug(recording['sentence'])}.json"
    return f"{recording['kind']}.{slug(label)}.{recording['language']}.json"


def write(recording: dict, directory: Path | None = None) -> Path:
    """Writes a recording to its file. Nothing shaped like a key can be in it: the requests hold no header, and the
    text is scrubbed all the same."""
    directory = directory or DIR
    directory.mkdir(parents=True, exist_ok=True)
    file = directory / file_name(recording)
    file.write_text(scrub(json.dumps({"format": FORMAT, **recording}, ensure_ascii=False, indent=1)) + "\n", encoding="utf-8")
    return file


def every(directory: Path | None = None) -> list[dict]:
    """Every recording of the directory, in the order of the file names. Each one carries the name of its file."""
    directory = directory or DIR
    files = sorted(directory.glob("*.json")) if directory.is_dir() else []
    stamp = tuple((file.name, file.stat().st_mtime_ns, file.stat().st_size) for file in files)
    if _read.get(directory) is None or _read[directory][0] != stamp:
        _read[directory] = (stamp, [{**json.loads(file.read_text(encoding="utf-8")), "file": file.name} for file in files])
    return _read[directory][1]


def find(kind: str, language: str, scenario: str, path: list[dict] | None, assumptions: dict | None, sentence: str | None = None,
         directory: Path | None = None) -> dict | None:
    """The recording made for exactly this: the same route, the same assumptions, the same language, and for “Ask” the
    same sentence. None when there is none."""
    assumptions = {key: float(value) for key, value in (assumptions or {}).items()}
    for recording in every(directory):
        if (recording["kind"], recording["language"], recording["scenario"]) == (kind, language, scenario) and recording["path"] == path \
                and {key: float(value) for key, value in recording["assumptions"].items()} == assumptions \
                and (kind != "ask" or same_sentence(recording["sentence"], sentence)):
            return recording
    return None


def listing(scenario: str, directory: Path | None = None) -> dict:
    """What is recorded for a scenario, for the screen: which routes for the stress test, which sentences for “Ask”."""
    listed: dict = {"stress": [], "ask": []}
    for recording in every(directory):
        if recording["scenario"] == scenario and recording["kind"] in listed:
            entry = {"language": recording["language"], "path": recording["path"], "assumptions": recording["assumptions"],
                     "model": recording["model"], "recorded_at": recording["recorded_at"]}
            if recording["kind"] == "ask":
                entry["sentence"] = recording["sentence"]
            listed[recording["kind"]].append(entry)
    return listed
