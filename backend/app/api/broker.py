from flask import Blueprint, jsonify, request
from sqlalchemy import text

from .. import domain, scoring
from ..extensions import db
from .common import current_user, page_args, require_key

bp = Blueprint("broker", __name__)

HIGH_SCORE = 75
BOARD_LIMIT = 20

LATEST_ASSESSMENTS = """
    SELECT DISTINCT ON (innovation_id) innovation_id, total, confidence, items, criteria_version,
           items @> '[{"missing": true}]'::jsonb AS has_missing,
           confidence < CASE WHEN criteria_version = :current_version
               THEN :review_threshold ELSE :legacy_threshold END AS low_confidence
    FROM assessments
    ORDER BY innovation_id, created_at DESC, id DESC
"""

APPROVED_PATHS = """
    SELECT DISTINCT ON (innovation_id) innovation_id, payload->>'path' AS path
    FROM events
    WHERE type = 'rekomendacja_zatwierdzona' AND payload->>'path' IS NOT NULL
    ORDER BY innovation_id, created_at DESC, id DESC
"""


def _rows(sql, **params):
    return db.session.execute(text(sql), params).mappings()


def _assessment_rows(sql, **params):
    return _rows(
        sql, current_version=scoring.CRITERIA_VERSION, review_threshold=scoring.REVIEW_THRESHOLD,
        legacy_threshold=scoring.LEGACY_REVIEW_THRESHOLD, **params,
    )


def _counts(rows, keys=()):
    counts = dict.fromkeys(keys, 0)
    counts.update((row["key"], row["total"]) for row in rows)
    return counts


@bp.get("/broker/summary")
def summary():
    counts = {
        "origin": dict.fromkeys(domain.ORIGINS, 0),
        "kind": dict.fromkeys(domain.INNOVATION_KINDS, 0),
        "status": dict.fromkeys(domain.STATUSES, 0),
    }
    for row in _rows("""
        SELECT 'origin' AS dimension, origin AS key, count(*) AS total FROM innovations GROUP BY origin
        UNION ALL
        SELECT 'kind', coalesce(kind, 'nieokreslona'), count(*) FROM innovations GROUP BY kind
        UNION ALL
        SELECT 'status', status, count(*) FROM innovations GROUP BY status
    """):
        counts[row["dimension"]][row["key"]] = row["total"]

    assessments = _assessment_rows(f"""
        WITH latest AS ({LATEST_ASSESSMENTS})
        SELECT count(*) AS total,
               avg(total) FILTER (WHERE criteria_version <> :current_version
                   OR items @> '[{{"missing": false}}]'::jsonb) AS average_score,
               count(*) FILTER (WHERE low_confidence) AS low_confidence
        FROM latest
    """).one()

    paths = _counts(_rows(f"""
        WITH approved AS ({APPROVED_PATHS})
        SELECT path AS key, count(*) AS total FROM approved GROUP BY path
    """), domain.PATHS)

    matches = _counts(_rows("""
        SELECT status AS key, count(*) AS total FROM matches GROUP BY status
    """), domain.MATCH_STATUSES)
    reach = _rows("""
        SELECT (SELECT count(*) FROM innovations WHERE origin = 'radar' AND claimed) AS radar_claimed,
               count(DISTINCT m.innovation_id) FILTER (WHERE m.status = 'kontakt') AS with_contact,
               count(DISTINCT m.innovation_id)
                   FILTER (WHERE i.origin = 'radar' AND m.status <> 'odrzucone') AS radar_matched
        FROM matches m JOIN innovations i ON i.id = m.innovation_id
    """).one()

    organizations = _counts(_rows("""
        SELECT o.kind AS key, count(DISTINCT o.id) AS total
        FROM organizations o JOIN innovations i ON i.organization_id = o.id
        GROUP BY o.kind
    """), domain.ORG_KINDS)

    medians = _rows("""
        WITH starts AS (
            SELECT innovation_id, min(created_at) AS started_at
            FROM events
            WHERE type IN ('wykryta', 'zgloszona')
            GROUP BY innovation_id
        ),
        milestones AS (
            SELECT s.innovation_id, s.started_at,
                   min(e.created_at) FILTER (
                       WHERE e.type = 'oceniona'
                   ) AS assessed_at,
                   min(e.created_at) FILTER (
                       WHERE e.type = 'dopasowanie' AND e.payload->>'to' = 'kontakt'
                   ) AS contact_at
            FROM starts s
            JOIN events e ON e.innovation_id = s.innovation_id AND e.created_at >= s.started_at
            GROUP BY s.innovation_id, s.started_at
        )
        SELECT percentile_cont(0.5) WITHIN GROUP (
                   ORDER BY extract(epoch FROM assessed_at - started_at) / 86400
               ) AS to_assessment,
               percentile_cont(0.5) WITHIN GROUP (
                   ORDER BY extract(epoch FROM contact_at - started_at) / 86400
               ) AS to_contact
        FROM milestones
    """).one()

    return jsonify(
        innovations={
            "total": sum(counts["origin"].values()),
            "by_origin": counts["origin"],
            "by_kind": counts["kind"],
            "by_status": counts["status"],
            "radar_claimed": reach["radar_claimed"],
        },
        assessments=dict(assessments),
        paths={"total": sum(paths.values()), "by_path": paths},
        matches={
            "by_status": matches,
            "innovations_with_contact": reach["with_contact"],
            "radar_innovations_matched": reach["radar_matched"],
        },
        median_days=dict(medians),
        organizations={"total": sum(organizations.values()), "by_kind": organizations},
    )


