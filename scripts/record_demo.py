# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright"]
# ///
"""Record the README's demo: the viewer on examples/pizzeria, from the top level down
to the line of code that breaks a rule, and back.

    uv run scripts/record_demo.py

Starts `archview serve` on the demo, drives the viewer in headless Chromium with a
visible pointer, and writes docs/images/demo.gif (for the README) and
docs/images/demo.mp4 (git-ignored, for posting). Needs ffmpeg on the PATH and
Playwright's Chromium (`uv run --with playwright python -m playwright install chromium`).
Every target is found in the page, never by pixel position, so a new layout still works.
"""

import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "examples" / "pizzeria"
OUT = REPO / "docs" / "images"
VIEWPORT = {"width": 1440, "height": 860}
GIF_WIDTH = 1080
GIF_FPS = 12
REST = (1250, 640)  # where the pointer starts and ends, away from the boxes

STATIONS = "pizzeria.kitchen.stations"

# The viewer's own remembered options (View menu, the files button, the panel's width):
# the diagram gets the room, and the panel is wide enough for a line of code.
OPTIONS = '{"tree": false, "legend": false, "panel": 560}'

# The only thing added to the page: an arrow that follows the mouse, since recorded
# video does not show the real pointer.
POINTER_JS = """
window.addEventListener("DOMContentLoaded", () => {
  const p = document.createElement("div");
  p.innerHTML = '<svg width="22" height="22" viewBox="0 0 22 22">'
    + '<path d="M3 2 L3 18 L7.5 14 L10.5 20.5 L13 19.3 L10 13 L16 13 Z"'
    + ' fill="#1f2328" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></svg>';
  Object.assign(p.style, {
    position: "fixed", left: "0", top: "0", zIndex: "2147483647",
    pointerEvents: "none", transformOrigin: "3px 2px", transition: "transform 80ms",
  });
  document.body.append(p);
  let x = 0, y = 0, scale = 1;
  const place = () => { p.style.transform = `translate(${x - 3}px, ${y - 2}px) scale(${scale})`; };
  addEventListener("mousemove", (e) => { x = e.clientX; y = e.clientY; place(); }, true);
  addEventListener("mousedown", () => { scale = 0.8; place(); }, true);
  addEventListener("mouseup", () => { scale = 1; place(); }, true);
});
"""

# The midpoint of an edge's line on screen: a curve's bounding-box centre can miss it.
EDGE_MIDPOINT_JS = """
([source, target]) => {
  const g = document.querySelector(
    `#graph g.edge[data-source="${source}"][data-target="${target}"]`);
  const path = g.querySelector("path");
  const at = path.getPointAtLength(path.getTotalLength() / 2);
  const m = path.getScreenCTM();
  return [at.x * m.a + at.y * m.c + m.e, at.x * m.b + at.y * m.d + m.f];
}
"""


def serve() -> tuple[subprocess.Popen, str]:
    """`archview serve` on the demo, and the URL it listens on."""
    process = subprocess.Popen(
        ["uv", "run", "--project", str(REPO), "archview", "serve", str(DEMO), "--no-open"],
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for line in process.stdout:
        found = re.search(r" at (http://\S+/)", line)
        if found:
            return process, found.group(1)
    process.wait()
    raise SystemExit(f"record_demo: archview serve exited ({process.returncode}): {line.strip()}")


def centre(page: Page, selector: str) -> tuple[float, float]:
    box = page.locator(selector).first.bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def node(page: Page, node_id: str) -> tuple[float, float]:
    return centre(page, f'#graph g.node[data-id="{node_id}"]')


def edge_point(page: Page, source: str, target: str) -> tuple[float, float]:
    return tuple(page.evaluate(EDGE_MIDPOINT_JS, [source, target]))


def aside(page: Page) -> tuple[float, float]:
    """A spot just right of the diagram, so a held view shows no hover card."""
    box = page.locator("#graph svg").bounding_box()
    return min(box["x"] + box["width"] + 60, VIEWPORT["width"] - 40), box["y"] + box["height"] / 2


def below_code(page: Page) -> tuple[float, float]:
    """A spot in the panel under the source, so the pointer does not cover a line."""
    box = page.locator("#panel").bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] * 0.7


