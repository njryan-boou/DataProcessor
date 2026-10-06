"""Opt-in serving of the frontend build alongside the API."""

from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class FrontendFiles(StaticFiles):
    """Serve static files safely and keep API misses out of the SPA fallback."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        request_path = scope["path"]
        segments = [segment for segment in request_path.split("/") if segment]
        if (
            (segments and segments[0] == "api")
            or any(segment in {".", ".."} for segment in segments)
            or "\\" in request_path
            or any(ord(character) < 32 for character in request_path)
        ):
            raise HTTPException(status_code=404)

        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            # Missing JavaScript, CSS, and other assets must remain real 404s.
            # Only client-side page URLs may load the application shell.
            is_page = not Path(path).suffix and (not segments or segments[0] != "assets")
            if error.status_code != 404 or not is_page:
                raise
            return await super().get_response("index.html", scope)


def configure_frontend(app: FastAPI, directory: Path | None) -> None:
    """Mount the built application last, leaving registered API/docs routes first."""
    if directory is None:
        return

    directory = directory.resolve()
    index = directory / "index.html"
    if not directory.is_dir() or not index.is_file() or not index.resolve().is_relative_to(directory):
        raise RuntimeError(
            "DATAFLOW_FRONTEND_DIST must point to a frontend build directory containing index.html. "
            "Run npm run build in frontend and configure the resulting dist directory."
        )

    app.mount("/", FrontendFiles(directory=directory), name="frontend")
