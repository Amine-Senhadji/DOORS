"""Makes docs/demo.gif: fifteen seconds of the running application, one still picture per scene.

Nothing in the picture is drawn by hand. This script starts a local server of Doors, headless Chrome takes each
picture from it, and Pillow puts the pictures together. Run from the root of the repository:

    .venv/bin/python scripts/demo_gif.py

It needs two things that the project does not ask for anywhere else:

- Pillow, which is NOT one of the project's dependencies: requirements.txt does not list it, and nothing but this
  script imports it. Install it where the script runs:

      .venv/bin/pip install pillow

  To leave the environment of the project as it is, install it in a folder of its own and point the script to it:

      .venv/bin/pip install --target some/folder pillow
      PYTHONPATH=some/folder .venv/bin/python scripts/demo_gif.py

  Without Pillow the script stops at once, before it starts a server or a browser, and says so.
- Google Chrome or Chromium. CHROME_BIN names the browser when it is not in one of the usual places.

The server runs in recorded mode: no model is called, whatever the environment holds. Chrome is started once per
picture, never twice at the same time.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DOORS_AI"] = "recorded"            # before the application is loaded: the page of the demo calls no model

WIDTH, HEIGHT, STRIP = 1280, 1100, 64          # the page as Chrome draws it, and the strip of the caption under it
# One scene: how long it stays, the address of the page, and the sentence under it. No figure is written here:
# every figure of the picture is on the page, and comes from the engine.
SCENES = [
    (3.0, "/", "Alexia's plan: five years of work, a master's at 25, then work again. Each station is a goal."),
    (2.5, "/?monde=krach@24", "Service updates: a market crash at 24."),
    (3.0, "/?monde=krach@24&station=reconversion", "“Career change” turns red: in this world, the plan no longer holds this goal."),
    (3.0, "/?monde=krach@24&gare=72", "The signpost at 26: below this amount set aside, the route stops holding “Career change”."),
    (3.5, "/?politiques=1", "Policies, not plans: a rule read at 26 keeps the goal in all four worlds of the table."),
]
# The page of one picture: Doors in a frame, and the caption under it, in the fonts and colours of Doors.
FRAME = f"""<!doctype html>
<meta charset="utf-8">
<title>Doors, the demo</title>
<link rel="stylesheet" href="/style.css">
<style>
  body {{ display: block; min-height: 0; background: var(--map); overflow: hidden; }}
  iframe {{ display: block; width: {WIDTH}px; height: {HEIGHT}px; border: 0; }}
  p {{ margin: 0; height: {STRIP}px; padding: 0 28px; display: flex; align-items: center; gap: 16px; border-top: 1px solid var(--edge-strong);
       font-size: 22px; font-weight: 500; color: var(--text); white-space: nowrap; }}
  b {{ font-family: var(--title); font-size: 24px; font-weight: 700; color: var(--lamp); }}
</style>
<iframe id="page"></iframe>
<p><b id="step"></b><span id="caption"></span></p>
<script>
  const asked = new URLSearchParams(location.search);
  document.getElementById('page').src = asked.get('page');
  document.getElementById('step').textContent = asked.get('step');
  document.getElementById('caption').textContent = asked.get('caption');
</script>
"""


# Where the browser usually is: the same places as for the tests that read the page (tests/browser.py).
USUAL = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
PILLOW = ("Pillow is needed to put the pictures together, and it is not one of the project's dependencies. Install it with "
          "`.venv/bin/pip install pillow`, or in a folder of its own with `pip install --target some/folder pillow` and run this script "
          "with PYTHONPATH=some/folder.")


def chrome() -> str:
    """The browser: the one CHROME_BIN names (a path that leads nowhere means that there is none), else the first of the usual places."""
    named = os.environ.get("CHROME_BIN")
    found = shutil.which(named) if named else next(filter(None, map(shutil.which, USUAL)), None)
    if found is None:
        raise SystemExit("Chrome is needed to take the pictures: it was not found on this machine. CHROME_BIN can name it.")
    return found


def pillow():
    """Pillow's Image module, or the end of the script with the way to install it."""
    try:
        from PIL import Image
    except ImportError:
        raise SystemExit(PILLOW) from None
    return Image


def serve():
    """Doors on a free port of this machine, behind one more page: the frame of a picture. Returns the server and its port."""
    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    from api.main import app

    outer = FastAPI()
    outer.add_api_route("/demo-frame", lambda: HTMLResponse(FRAME), methods=["GET"])
    outer.mount("/", app)
    server = uvicorn.Server(uvicorn.Config(outer, host="127.0.0.1", port=0, log_level="error"))      # port 0: any free port of this machine
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(200):
        if server.started:
            return server, server.servers[0].sockets[0].getsockname()[1]
        time.sleep(0.05)
    raise SystemExit("The local server of Doors did not start.")


def pictures(folder: Path) -> list[Path]:
    """One picture per scene, taken by headless Chrome from the running application."""
    server, port = serve()
    taken = []
    try:
        for number, (_, address, caption) in enumerate(SCENES, 1):
            file = folder / f"scene-{number}.png"
            asked = f"http://127.0.0.1:{port}/demo-frame?page={quote(address, safe='')}&step={number}/{len(SCENES)}&caption={quote(caption, safe='')}"
            subprocess.run([chrome(), "--headless=new", f"--window-size={WIDTH},{HEIGHT + STRIP}", "--hide-scrollbars", "--virtual-time-budget=12000",
                            f"--screenshot={file}", asked], capture_output=True, timeout=120, check=True)
            taken.append(file)
            print(f"  scene {number}: {address}")
    finally:
        server.should_exit = True
    return taken


def assemble(files: list[Path], out: Path) -> None:
    """The pictures put together: each one stays as long as its scene, and the whole plays again from the start."""
    Image = pillow()
    frames = [Image.open(file).convert("RGB") for file in files]
    for frame in frames:
        if frame.size != (WIDTH, HEIGHT + STRIP):
            raise SystemExit(f"A picture is {frame.size}, and not {(WIDTH, HEIGHT + STRIP)}: the window of Chrome was not the one asked for.")
    # 256 colours per picture, as the format asks. Flat colours and small text: no dithering keeps the text sharp and the
    # file small. And the few bright colours of the map each have a meaning: of the methods of Pillow, this one keeps
    # them (no colour of a picture moves by more than a few levels out of 255).
    reduced = [frame.quantize(colors=256, method=Image.Quantize.MAXCOVERAGE, dither=Image.Dither.NONE) for frame in frames]
    reduced[0].save(out, save_all=True, append_images=reduced[1:], duration=[round(seconds * 1000) for seconds, _, _ in SCENES], loop=0, disposal=1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Makes docs/demo.gif from the running application.")
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "demo.gif")
    parser.add_argument("--keep", type=Path, help="a folder where the pictures of the scenes are kept as PNG files")
    args = parser.parse_args(argv)
    pillow()                    # before anything is started: a missing Pillow is found in a second, not after the pictures
    chrome()                    # likewise for the browser
    with tempfile.TemporaryDirectory(prefix="doors-demo-") as temporary:
        folder = args.keep or Path(temporary)
        folder.mkdir(parents=True, exist_ok=True)
        print(f"{len(SCENES)} scenes, {sum(seconds for seconds, _, _ in SCENES):g} seconds:")
        assemble(pictures(folder), args.out)
    print(f"{args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}: {args.out.stat().st_size / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
