import hmac
from pathlib import Path

from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import Route, Router
from starlette.templating import Jinja2Templates

from portfolio_monitor.config import PortfolioMonitorConfig

TEMPLATES_DIR = Path(__file__).parent / "templates"


class DashboardApp(Router):
    """Dashboard web UI with session-based authentication."""

    def __init__(self, config: PortfolioMonitorConfig):
        assert config.dashboard_username, "dashboard_username is required"
        assert config.dashboard_password, "dashboard_password is required"
        self.username: str = config.dashboard_username
        self.password: str = config.dashboard_password
        self.templates: Jinja2Templates = Jinja2Templates(directory=TEMPLATES_DIR)

        super().__init__(
            routes=[
                Route("/", self.index, methods=["GET"]),
                Route("/login", self.login, methods=["GET", "POST"]),
                Route("/logout", self.logout, methods=["GET"]),
            ]
        )

    async def index(self, request: Request):
        if not request.session.get("authenticated"):
            return RedirectResponse(url="/login", status_code=302)
        return self.templates.TemplateResponse(request, "dashboard.html")

    def _check_login(self, username, password):
        return hmac.compare_digest(
            str(username), self.username
        ) and hmac.compare_digest(str(password), self.password)

    async def login(self, request: Request):
        if request.method == "GET":
            return self.templates.TemplateResponse(request, "login.html")

        form = await request.form()
        username = form.get("username", "")
        password = form.get("password", "")

        if self._check_login(username, password):
            request.session["authenticated"] = True
            return RedirectResponse(url="/", status_code=302)

        return self.templates.TemplateResponse(
            request, "login.html", context={"error": "Invalid credentials"}
        )

    async def logout(self, request: Request):
        request.session.clear()
        return RedirectResponse(url="/login", status_code=302)
