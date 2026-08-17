from fastapi import Request


def is_authenticated(request: Request) -> bool:
    return request.session.get("admin_authenticated") is True
