from pathlib import Path

from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, Response
from starlette.routing import Route, Router

DIST_DIR = Path(__file__).resolve().parents[4] / "frontend" / "dist"


class DashboardApp(Router):
    """Serves the React SPA from frontend/dist/."""

    def __init__(self) -> None:
        handler = self.spa if DIST_DIR.is_dir() else self.not_built
        super().__init__(routes=[Route("/{path:path}", handler, methods=["GET"])])

    async def spa(self, request: Request) -> Response:
        path = request.path_params.get("path", "")
        file = DIST_DIR / path
        if path and file.is_file():
            return FileResponse(file)
        return FileResponse(DIST_DIR / "index.html")

    async def not_built(self, request: Request) -> Response:
        return HTMLResponse(
            "<h1>Frontend not built</h1>"
            "<p>Run: <code>cd frontend &amp;&amp; pnpm install &amp;&amp; pnpm build</code></p>",
            status_code=503,
        )
