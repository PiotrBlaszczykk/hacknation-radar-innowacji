from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Daty zawsze ze strefą czasową, żeby front nie musiał zgadywać.
Base.registry.update_type_annotation_map({datetime: DateTime(timezone=True)})

db = SQLAlchemy(model_class=Base)
