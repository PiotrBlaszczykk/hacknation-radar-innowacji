from flask import abort, request

from ..extensions import db
from ..models import User


def current_user() -> User | None:
    """Prototyp nie ma logowania: front wysyła wybraną personę w nagłówku X-User-Id."""
    raw = request.headers.get("X-User-Id")
    if not raw or not raw.isdigit():
        return None
    return db.session.get(User, int(raw))


def json_body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "Oczekiwano obiektu JSON")
    return data


def require_key(value: str | None, allowed: dict, field: str) -> None:
    if value is not None and value not in allowed:
        abort(400, f"Niepoprawna wartość pola {field}: {value}")


def page_args(default_limit: int = 20, max_limit: int = 100) -> tuple[int, int]:
    limit = min(request.args.get("limit", default_limit, type=int), max_limit)
    offset = max(request.args.get("offset", 0, type=int), 0)
    return max(limit, 1), offset