def glide(page: Page, at: tuple[float, float], steps: int = 30) -> None:
    page.mouse.move(*at, steps=steps)


def click_at(page: Page, at: tuple[float, float]) -> None:
    glide(page, at)
    page.wait_for_timeout(250)
    page.mouse.click(*at)


def wait_for_view(page: Page, root: str) -> None:
    page.wait_for_function("(root) => document.title.startsWith(root + ' ·')", arg=root)
    page.wait_for_selector("#graph svg g.node")
    page.wait_for_timeout(300)


def shots(page: Page) -> None:
    """The shot list: top level, into the kitchen, into the stations, the broken
    rule's import, its line of code, and back to the top."""
    page.wait_for_timeout(2000)
    glide(page, node(page, "pizzeria.orders"), steps=40)
    page.wait_for_timeout(1500)
    click_at(page, node(page, "pizzeria.kitchen"))
    wait_for_view(page, "pizzeria.kitchen")
    glide(page, aside(page), steps=15)
    page.wait_for_timeout(1200)
    click_at(page, node(page, STATIONS))
    wait_for_view(page, STATIONS)
    glide(page, aside(page), steps=15)
    page.wait_for_timeout(2500)
    click_at(page, edge_point(page, f"{STATIONS}.boxing", f"{STATIONS}.dough"))
    page.wait_for_selector("#panel-body .imports li")
    glide(page, centre(page, "#panel-body .imports li"), steps=25)
    page.wait_for_timeout(1200)
    click_at(page, centre(page, "#panel-body .imports li"))
    page.wait_for_selector("#panel-body pre, #panel-body code")
    glide(page, below_code(page), steps=20)
    page.wait_for_timeout(2200)
    click_at(page, centre(page, "#crumbs a:text-is('pizzeria')"))
    wait_for_view(page, "pizzeria")
    glide(page, REST, steps=40)
    page.wait_for_timeout(1500)


def record(url: str, video_dir: Path) -> tuple[Path, float]:
    """Run the shot list; return the video and the second the top level was ready."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport=VIEWPORT,
            color_scheme="light",
            record_video_dir=str(video_dir),
            record_video_size=VIEWPORT,
        )
        context.add_init_script(f"localStorage.setItem('archview.options', '{OPTIONS}');")
        context.add_init_script(POINTER_JS)
        page = context.new_page()
        began = time.monotonic()
        page.goto(url)
        wait_for_view(page, "pizzeria")
        page.mouse.move(*REST)
        page.wait_for_timeout(200)
        start = time.monotonic() - began
        shots(page)
        video = Path(page.video.path())
        context.close()
        browser.close()
    return video, start


def encode(video: Path, start: float) -> tuple[Path, Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    gif, mp4 = OUT / "demo.gif", OUT / "demo.mp4"
    palette = (
        f"fps={GIF_FPS},scale={GIF_WIDTH}:-1:flags=lanczos,split[a][b];"
        "[a]palettegen=stats_mode=diff[p];"
        "[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle"
    )
    ffmpeg = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-i", str(video)]
    subprocess.run([*ffmpeg, "-vf", palette, "-loop", "0", str(gif)], check=True)
    mp4_args = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    subprocess.run([*ffmpeg, *mp4_args, "-crf", "20", str(mp4)], check=True)
    return gif, mp4


def main() -> int:
    if shutil.which("ffmpeg") is None:
        raise SystemExit("record_demo: ffmpeg is not on the PATH")
    process, url = serve()
    video_dir = Path(tempfile.mkdtemp(prefix="archview-demo-"))
    try:
        video, start = record(url, video_dir)
        for path in encode(video, start):
            print(f"{path.relative_to(REPO)}  {path.stat().st_size / 1e6:.1f} MB")
    finally:
        process.terminate()
        process.wait()
        shutil.rmtree(video_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
