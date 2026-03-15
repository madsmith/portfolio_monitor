from starlette.requests import Request
from starlette.responses import JSONResponse

from portfolio_monitor.service.settings import AccountStore, Role, SessionStore


def accounts_handler(account_store: AccountStore, session_store: SessionStore, default_username: str):
    """Return route handlers for account management (admin-only) and per-account alerts."""

    async def list_accounts(request: Request) -> JSONResponse:
        accounts = [
            {"username": a.username, "role": str(a.role)}
            for a in account_store.get_all()
        ]
        # Prepend the default admin as a synthetic entry
        return JSONResponse(
            [{"username": default_username, "role": "admin", "is_default": True}] + accounts
        )

    async def create_account(request: Request) -> JSONResponse:
        try:
            data = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid request body"}, status_code=400)
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))
        role_str = str(data.get("role", "normal"))
        if not username or not password:
            return JSONResponse({"error": "username and password are required"}, status_code=400)
        if username == default_username:
            return JSONResponse({"error": "cannot create account with that username"}, status_code=409)
        try:
            role = Role(role_str)
        except ValueError:
            return JSONResponse({"error": f"invalid role: {role_str}"}, status_code=400)
        try:
            account = account_store.create(username, password, role)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=409)
        account_store.save()
        return JSONResponse({"username": account.username, "role": str(account.role)}, status_code=201)

    async def delete_account(request: Request) -> JSONResponse:
        username = request.path_params["username"]
        if username == default_username:
            return JSONResponse({"error": "cannot delete the default admin account"}, status_code=403)
        deleted = account_store.delete(username)
        if not deleted:
            return JSONResponse({"error": "account not found"}, status_code=404)
        account_store.save()
        return JSONResponse({"ok": True})

    async def update_account(request: Request) -> JSONResponse:
        """Update role for an account."""
        username = request.path_params["username"]
        if username == default_username:
            return JSONResponse({"error": "cannot modify the default admin account"}, status_code=403)
        try:
            data = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid request body"}, status_code=400)
        if "role" in data:
            try:
                role = Role(data["role"])
            except ValueError:
                return JSONResponse({"error": f"invalid role: {data['role']}"}, status_code=400)
            if not account_store.update_role(username, role):
                return JSONResponse({"error": "account not found"}, status_code=404)
        account_store.save()
        return JSONResponse({"ok": True})

    async def reset_password(request: Request) -> JSONResponse:
        """Reset password for an account (admin or self)."""
        target_username = request.path_params["username"]
        caller = request.user.display_name
        is_admin = "role:admin" in request.auth.scopes
        # Admins can reset anyone's password; others can only reset their own
        if not is_admin and caller != target_username:
            return JSONResponse({"error": "forbidden"}, status_code=403)
        if target_username == default_username:
            return JSONResponse(
                {"error": "cannot change default admin password via API; update config_private.yaml"},
                status_code=403,
            )
        try:
            data = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid request body"}, status_code=400)
        password = str(data.get("password", ""))
        if not password:
            return JSONResponse({"error": "password is required"}, status_code=400)
        if not account_store.update_password(target_username, password):
            return JSONResponse({"error": "account not found"}, status_code=404)
        account_store.save()
        return JSONResponse({"ok": True})

    async def get_account_alerts(request: Request) -> JSONResponse:
        username = request.path_params["username"]
        if username == default_username:
            return JSONResponse(account_store.get_default_admin_alerts())
        account = account_store.get(username)
        if account is None:
            return JSONResponse({"error": "account not found"}, status_code=404)
        return JSONResponse(account.alerts)

    async def update_account_alerts(request: Request) -> JSONResponse:
        username = request.path_params["username"]
        try:
            alerts = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid request body"}, status_code=400)
        if username == default_username:
            account_store.set_default_admin_alerts(alerts)
            account_store.save()
            return JSONResponse({"ok": True})
        if not account_store.update_alerts(username, alerts):
            return JSONResponse({"error": "account not found"}, status_code=404)
        account_store.save()
        return JSONResponse({"ok": True})

    return (
        list_accounts,
        create_account,
        delete_account,
        update_account,
        reset_password,
        get_account_alerts,
        update_account_alerts,
    )
