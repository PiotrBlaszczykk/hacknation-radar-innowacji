import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.orm import joinedload, load_only

from .. import domain
from ..extensions import db
from ..models import Innovation, Interaction, User
from . import rules

I = Innovation
NEWEST_ORDER = (I.created_at.desc(), I.id.desc())
POST_FIELDS = (
    I.id, I.title, I.summary, I.kind, I.stage, I.domains, I.support_needs, I.keywords,
    I.origin, I.source_name, I.source_url, I.claimed, I.status, I.score, I.path,
    I.novelty, I.created_at, I.organization_id, I.author_id,
)
STOP_WORDS = set(
    "a aby albo bez bo chcę chcemy czy dla do i ich jak jaki jest ma można na nad np o od oraz po pod "
    "podczas przez przy się sposób szukam szukamy to w we z za ze żeby".split()
)


def _days_since(column, now):
    return func.greatest(0, func.extract("epoch", now - column) / 86400)


def interaction_stats(scope, persona_id, now):
    age = _days_since(Interaction.created_at, now)
    popularity_weight = case(
        rules.POPULAR_WEIGHTS, value=Interaction.type, else_=0,
    )
    recent = Interaction.created_at.between(now - timedelta(days=rules.POPULAR_DAYS), now)
    return (
        select(
            Interaction.innovation_id,
            func.count().label("attention"),
            func.count().filter(Interaction.type == "podbicie").label("bumps"),
            func.count().filter(Interaction.type == "zainteresowany").label("interest_count"),
            func.count().filter(Interaction.type == "komentarz").label("comments_count"),
            func.count().filter(
                Interaction.type == "podbicie", Interaction.user_id == persona_id,
            ).label("my_bumps"),
            func.coalesce(
                func.sum(popularity_weight * func.power(0.5, age / rules.POPULAR_HALF_LIFE_DAYS)).filter(recent), 0,
            ).label("popularity"),
        )
        .join(scope, scope.c.id == Interaction.innovation_id)
        .group_by(Interaction.innovation_id)
        .subquery()
    )


def _base(scope, stats):
    metrics = ("attention", "bumps", "interest_count", "comments_count", "my_bumps", "popularity")
    return (
        select(I.id, *(func.coalesce(stats.c[key], 0).label(key) for key in metrics))
        .join(scope, scope.c.id == I.id)
        .outerjoin(stats, stats.c.innovation_id == I.id)
    )


def _lexical(query):
    terms = dict.fromkeys(
        word for word in re.findall(r"[^\W_]+", query.casefold()) if len(word) >= 2 and word not in STOP_WORDS
    )
    if not terms:
        return literal(0.0)
    words = list(terms)[:32]
    text = func.concat_ws(" ", I.summary, I.description, I.problem, I.solution, I.keywords)
    term_hits = []
    for word in words:
        pattern = r"\m" + re.escape(word) + (r"\M" if len(word) < 5 else "")
        matches = [(I.title.op("~*")(pattern), 1.0), (text.op("~*")(pattern), 0.85)]
        if len(word) >= 7 and word.isalpha():
            # Dłuższy wspólny początek łapie część odmian. Jedno takie trafienie nie wystarczy.
            prefix = r"\m" + re.escape(word[:-2])
            matches.extend([(I.title.op("~*")(prefix), 0.6), (text.op("~*")(prefix), 0.5)])
        term_hits.append(case(*matches, else_=0.0))
    hits = sum(term_hits)
    minimum = 1.0 if len(words) >= 3 else 0.85
    return case((hits >= minimum, hits / len(words)), else_=0.0)


def _area_weights(user):
    personal = set(user.interests or [])
    organization = set((user.organization.interests or []) if user.organization else [])
    return {key: 0.75 if key in personal else 0.35 for key in sorted(personal | organization)}


def _role_fit(user):
    if user.role == "broker":
        return case((I.status.in_(rules.BROKER_PENDING), 1.0), else_=0.0), literal(0.0)
    kind = user.organization.kind if user.organization else None
    needs = rules.NEED_FIT.get(kind, ())
    stages = rules.STAGE_FIT.get(kind, {})
    need = case((or_(*(I.support_needs.has_key(key) for key in needs)), 1.0), else_=0.0) if needs else literal(0.0)
    stage = case(stages, value=I.stage, else_=0.0) if stages else literal(0.0)
    return need, stage


def dla_ciebie(base, stats, user, vector, query, now):
    similarity = func.coalesce(1 - I.embedding.cosine_distance(vector), 0.0) if vector is not None else literal(0.0)
    semantic = func.least(1.0, func.greatest(
        0.0, (similarity - rules.SIMILARITY_LOW) / (rules.SIMILARITY_HIGH - rules.SIMILARITY_LOW),
    ))
    lexical = _lexical(query) if query else literal(0.0)
    if query:
        base = base.where(or_(lexical > 0, similarity >= rules.QUERY_MATCH_MIN))
        content = (
            lexical if vector is None
            else rules.QUERY_VECTOR_WEIGHT * semantic + (1 - rules.QUERY_VECTOR_WEIGHT) * lexical
        )
    else:
        content = semantic

    need, stage = _role_fit(user)
    areas = sum(case((I.domains.has_key(key), weight), else_=0.0) for key, weight in _area_weights(user).items())
    components = {
        "content": content,
        "areas": func.least(1.0, areas),
        "need": need,
        "stage": stage,
        "potential": func.coalesce(I.score, 0.0) / 100,
        "freshness": func.power(0.5, _days_since(I.created_at, now) / rules.FRESHNESS_HALF_LIFE_DAYS),
        "activity": func.least(1.0, func.coalesce(stats.c.popularity, 0.0) / rules.PERSONAL_ACTIVITY_CAP),
    }
    weights = rules.WEIGHTS["query" if query else "profile"]
    rank = sum(components[key] * weight for key, weight in weights.items()).label("rank")
    order = [rank.desc(), *NEWEST_ORDER]
    if not query and user.organization_id is not None:
        order.insert(0, func.coalesce(I.organization_id == user.organization_id, False))
    return base.add_columns(
        *(expr.label(name) for name, expr in components.items()),
        (similarity >= rules.QUERY_MATCH_MIN).label("semantic_match"),
        (lexical > 0).label("word_match"),
    ).order_by(*order)


