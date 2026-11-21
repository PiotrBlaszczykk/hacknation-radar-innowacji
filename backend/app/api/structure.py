from flask import Blueprint, abort, jsonify

from ..services import llm, structuring
from .common import json_body

bp = Blueprint("structure", __name__)


@bp.post("/structure")
def structure():
    text = json_body().get("text")
    if not isinstance(text, str) or len(text.strip()) < 40:
        abort(400, "Wpisz opis innowacji zawierający co najmniej 40 znaków.")
    try:
        return jsonify(structuring.structure_text(text))
    except llm.LLMUnavailable:
        abort(503, "Automatyczne układanie karty jest chwilowo niedostępne. Formularz możesz wypełnić ręcznie.")
