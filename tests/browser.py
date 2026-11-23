"""Google Chrome, for the tests that read the page in a browser.

Every test module finds the browser here, so that all of them do the same on a machine that has none: the tests that
need it are skipped, each with the reason written next to it, and everything else runs. tests/test_browser.py hides the
browser for real and checks that this is what happens.

- CHROME_BIN names the browser to use, as a path or as a command. It is the browser, whatever else is installed: a
  name that leads nowhere means that there is none, and the tests that need one are skipped. Without it, the usual
  places are looked at, in the order of USUAL.
- CHROME_ARGS adds flags to every start of the browser. The continuous integration gives it --no-sandbox, which a
  browser started by a runner may need. The pages read here are the ones of a server of this machine, nothing else.
"""
from __future__ import annotations

import os
import shlex
import shutil
import unittest

# Where the browser usually is, in this order: macOS first, then the names it has on Linux.
USUAL = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
WHY = "Google Chrome is not installed (CHROME_BIN can name it): the tests that read the page in a browser are skipped"


def find(environ=os.environ, which=shutil.which) -> str | None:
    """The browser, or None. `environ` and `which` are parameters so that the search itself can be tested."""
    named = environ.get("CHROME_BIN")
    if named:
        return which(named)
    return next(filter(None, map(which, USUAL)), None)


CHROME = find()
needed = unittest.skipIf(CHROME is None, WHY)


def command(*flags: str) -> list[str]:
    """What to run to start the browser without a window: the flags of CHROME_ARGS, then the flags given."""
    assert CHROME is not None, WHY                  # a test that needs the browser is skipped before it gets here
    return [CHROME, "--headless=new", *shlex.split(os.environ.get("CHROME_ARGS", "")), *flags]