def popularne(base, stats):
    return base.where(stats.c.popularity > 0).order_by(stats.c.popularity.desc(), *NEWEST_ORDER)


def _radar_pending():
    return and_(I.origin == "radar", I.claimed.is_(False))


def perelki(base, stats):
    attention = func.coalesce(stats.c.attention, 0)
    rank = I.score - rules.GEM_ATTENTION_PENALTY * attention + case((_radar_pending(), rules.GEM_RADAR_BONUS), else_=0)
    return base.where(I.score > rules.GEM_SCORE_THRESHOLD, attention <= rules.GEM_MAX_ATTENTION).order_by(
        rank.desc(), *NEWEST_ORDER,
    )


def najnowsze(base):
    return base.order_by(*NEWEST_ORDER)


def _why_personal(innovation, row, user, query):
    shared = set(innovation.domains or []) & _area_weights(user).keys()
    labels = (domain.DOMAINS.get(area, area) for area in sorted(shared))
    areas = [label[:1].lower() + label[1:] for label in labels]
    kind = user.organization.kind if user.organization else None
    if user.role == "broker":
        need_reason = "Wpis czeka na decyzję brokera."
    else:
        need = next((key for key in rules.NEED_FIT.get(kind, ()) if key in (innovation.support_needs or [])), None)
        need_reason = rules.NEED_REASONS.get(need)

    content_reason = "Treść pasuje do opisu w Twoim profilu."
    if query:
        if row["semantic_match"] and row["word_match"]:
            content_reason = "Pasuje temat i słownictwo z Twojego opisu."
        elif row["semantic_match"]:
            content_reason = "Temat pasuje do Twojego opisu."
        else:
            content_reason = "Słownictwo pasuje do Twojego opisu."

    reasons = {
        "content": content_reason,
        "areas": "Wspólne obszary z Twoim profilem lub organizacją: " + ", ".join(areas) + ".",
        "need": need_reason,
        "stage": f"Etap pasuje do Twojej organizacji — {domain.STAGES.get(innovation.stage, '').lower()}.",
        "potential": f"Ocena potencjału to {round(innovation.score)}/100." if innovation.score is not None else None,
        "freshness": f"Wpis jest w radarze od {innovation.created_at:%d.%m.%Y}.",
        "activity": "Wpis zebrał interakcje w ostatnich dniach.",
    }
    weights = rules.WEIGHTS["query" if query else "profile"]
    contributions = [(row[key] * weight, reasons[key]) for key, weight in weights.items() if row[key] > 0 and reasons[key]]
    contributions.sort(key=lambda item: item[0], reverse=True)
    if not query:
        return " ".join(reason for _, reason in contributions[:2])
    other_reason = next((reason for _, reason in contributions if reason != content_reason), "")
    return " ".join(filter(None, (content_reason, other_reason)))


def _why_gem(innovation, row):
    reason = f"Wysoki potencjał ({round(innovation.score)}/100)."
    if not row["attention"]:
        return reason + " Wpis nie zebrał jeszcze żadnych interakcji."
    return reason + f" Liczba dotychczasowych interakcji: {row['attention']}."


def feed_page(tab, filters, user: User | None, vector, query, limit, offset):
    now = datetime.now(UTC).replace(tzinfo=None)
    scope = select(I.id).where(*filters).cte("feed_scope")
    stats = interaction_stats(scope, user.id if user else None, now)
    base = _base(scope, stats)
    if tab == "dla_ciebie":
        ranked = dla_ciebie(base, stats, user, vector, query, now)
    elif tab == "popularne":
        ranked = popularne(base, stats)
    elif tab == "perelki":
        ranked = perelki(base, stats)
    else:
        ranked = najnowsze(base)

    # Filtry i sortowanie działają w bazie. Treść kart i powody pobieramy tylko dla bieżącej strony.
    page = db.session.execute(
        ranked.add_columns(func.count().over().label("total")).limit(limit).offset(offset)
    ).mappings().all()
    total = page[0]["total"] if page else 0
    if not page and offset:
        total = db.session.scalar(select(func.count()).select_from(ranked.order_by(None).subquery()))

    items = []
    if page:
        innovations = db.session.scalars(
            select(I).where(I.id.in_([row["id"] for row in page])).options(
                load_only(*POST_FIELDS), joinedload(I.organization), joinedload(I.author).load_only(User.id, User.name, User.title),
            ),
        )
        by_id = {innovation.id: innovation for innovation in innovations}
        for row in page:
            innovation = by_id.get(row["id"])
            if innovation is None:
                continue
            why = ""
            if tab == "dla_ciebie":
                why = _why_personal(innovation, row, user, query)
            elif tab == "perelki":
                why = _why_gem(innovation, row)
            items.append({
                **innovation.to_dict(), "why": why, "bumps": row["bumps"], "bumped": bool(row["my_bumps"]),
                "interest_count": row["interest_count"], "comments_count": row["comments_count"],
            })
    return {"items": items, "total": total, "limit": limit, "offset": offset}
