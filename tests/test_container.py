"""The container of the online demo and its Render blueprint: what they say, and what they do.

Docker is not needed to run these tests; one of them, which is off unless DOORS_TEST_DOCKER=1, uses it. The files are
read line by line. The build context is made again from .dockerignore, and the server is started in it the way the
container starts it: with the command of the Dockerfile, and the port given in PORT. What is checked is that the demo
starts, answers on every route of the page and serves every file of the interface, listens on every interface, holds
less than the free plan gives it, stops when it is told to, and is in recorded mode whatever the environment holds.
"""
from __future__ import annotations

import offline  # noqa: F401  the recorded mode, and no client of the SDK: before anything else

import contextlib
import json
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

try:
    from fastapi.testclient import TestClient
    from api.main import app
except ImportError:  # pragma: no cover
    TestClient = None

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
IGNORE = (ROOT / ".dockerignore").read_text(encoding="utf-8")
BLUEPRINT = (ROOT / "render.yaml").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")
SHAPED = "sk-" + "ant-" + "api03-" + "k" * 60                    # the shape of a key, put together here: it is not one
FREE_PLAN_MB = 512                                               # what Render gives a free web service, in memory
HOLDS_LESS_THAN_MB = 200                                         # what the README says the server holds, once every route has been asked
STORY = [{"block": "job", "years": 5}, {"block": "master", "years": 2}, {"block": "job", "years": 3}]
ASKED = "What if I lost my job for 9 months at 27?"
# What the page asks of the server, and a few more: (route, body). No body: a GET.
# Each route says its language: in a whole run of the tests, the process of the tests writes in French unless it is told otherwise.
CALLS = [("/scenario/alexia?lang=en", None), ("/worlds?lang=en", None), ("/assumptions?lang=en", None), ("/limits?lang=en", None), ("/limits?lang=fr", None),
         ("/checks?lang=en", None), ("/checks/starter-kit?lang=en", {}), ("/ai/status?lang=en", None),
         ("/node?lang=en", {"path": [], "gare_month": 0}), ("/path?lang=en", {"path": STORY, "world_id": "reference", "assumptions": {}}),
         ("/pathways?lang=en", {"path": STORY, "gare_month": 0, "assumptions": {}}), ("/adaptive?lang=en", {"path": STORY, "assumptions": {}}),
         ("/policies?lang=en", {"path": STORY, "assumptions": {}}), ("/folk-rule?lang=en", {"path": STORY, "assumptions": {}}),
         ("/ai/stress?lang=en", {"path": STORY, "assumptions": {}}), ("/ai/ask?lang=en", {"sentence": ASKED, "path": STORY, "assumptions": {}})]


# ---------------------------------------------------------------------------------------------------- the files, read
def code_of(text: str) -> str:
    """A configuration file without its comments: they say "no secret" and must be able to."""
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))


def stable(data):
    """An answer without what changes from one run to the next: the time of the live check of the starter kit, and its duration."""
    return {key: value for key, value in data.items() if key not in ("ran_at", "duration_s")} if isinstance(data, dict) else data


def instructions(text: str = DOCKERFILE) -> list[tuple[str, str]]:
    """The instructions of a Dockerfile, each on one line: ("FROM", "python:3.12.15-slim-trixie")."""
    lines = re.sub(r"\\\n\s*", " ", text).splitlines()
    return [(line.partition(" ")[0].upper(), line.partition(" ")[2].strip()) for line in map(str.strip, lines) if line and not line.startswith("#")]


def environment_of_the_image() -> dict[str, str]:
    values = {}
    for keyword, rest in instructions():
        if keyword == "ENV":
            values.update(item.split("=", 1) for item in shlex.split(rest))
    return values


def start_command() -> str:
    """The shell command that the container runs when it starts: the one of the last CMD."""
    words = json.loads([rest for keyword, rest in instructions() if keyword == "CMD"][-1])
    assert words[:2] == ["sh", "-c"] and len(words) == 3, words
    return words[2]


# ------------------------------------------------------------------------------------------ the build context, made again
def patterns() -> list[str]:
    return [line.strip() for line in IGNORE.splitlines() if line.strip() and not line.startswith("#")]


def regex_of(pattern: str) -> re.Pattern:
    """A pattern of .dockerignore as a regular expression, for the few forms the file uses: names, `*`, `?`, `[...]` and
    `**/`. The paths are those of the build context, and `**/` is what excludes a name at any depth."""
    out, at = "", 0
    while at < len(pattern):
        if pattern.startswith("**/", at):
            out, at = out + "(?:.*/)?", at + 3
        elif pattern[at] == "*":
            out, at = out + "[^/]*", at + 1
        elif pattern[at] == "?":
            out, at = out + "[^/]", at + 1
        elif pattern[at] == "[":
            end = pattern.index("]", at)
            out, at = out + pattern[at:end + 1], end + 1
        else:
            out, at = out + re.escape(pattern[at]), at + 1
    return re.compile(f"^{out}$")


