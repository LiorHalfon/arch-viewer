"""The local HTTP API and the static UI (requirements V1-V13).

Bound to localhost by the CLI, no network calls, and the only files it reads are
the ones the model already lists as source files.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

from archview.server.workspace import NotFound, Workspace

UI = Path(__file__).resolve().parent.parent / "ui"
NO_STORE = {"Cache-Control": "no-store"}


def create_app(workspace: Workspace) -> FastAPI:
    app = FastAPI(title="archview", docs_url=None, redoc_url=None, openapi_url=None)

    def found(call):
        try:
            return call()
        except NotFound as error:
            raise HTTPException(404, str(error)) from error

    @app.get("/api/project")
    def project() -> dict:
        return workspace.summary()

    @app.get("/api/view")
    def view(root: str | None = None, externals: bool = False, hide_tests: bool = False) -> dict:
        return found(lambda: workspace.view(root, externals, hide_tests))

    @app.get("/api/check")
    def check() -> dict:
        return found(workspace.check)

    @app.get("/api/export", response_class=PlainTextResponse)
    def export(
        format: str, root: str | None = None, externals: bool = False, hide_tests: bool = False
    ) -> str:
        return found(lambda: workspace.export(root, format, externals, hide_tests))

    @app.get("/api/source")
    def source(module: str) -> dict:
        return found(lambda: workspace.source(module))

    @app.post("/api/reanalyze")
    def reanalyze() -> dict:
        workspace.reload()
        return workspace.summary()

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
