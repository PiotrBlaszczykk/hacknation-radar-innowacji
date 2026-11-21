from flask import Blueprint, jsonify

from ..opportunities import analyze

bp = Blueprint("opportunities", __name__)


@bp.get("/opportunities")
def list_opportunities():
    response = jsonify(analyze())
    response.cache_control.no_store = True
    return response
