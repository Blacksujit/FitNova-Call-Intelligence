"""Seed the database with one Org, two Teams, and 3 Advisors per team."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fitnova.storage.db import init_db, get_session
from fitnova.storage.models import Org, Team, Advisor


def seed():
    init_db()
    session = get_session()
    try:
        if session.query(Org).first():
            print("DB already seeded, skipping.")
            return

        org = Org(name="FitNova")
        session.add(org)
        session.flush()

        alpha = Team(org_id=org.id, name="Alpha Pod")
        beta = Team(org_id=org.id, name="Beta Pod")
        session.add_all([alpha, beta])
        session.flush()

        advisors = [
            Advisor(team_id=alpha.id, name="Priya Sharma", email="priya@fitnova.in"),
            Advisor(team_id=alpha.id, name="Rahul Verma", email="rahul@fitnova.in"),
            Advisor(team_id=alpha.id, name="Sneha Kapoor", email="sneha@fitnova.in"),
            Advisor(team_id=beta.id, name="Ananya Patel", email="ananya@fitnova.in"),
            Advisor(team_id=beta.id, name="Vikram Singh", email="vikram@fitnova.in"),
            Advisor(team_id=beta.id, name="Arjun Nair", email="arjun@fitnova.in"),
        ]
        session.add_all(advisors)
        session.commit()
        print(f"Seeded: {org.name} — 2 teams, {len(advisors)} advisors.")
    finally:
        session.close()


if __name__ == "__main__":
    seed()
