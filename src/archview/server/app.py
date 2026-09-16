"""The local HTTP API and the static UI (requirements V1-V6, V13).

Bound to localhost by the CLI, no network calls, and the only files it reads are
the ones the model already lists as source files.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from archview.server.workspace import NotFound, Workspace

UI = Path(__file__).resolve().parent.parent / "ui"


def create_app(workspace: Workspace) -> FastAPI:
    app = FastAPI(title="archview", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/api/project")
    def project() -> dict:
        return workspace.summary()

    @app.get("/api/view")
    def view(root: str | None = None) -> dict:
        try:
            return workspace.view(root)
        except NotFound as error:
            raise HTTPException(404, str(error)) from error

    @app.get("/api/source")
    def source(module: str) -> dict:
        try:
            return workspace.source(module)
        except NotFound as error:
            raise HTTPException(404, str(error)) from error

    @app.post("/api/reanalyze")
    def reanalyze() -> dict:
        workspace.reload()
        return workspace.summary()

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(UI / "index.html", headers={"Cache-Control": "no-store"})

    app.mount("/ui", StaticFiles(directory=UI), name="ui")
    return app