@bp.get("/broker/board")
def board():
    columns = {
        status: {"status": status, "items": [], "total": 0}
        for status in domain.STATUSES if status != "archiwum"
    }
    rows = _assessment_rows(f"""
        WITH ranked AS (
            SELECT id, title, organization_id, origin, claimed, status, score,
                   count(*) OVER (PARTITION BY status) AS total,
                   row_number() OVER (
                       PARTITION BY status ORDER BY score DESC NULLS LAST, id DESC
                   ) AS position
            FROM innovations
            WHERE status <> 'archiwum'
        ),
        latest AS ({LATEST_ASSESSMENTS}),
        approved AS ({APPROVED_PATHS})
        SELECT r.id, r.title, r.origin, r.claimed, r.status, r.score, r.total,
               CASE WHEN o.id IS NOT NULL THEN json_build_object('id', o.id, 'name', o.name) END AS organization,
               coalesce(a.low_confidence OR a.has_missing, false) AS needs_review,
               p.innovation_id IS NOT NULL AS has_path,
               (SELECT count(*) FROM matches m WHERE m.innovation_id = r.id) AS matches_count,
               (SELECT count(*) FROM interactions t
                WHERE t.innovation_id = r.id AND t.type = 'zainteresowany')
                   + (SELECT count(*) FROM matches m
                      WHERE m.innovation_id = r.id AND m.status = 'zainteresowanie') AS interest_count
        FROM ranked r
        LEFT JOIN organizations o ON o.id = r.organization_id
        LEFT JOIN latest a ON a.innovation_id = r.id
        LEFT JOIN approved p ON p.innovation_id = r.id
        WHERE r.position <= :board_limit
        ORDER BY r.position
    """, board_limit=BOARD_LIMIT)

    for row in rows:
        item = dict(row)
        column = columns[item["status"]]
        column["total"] = item.pop("total")
        column["items"].append(item)
    return jsonify(columns=list(columns.values()))


QUEUE_TYPES = {
    "contact_request": "Przeczytaj prośbę o kontakt.",
    "match_interest": "Sprawdź dopasowanie i zdecyduj, czy połączyć strony.",
    "path_approval": "Zatwierdź lub wybierz inną ścieżkę.",
    "missing_evidence": "Poproś twórców o brakujące informacje.",
    "low_confidence": "Sprawdź uzasadnienie oceny i w razie potrzeby popraw kryterium.",
    "unclaimed_profile": "Poproś twórców o potwierdzenie profilu.",
}

CONTACT_REQUESTS = """
    UNION ALL
    SELECT c.innovation_id, 'contact_request',
           coalesce(o.name, 'Użytkownik radaru') || ' prosi o kontakt z twórcami.',
           candidate.id, 0, c.id, NULL
    FROM interactions c
    JOIN users u ON u.id = c.user_id
    LEFT JOIN organizations o ON o.id = u.organization_id
    LEFT JOIN LATERAL (
        SELECT m.id
        FROM matches m LEFT JOIN needs n ON n.id = m.need_id
        WHERE m.innovation_id = c.innovation_id
          AND coalesce(m.organization_id, n.organization_id) = u.organization_id
          AND m.status IN ('zainteresowanie', 'proponowane')
          AND (m.factors->>'eligible')::boolean IS NOT FALSE
        ORDER BY (m.status = 'zainteresowanie') DESC, m.score DESC, m.id
        LIMIT 1
    ) candidate ON true
    WHERE c.type = 'kontakt'
      AND NOT EXISTS (
          SELECT 1 FROM events e
          WHERE e.innovation_id = c.innovation_id AND e.type = 'dopasowanie'
            AND e.created_at >= c.created_at
            AND e.payload @> jsonb_build_object('organization_id', u.organization_id)
            AND e.payload->>'to' IN ('kontakt', 'odrzucone')
      )
"""


