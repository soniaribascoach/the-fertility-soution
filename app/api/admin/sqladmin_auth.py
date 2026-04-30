from starlette.requests import Request
from sqladmin.authentication import AuthenticationBackend
from config import settings


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        if form.get("password", "") == settings.admin_password:
            request.session["sqladmin_authenticated"] = True
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return request.session.get("sqladmin_authenticated") is True
