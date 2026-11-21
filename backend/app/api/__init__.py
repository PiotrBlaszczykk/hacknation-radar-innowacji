"""Każdy moduł w tym pakiecie, który ma zmienną `bp` (Blueprint), jest rejestrowany
automatycznie pod /api. Nowy zestaw endpointów = nowy plik, bez edycji wspólnego kodu.
"""

import importlib
import pkgutil
import traceback

from flask import Blueprint, Flask


def register_blueprints(app: Flask) -> None:
    # Nad API pracuje kilka osób naraz. Błąd w jednym module nie może wyłączyć pozostałych,
    # więc zepsuty moduł pomijamy, a jego nazwę i błąd pokazuje /api/health.
    broken = app.config["BROKEN_MODULES"] = {}
    for mod in pkgutil.iter_modules(__path__):
        try:
            module = importlib.import_module(f"{__name__}.{mod.name}")
            bp = getattr(module, "bp", None)
            if isinstance(bp, Blueprint):
                app.register_blueprint(bp, url_prefix="/api")
        except Exception:
            broken[mod.name] = traceback.format_exc(limit=3)
            app.logger.error("Moduł api/%s.py nie załadował się:\n%s", mod.name, broken[mod.name])