def _queue_source(show_contacts: bool) -> str:
    return f"""
        WITH latest AS ({LATEST_ASSESSMENTS}),
        proposed AS (
            SELECT DISTINCT ON (innovation_id) innovation_id, id, path
            FROM recommendations
            ORDER BY innovation_id, created_at DESC, id DESC
        ),
        pending AS (
            SELECT innovation_id,
                   CASE WHEN has_missing AND NOT :legacy THEN 'missing_evidence'
                        ELSE 'low_confidence' END AS type,
                   CASE WHEN has_missing THEN 'W karcie brakuje danych do części lub całości oceny.'
                   ELSE 'Model nie rozstrzygnął przesłanek z wystarczającą pewnością.' END AS description,
                   NULL::integer AS match_id, 2 AS priority, NULL::integer AS interaction_id,
                   NULL::text AS path
            FROM latest WHERE low_confidence OR has_missing
            UNION ALL
            SELECT r.innovation_id, 'path_approval',
                   'Proponowana ścieżka czeka na zatwierdzenie.', NULL, 1, NULL, r.path
            FROM proposed r
            WHERE NOT EXISTS (
                SELECT 1 FROM events e
                WHERE e.innovation_id = r.innovation_id AND e.type = 'rekomendacja_zatwierdzona'
                  AND e.payload @> jsonb_build_object('recommendation_id', r.id)
            )
            UNION ALL
            SELECT m.innovation_id, 'match_interest',
                   coalesce(o.name, 'Dopasowana organizacja') || ' zgłasza zainteresowanie i czeka na kontakt.',
                   m.id, 0, NULL, NULL
            FROM matches m
            LEFT JOIN needs n ON n.id = m.need_id
            LEFT JOIN organizations o ON o.id = coalesce(m.organization_id, n.organization_id)
            WHERE m.status = 'zainteresowanie'
              AND (:legacy OR (m.factors->>'eligible')::boolean IS NOT FALSE)
            UNION ALL
            SELECT id, 'unclaimed_profile',
                   'Wysoko oceniony profil z radaru czeka na potwierdzenie przez twórcę.', NULL, 3, NULL, NULL
            FROM innovations WHERE origin = 'radar' AND NOT claimed AND score >= :high_score
            {CONTACT_REQUESTS if show_contacts else ''}
        ),
        active AS (
            SELECT p.*, i.title, i.score
            FROM pending p JOIN innovations i ON i.id = p.innovation_id
            WHERE i.status <> 'archiwum'
        )
    """


QUEUE_ORDER = "priority, score DESC NULLS LAST, innovation_id, match_id, interaction_id"


def _queue_item(row):
    kind = row["type"]
    description = row["description"]
    next_step = QUEUE_TYPES[kind]
    if kind == "contact_request" and row["match_id"] is not None:
        next_step = "Przeczytaj prośbę i podejmij decyzję w dopasowaniu tej organizacji."
    elif kind == "path_approval":
        path = domain.PATHS.get(row["path"])
        if path:
            description = f"Proponowana ścieżka „{path}” czeka na zatwierdzenie."
    elif kind == "missing_evidence":
        missing = [item for item in row["assessment_items"] if item.get("missing")]
        criterion = max(missing, key=lambda item: item.get("weight", 0))
        if criterion.get("label"):
            description = f"Brakuje danych do oceny kryterium „{criterion['label']}”."
        if criterion.get("question"):
            next_step = f"Zapytaj twórców: {criterion['question']}"
    elif kind == "low_confidence":
        scored = [
            item for item in row["assessment_items"] or []
            if item.get("confidence") is not None and not item.get("override") and item.get("label")
        ]
        if scored:
            criterion = min(scored, key=lambda item: item["confidence"])
            description = f"Najmniej pewne kryterium to „{criterion['label']}”."

    return {
        "innovation_id": row["innovation_id"], "title": row["title"], "type": kind,
        "description": description, "next_step": next_step, "match_id": row["match_id"],
        "interaction_id": row["interaction_id"],
    }


@bp.get("/broker/queue")
def queue():
    legacy = not any(key in request.args for key in ("type", "limit", "offset"))
    if legacy:
        rows = _assessment_rows(f"""
            {_queue_source(False)}
            SELECT innovation_id, title, type, description, match_id FROM active
            ORDER BY {QUEUE_ORDER}
        """, legacy=True, high_score=HIGH_SCORE)
        items = [dict(row) for row in rows]
        return jsonify(items=items, total=len(items))

    kind = request.args.get("type")
    require_key(kind, QUEUE_TYPES, "type")
    limit, offset = page_args(default_limit=8, max_limit=50)
    user = current_user()
    rows = _assessment_rows(f"""
        {_queue_source(user is not None and user.role == "broker")},
        filtered AS (
            SELECT * FROM active WHERE CAST(:kind AS text) IS NULL OR type = :kind
        ),
        totals AS (
            SELECT (SELECT count(*) FROM filtered) AS total, count(*) AS overall FROM active
        ),
        page AS (
            SELECT * FROM filtered ORDER BY {QUEUE_ORDER} LIMIT :limit OFFSET :offset
        )
        SELECT page.*, totals.*, latest.items AS assessment_items
        FROM totals LEFT JOIN page ON true
        LEFT JOIN latest ON latest.innovation_id = page.innovation_id
            AND page.type IN ('missing_evidence', 'low_confidence')
        ORDER BY {QUEUE_ORDER}
    """, legacy=False, high_score=HIGH_SCORE, kind=kind, limit=limit, offset=offset).all()
    response = jsonify(
        items=[_queue_item(row) for row in rows if row["innovation_id"] is not None],
        total=rows[0]["total"], overall=rows[0]["overall"], limit=limit, offset=offset,
    )
    response.cache_control.no_store = True
    return response