def excluded(path: str, compiled: list[re.Pattern] | None = None) -> bool:
    """Whether the build context leaves this path out: when a pattern names it, or any folder above it."""
    compiled = compiled or [regex_of(pattern) for pattern in patterns()]
    parts = path.split("/")
    return any(each.match("/".join(parts[:count])) for each in compiled for count in range(1, len(parts) + 1))


def context_files() -> list[str]:
    """Every file of the repository that the image receives, as paths from the root."""
    compiled, found = [regex_of(pattern) for pattern in patterns()], []
    for folder, dirs, files in os.walk(ROOT):
        here = Path(folder).relative_to(ROOT).as_posix()
        here = "" if here == "." else here + "/"
        dirs[:] = [name for name in sorted(dirs) if not excluded(here + name, compiled)]
        found += [here + name for name in sorted(files) if not excluded(here + name, compiled)]
    return sorted(found)


# ------------------------------------------------------------------------------------------------- the server, started
def answer(port: int, route: str, body: dict | None = None) -> tuple[int, bytes]:
    request = urllib.request.Request(f"http://127.0.0.1:{port}{route}", data=None if body is None else json.dumps(body).encode(),
                                     method="GET" if body is None else "POST", headers={"content-type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as reply:
        return reply.status, reply.read()


@contextlib.contextmanager
def running(folder: Path):
    """The demo, started the way the container starts it. `python` is the one that runs the tests; the environment is
    the one of the image, plus a port, and a key in the shape of a real one: the demo must stay in recorded mode."""
    with tempfile.TemporaryDirectory(prefix="doors-container-") as temporary:
        wrapper = Path(temporary) / "bin" / "python"
        wrapper.parent.mkdir()
        wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
        wrapper.chmod(0o755)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        environment = {"PATH": os.pathsep.join([str(wrapper.parent), os.environ.get("PATH", "")]), "PORT": str(port), "ANTHROPIC_API_KEY": SHAPED,
                       "DOORS_AI": environment_of_the_image()["DOORS_AI"], "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}
        with open(Path(temporary) / "output.txt", "w+", encoding="utf-8") as output:
            process = subprocess.Popen(["sh", "-c", start_command()], cwd=folder, env=environment, stdout=output, stderr=subprocess.STDOUT)
            try:
                for _ in range(240):
                    if process.poll() is not None:
                        output.seek(0)
                        raise AssertionError(f"The server stopped by itself (code {process.returncode}): {output.read()[-1500:]}")
                    try:
                        answer(port, "/ai/status")
                        break
                    except OSError:
                        time.sleep(0.25)
                else:
                    raise AssertionError("The server did not answer within a minute.")
                yield process, port
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)


def resident_megabytes(pid: int) -> float:
    """The memory that a process holds: from /proc where there is one (Linux, and its slim images, which have no `ps`), else from `ps`."""
    status = Path(f"/proc/{pid}/status")
    if status.exists():
        return int(re.search(r"VmRSS:\s+(\d+) kB", status.read_text()).group(1)) / 1024
    return int(subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, check=True).stdout) / 1024


def listening_on(port: int) -> set[str]:
    """The addresses that something of this machine listens on, for this port: "*" for every interface. None where
    neither /proc nor lsof can say."""
    if Path("/proc/net/tcp").exists():
        found = set()
        for file in ("/proc/net/tcp", "/proc/net/tcp6"):
            for line in Path(file).read_text().splitlines()[1:]:
                columns = line.split()
                address, _, number = columns[1].rpartition(":")
                if columns[3] == "0A" and int(number, 16) == port:                                   # state 0A: listening
                    found.add("*" if set(address) == {"0"} else "127.0.0.1" if address == "0100007F" else address)
        return found
    if shutil.which("lsof"):
        shown = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fn"], capture_output=True, text=True).stdout
        return {line[1:].rpartition(":")[0] for line in shown.splitlines() if line.startswith("n")}
    return set()


# --------------------------------------------------------------------------------------------------------- the tests
class TheDockerfile(unittest.TestCase):
    def test_the_image_is_a_slim_python_3_12_with_its_version_pinned(self):
        self.assertEqual([rest for keyword, rest in instructions() if keyword == "FROM"], ["python:3.12.15-slim-trixie"])
        self.assertRegex(DOCKERFILE, r"(?m)^FROM python:3\.12\.\d+-slim-[a-z]+$")                        # a patch version, never `latest` or `3.12`
        self.assertIn('python-version: "3.12"', WORKFLOW)                                                # the same minor version as the tests of the workflow

    def test_the_dependencies_come_before_the_code_so_that_their_layer_is_kept(self):
        steps = [(keyword, rest) for keyword, rest in instructions() if keyword in ("COPY", "RUN")]
        self.assertEqual(steps[:3], [("COPY", "requirements.txt ./"), ("RUN", "pip install -r requirements.txt"), ("COPY", ". .")])
        env = environment_of_the_image()
        self.assertEqual((env["PIP_NO_CACHE_DIR"], env["PYTHONDONTWRITEBYTECODE"], env["PYTHONUNBUFFERED"]), ("1", "1", "1"))

    def test_the_demo_runs_in_recorded_mode_with_no_key_and_no_secret_anywhere(self):
        env = environment_of_the_image()
        self.assertEqual((env["DOORS_AI"], env["PORT"]), ("recorded", "8000"))
        for name, text in (("Dockerfile", DOCKERFILE), (".dockerignore", IGNORE), ("render.yaml", BLUEPRINT)):
            with self.subTest(file=name):
                self.assertIsNone(re.search(r"ANTHROPIC|API[_-]?KEY|SECRET|TOKEN|PASSWORD|sk-ant", code_of(text), re.IGNORECASE))
        self.assertEqual([keyword for keyword, _ in instructions() if keyword == "ARG"], [])             # nothing is passed in when the image is built
        self.assertNotIn(".env", [rest for keyword, rest in instructions() if keyword in ("COPY", "ADD")])

    def test_the_server_runs_as_a_user_with_no_rights_and_listens_on_every_interface_on_the_port_it_is_given(self):
        steps = instructions()
        self.assertIn(("RUN", "useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin doors"), steps)
        self.assertEqual(steps[[keyword for keyword, _ in steps].index("USER") + 1:][0][0], "EXPOSE")      # the last user is `doors`, before the command
        self.assertEqual([rest for keyword, rest in steps if keyword == "USER"], ["doors"])
        self.assertEqual(start_command(), "exec python -m api --host 0.0.0.0 --port ${PORT}")             # `exec`: the server is the process that is told to stop
        self.assertEqual(steps[-1][0], "CMD")

    def test_nothing_in_the_files_of_the_container_belongs_to_a_machine_or_a_person(self):
        for name, text in (("Dockerfile", DOCKERFILE), (".dockerignore", IGNORE), ("render.yaml", BLUEPRINT)):
            with self.subTest(file=name):
                self.assertIsNone(re.search(r"/Us" r"ers/|/ho" r"me/|@[\w-]+\.(com|ch|org|fr|net)", text))


class TheIgnoreFile(unittest.TestCase):
    def test_what_a_machine_leaves_around_stays_out_and_what_the_server_reads_stays_in(self):
        for path in (".venv/bin/python", ".venv/lib/python3.12/site-packages/fastapi/__init__.py", ".git/config", ".github/workflows/tests.yml", ".env", ".env.local",
                     "engine/__pycache__/simulate.cpython-312.pyc", "ai/__pycache__/x.pyc", "engine/stray.pyc", ".pytest_cache/v/cache/lastfailed", "web/.DS_Store",
                     "reports/ai_live.log", "reports/ai_dry_run.record.json", "reports/coverage.json", "benchmarks/agent.json.tmp",
                     "scripts/record_ai.py", "docs/demo.gif", "docs/screenshots/route-en.png", "Dockerfile", ".dockerignore", "render.yaml"):
            with self.subTest(out=path):
                self.assertTrue(excluded(path))
        for path in ("api/main.py", "api/__main__.py", "engine/simulate.py", "engine/scenarios/alexia.json", "ai/service.py", "ai/recorded/README.md",
                     "web/index.html", "web/app.js", "web/vendor/barlow/barlow-latin-400-normal.woff2", "web/vendor/barlow/LICENSE",
                     "docs/LIMITS.md", "docs/limits.fr.md", "Data/synthetic-goals.csv", "starter-kit/financial_twin.py", "tests/test_vs_starter_kit.py", "benchmarks/truth.json",
                     "benchmarks/random.json", "requirements.txt", "LICENSE", "NOTICE", "DISCLAIMER.md"):
            with self.subTest(kept=path):
                self.assertFalse(excluded(path))

    def test_the_patterns_use_only_the_forms_that_this_file_knows_how_to_read(self):
        self.assertGreater(len(patterns()), 15)
        for pattern in patterns():
            with self.subTest(pattern=pattern):
                self.assertRegex(pattern, r"^[\w.\-*?\[\]/]+$")                                          # no `!`, no space, no other form
                self.assertFalse(pattern.startswith("/"))

    def test_the_context_holds_the_files_the_server_reads_and_none_of_the_local_ones(self):
        files = context_files()
        self.assertGreater(len(files), 60)
        folders = {path.partition("/")[0] for path in files if "/" in path}
        self.assertEqual(folders, {"Data", "ai", "api", "benchmarks", "docs", "engine", "starter-kit", "tests", "web"})
        self.assertFalse([path for path in files if any(part in (".git", ".venv", "__pycache__", "scripts", "reports") for part in path.split("/"))])
        self.assertFalse([path for path in files if path.endswith((".pyc", ".log", ".tmp", ".DS_Store")) or "ai_dry_run" in path])
        self.assertEqual(sorted(path for path in files if "/" not in path), [".gitignore", "DISCLAIMER.md", "LICENSE", "NOTICE", "README.md", "pytest.ini", "requirements.txt"])


@unittest.skipIf(TestClient is None, "FastAPI is not installed: .venv/bin/pip install -r requirements.txt")
class TheRenderBlueprint(unittest.TestCase):
    LINES = [line.strip() for line in BLUEPRINT.splitlines() if line.strip() and not line.strip().startswith("#")]

    def test_it_is_one_web_service_on_the_free_plan_built_from_the_dockerfile(self):
        for line in ("services:", "- type: web", "name: doors", "runtime: docker", "plan: free", "dockerfilePath: ./Dockerfile", "dockerContext: ."):
            with self.subTest(line=line):
                self.assertIn(line, self.LINES)
        self.assertEqual(BLUEPRINT.count("- type:"), 1)
        self.assertTrue((ROOT / "Dockerfile").is_file())

    def test_the_server_listens_on_every_interface_and_on_the_port_of_the_platform_as_in_the_dockerfile(self):
        command = [line for line in self.LINES if line.startswith("dockerCommand:")]
        self.assertEqual(len(command), 1)
        self.assertEqual(command[0], 'dockerCommand: sh -c "' + start_command().replace("${PORT}", "$PORT") + '"')
        self.assertIn('--host 0.0.0.0 --port $PORT"', command[0])

    def test_the_health_check_is_a_route_that_exists_and_a_deploy_waits_for_the_checks(self):
        self.assertIn("healthCheckPath: /ai/status", self.LINES)
        self.assertEqual(TestClient(app).get("/ai/status").status_code, 200)
        self.assertIn("autoDeployTrigger: checksPass", self.LINES)
        self.assertIn("name: tests", WORKFLOW.splitlines())                                               # the checks it waits for are those of the workflow

    def test_it_asks_for_no_secret_and_sets_only_the_recorded_mode(self):
        at = self.LINES.index("envVars:")
        self.assertEqual(self.LINES[at:], ["envVars:", "- key: DOORS_AI", "value: recorded"])
        self.assertIsNone(re.search(r"sync:|generateValue|fromGroup|fromDatabase|fromService", BLUEPRINT))
        self.assertEqual(environment_of_the_image()["DOORS_AI"], "recorded")


class TheStartCommand(unittest.TestCase):
    """The demo started with the command of the Dockerfile, from the root of the repository, as in the container."""

    def test_it_answers_on_the_port_it_is_given_in_recorded_mode_though_the_environment_holds_a_key(self):
        with running(ROOT) as (process, port):
            status, body = answer(port, "/ai/status")
            self.assertEqual(status, 200)
            shown = json.loads(body)
            self.assertEqual((shown["mode"], shown["limits"]["live_requests_left"]), ("recorded", None))
            self.assertNotIn(SHAPED, body.decode())
            page = answer(port, "/")[1].decode()
            self.assertIn('<html lang="en"', page)

    @unittest.skipIf(TestClient is None, "FastAPI is not installed: .venv/bin/pip install -r requirements.txt")
    def test_every_route_of_the_page_answers_and_the_server_holds_less_than_the_free_plan_gives(self):
        with running(ROOT) as (process, port):
            for route, body in CALLS:
                with self.subTest(route=route):
                    self.assertEqual(answer(port, route, body)[0], 200)
            kit = json.loads(answer(port, "/checks/starter-kit?lang=en", {})[1])                            # 200 is not enough: it says in its body whether it passed
            self.assertEqual((kit["ok"], kit["failed"], kit["failures"]), (True, 0, []))
            held = resident_megabytes(process.pid)
        self.assertLess(held, HOLDS_LESS_THAN_MB, f"the server holds {held:.0f} MB once every route has been asked")
        self.assertLess(HOLDS_LESS_THAN_MB * 2.5, FREE_PLAN_MB + 1)                                                          # with room to spare for the system of the service

    def test_it_listens_on_every_interface_and_not_only_on_this_machine(self):
        with running(ROOT) as (process, port):
            found = listening_on(port)
            if not found:
                self.skipTest("neither /proc nor lsof says what this machine listens on")
            self.assertEqual(found, {"*"})

    def test_a_stop_signal_stops_the_server_itself_and_frees_the_port(self):
        with running(ROOT) as (process, port):
            process.send_signal(signal.SIGTERM)
            self.assertIn(process.wait(timeout=15), (0, -signal.SIGTERM))
        with self.assertRaises(OSError):
            answer(port, "/ai/status")


@unittest.skipIf(TestClient is None, "FastAPI is not installed: .venv/bin/pip install -r requirements.txt")
class TheBuildContext(unittest.TestCase):
    """The repository, cut down to what the image receives, and the demo started in it: nothing it needs is missing."""

    def test_the_server_started_in_the_context_answers_as_the_whole_repository_does(self):
        with tempfile.TemporaryDirectory(prefix="doors-context-") as temporary:
            copy = Path(temporary) / "app"
            for path in context_files():
                (copy / path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / path, copy / path)
            self.assertFalse(any((copy / name).exists() for name in ("scripts", "reports", ".git", ".venv", "Dockerfile", "render.yaml")))
            client = TestClient(app)
            with running(copy) as (process, port):
                for route, body in CALLS:
                    with self.subTest(route=route):
                        expected = client.get(route) if body is None else client.post(route, json=body)
                        status, shown = answer(port, route, body)
                        self.assertEqual((status, stable(json.loads(shown))), (200, stable(expected.json())))
                kit = json.loads(answer(port, "/checks/starter-kit?lang=en", {})[1])                        # the live check of the drawer passes in the context too
                self.assertEqual((kit["ok"], kit["failed"], kit["failures"]), (True, 0, []))
                # Every file of the interface is served, byte for byte, with the fonts and their licences.
                for file in sorted((ROOT / "web").rglob("*")):
                    if file.is_file() and file.name != ".DS_Store":
                        with self.subTest(file=file.relative_to(ROOT).as_posix()):
                            self.assertEqual(answer(port, "/" + file.relative_to(ROOT / "web").as_posix())[1], file.read_bytes())


@unittest.skipUnless(os.environ.get("DOORS_TEST_DOCKER") == "1", "Docker is only used with DOORS_TEST_DOCKER=1: it builds the image and runs it")
class TheImage(unittest.TestCase):
    """With Docker: the image is built, holds exactly the files of the context made here, and answers in recorded mode."""

    def test_the_image_builds_holds_the_files_of_the_context_and_answers_on_the_port_it_is_given(self):
        tag = f"doors-test:{os.getpid()}"
        docker = lambda *arguments, **keywords: subprocess.run(["docker", *arguments], capture_output=True, text=True, check=True, **keywords).stdout
        container = None
        try:
            docker("build", "-t", tag, str(ROOT))
            listed = docker("run", "--rm", "--entrypoint", "sh", tag, "-c", 'cd /app && find . -type f | sed "s|^\\./||" | sort').split()
            self.assertEqual(listed, context_files())
            container = docker("run", "-d", "-e", "PORT=10000", "-e", f"ANTHROPIC_API_KEY={SHAPED}", "-p", "127.0.0.1::10000", tag).strip()
            port = int(docker("port", container, "10000/tcp").split(":")[-1])
            for _ in range(120):
                try:
                    status = json.loads(answer(port, "/ai/status")[1])
                    break
                except (OSError, ValueError):
                    time.sleep(0.5)
            else:
                self.fail(docker("logs", container))
            self.assertEqual(status["mode"], "recorded")
            kit = json.loads(answer(port, "/checks/starter-kit?lang=en", {})[1])                            # the live check of the drawer passes in the image
            self.assertEqual((kit["ok"], kit["failed"], kit["failures"]), (True, 0, []))
            self.assertEqual(docker("exec", container, "id", "-u").strip(), "10001")
        finally:
            if container:
                subprocess.run(["docker", "rm", "-f", container], capture_output=True)
            subprocess.run(["docker", "rmi", "-f", tag], capture_output=True)


if __name__ == "__main__":
    unittest.main()
