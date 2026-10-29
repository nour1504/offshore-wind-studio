"""HTTP API used by the interface."""

from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

from owstudio import __version__
from owstudio.api import (
    routes_analysis,
    routes_cases,
    routes_data,
    routes_energy,
    routes_engine,
    routes_explore,
    routes_fs,
    routes_geo,
    routes_import,
    routes_map,
    routes_media,
    routes_method,
    routes_observations,
    routes_reference,
    routes_results,
    routes_system,
)
from owstudio.api.state import AppState
from owstudio.core import i18n
from owstudio.core.case.model import Case
from owstudio.core.case.workspace import CaseNotFound
from owstudio.core.settings import SETTINGS_FILE


class Language:
    """Each request speaks the language of the window that sent it: the X-OWS-Lang header, or a
    ``lang`` query parameter for addresses opened directly (downloads), else the settings'."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        asked = i18n.language(headers.get(b"x-ows-lang", b"").decode("latin-1"))
        query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
        asked = asked or i18n.language((query.get("lang") or [""])[0])
        with i18n.using(asked):
            await self.app(scope, receive, send)


def create_app(
    settings_path: Path = SETTINGS_FILE,
    static_dir: Path | None = None,
    example: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Offshore Wind Studio", version=__version__)
    app.add_middleware(Language)
    state = AppState(settings_path, static_dir)
    app.state.owstudio = state
    # A new data folder starts with the reproducible Horns Rev example
    if example is not None and example.exists() and not state.workspace.list():
        state.workspace.create(Case.from_yaml(example))

    @app.exception_handler(CaseNotFound)
    async def _not_found(_: Request, error: CaseNotFound) -> JSONResponse:
        error = error.args[0] if error.args else error
        return JSONResponse(
            status_code=404,
            content={
                "detail": i18n.tr(f"Project {error} not found", f"Projet {error} introuvable")
            },
        )

    for module in (
        routes_system,
        routes_engine,
        routes_cases,
        routes_results,
        routes_reference,
        routes_data,
        routes_explore,
        routes_analysis,
        routes_energy,
        routes_observations,
        routes_media,
        routes_method,
        routes_fs,
        routes_geo,
        routes_map,
        routes_import,
    ):
        app.include_router(module.router)

    if static_dir and static_dir.is_dir():
        index = static_dir / "index.html"

        # The page opens in the language of the settings at once, before any request: the
        # window keeps nothing from one start to the next
        @app.get("/", include_in_schema=False)
        @app.get("/index.html", include_in_schema=False)
        def page() -> HTMLResponse:
            lang = state.settings.language
            html = index.read_text(encoding="utf-8").replace(
                '<html lang="en">', f'<html lang="{lang}" data-saved-lang="{lang}">', 1
            )
            return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

        app.mount("/", StaticFiles(directory=static_dir, html=True), name="interface")
    return app
