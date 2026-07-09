from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, Session
from .models import Base, Org, Team, Advisor, Call, Segment, Score, Tag, Contest

DATABASE_URL = "sqlite:///fitnova/data/fitnova.db"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return SessionLocal()


# ── Aggregation helpers ────────────────────────────────────────────────

def _average_scores(session: Session, call_ids: list[int]) -> dict:
    if not call_ids:
        return {}
    rows = (
        session.query(Score.dimension, func.avg(Score.value))
        .filter(Score.call_id.in_(call_ids))
        .group_by(Score.dimension)
        .all()
    )
    result = {dim: round(float(avg), 2) for dim, avg in rows}
    if result:
        result["overall"] = round(sum(result.values()) / len(result), 2)
    return result


def get_advisor_average(advisor_id: int) -> dict:
    session = get_session()
    try:
        call_ids = [c.id for c in session.query(Call).filter_by(advisor_id=advisor_id).all()]
        return _average_scores(session, call_ids)
    finally:
        session.close()


def get_team_average(team_id: int) -> dict:
    session = get_session()
    try:
        advisor_ids = [a.id for a in session.query(Advisor).filter_by(team_id=team_id).all()]
        call_ids = (
            session.query(Call.id)
            .filter(Call.advisor_id.in_(advisor_ids))
            .all()
        )
        return _average_scores(session, [c[0] for c in call_ids])
    finally:
        session.close()


def get_org_average(org_id: int) -> dict:
    session = get_session()
    try:
        team_ids = [t.id for t in session.query(Team).filter_by(org_id=org_id).all()]
        advisor_ids = (
            session.query(Advisor.id)
            .filter(Advisor.team_id.in_(team_ids))
            .all()
        )
        call_ids = (
            session.query(Call.id)
            .filter(Call.advisor_id.in_([a[0] for a in advisor_ids]))
            .all()
        )
        return _average_scores(session, [c[0] for c in call_ids])
    finally:
        session.close()
