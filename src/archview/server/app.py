"""The local HTTP API and the static UI (requirements V1-V15).

Bound to localhost by the CLI, no network calls, and the only files it reads are
the ones the model already lists as source files.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

from archview.server.state import NotFound, ViewerState

UI = Path(__file__).resolve().parent.parent / "ui"
NO_STORE = {"Cache-Control": "no-store"}


def create_app(state: ViewerState) -> FastAPI:
    app = FastAPI(title="archview", docs_url=None, redoc_url=None, openapi_url=None)

    def found(call):
        try:
            return call()
        except NotFound as error:
            raise HTTPException(404, str(error)) from error

    @app.get("/api/project")
    def project() -> dict:
        return state.summary()

    @app.get("/api/view")
    def view(
        root: str | None = None,
        externals: bool = False,
        hide_tests: bool = False,
        package: str | None = None,
    ) -> dict:
        return found(lambda: state.view(root, externals, hide_tests, package))

    @app.get("/api/tree")
    def tree(root: str | None = None, hide_tests: bool = False, package: str | None = None) -> dict:
        return found(lambda: state.tree(root, hide_tests, package))

    @app.get("/api/check")
    def check(package: str | None = None) -> dict:
        return found(lambda: state.check(package))

    @app.get("/api/export", response_class=PlainTextResponse)
    def export(
        format: str,
        root: str | None = None,
        externals: bool = False,
        hide_tests: bool = False,
        package: str | None = None,
    ) -> str:
        return found(lambda: state.export(root, format, externals, hide_tests, package))

    @app.get("/api/source")
    def source(module: str, package: str | None = None) -> dict:
        return found(lambda: state.source(module, package))

    @app.post("/api/reanalyze")
    def reanalyze() -> dict:
        state.reload()
        return state.summary()

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(UI / "index.html", headers=NO_STORE)

    @app.get("/ui/{name:path}")
    def static(name: str) -> FileResponse:
        path = (UI / name).resolve()
        if not path.is_file() or UI not in path.parents:
            raise HTTPException(404, "not found")
        return FileResponse(path, headers=NO_STORE)

    return app
