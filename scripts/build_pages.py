"""Build the public demo: the viewer on examples/pizzeria as a static site (ADR 0022).

    uv run scripts/build_pages.py _site

Writes the page, a copy of the UI and snapshot.json, with every answer the viewer can
ask for and the note in scripts/pages/about.html, into a folder that must not exist yet.
GitHub Actions runs it on every push to main and publishes the folder to GitHub Pages.
"""

import sys
from pathlib import Path

from archview.server.snapshot import write_site
from archview.server.state import ViewerState

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "examples" / "pizzeria"
NOTE = Path(__file__).resolve().parent / "pages" / "about.html"


def main(out: str) -> None:
    write_site(ViewerState(DEMO), Path(out), about=NOTE.read_text())
    print(f"wrote the pizzeria demo to {out}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: uv run scripts/build_pages.py <out-folder>")
    main(sys.argv[1])
